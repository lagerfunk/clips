"""Clip pipeline tests on a synthetic source (no network, no speech model): candidates, captions, render, job, delivery text."""
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from clips import candidates as cand
from clips import job as jobmod
from clips.common import probe, write_json
from clips.buffer import post_input
from clips.deliver import albums
from clips import render as rendermod
from clips.render import build_ass, groups, map_words, no_face_spans, render, VARIANTS

TEXT = ("I wasted two years on this. Nobody tells you this about money? You can lose it all in one day. I did. "
        "Here is what I learned, and why it changed everything for me. Stop saving first. Start earning more. "
        "That is the rule nobody follows. And then we went to lunch and talked about the weather for a bit. "
        "It was fine I guess, nothing special happened that afternoon at all really.")


def transcript():
    words, t = [], 1.0
    for w in TEXT.split():
        words.append({"w": w, "s": round(t, 2), "e": round(t + 0.3, 2)})
        t += 0.38 + (0.5 if w[-1] in ".?!" else 0)
    segs, cur = [], []
    for w in words:
        cur.append(w)
        if w["w"][-1] in ".?!":
            segs.append({"s": cur[0]["s"], "e": cur[-1]["e"], "text": " ".join(x["w"] for x in cur)})
            cur = []
    return {"language": "en", "words": words, "segments": segs}


class Pipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="clipstest-"))
        cls.src = cls.tmp / "src.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=40",
                        "-f", "lavfi", "-i", "sine=frequency=220:duration=40", "-c:v", "libx264", "-preset", "ultrafast",
                        "-c:a", "aac", str(cls.src)], check=True)
        cls.tr = transcript()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_candidates_start_on_a_strong_line_and_do_not_overlap(self):
        found = cand.find(self.tr, None, min_len=8, max_len=20, top=3)
        self.assertTrue(found)
        self.assertNotRegex(found[0]["first"].lower(), r"^(and|but|so)\b", "never open on a filler word")
        self.assertTrue(any("?" in c["first"] or "Nobody" in c["first"] for c in found[:2]))
        for a in found:
            self.assertTrue(8 <= a["dur"] <= 20)
            for b in found:
                if a is not b:
                    self.assertTrue(a["e"] <= b["s"] or a["s"] >= b["e"])
        self.assertLess(cand.hook_score("and then we went to lunch"), cand.hook_score("Nobody tells you this about money?"))

    def test_captions_short_groups_and_clip_timeline(self):
        words, dur = map_words(self.tr["words"], [(1.0, 5.0), (10.0, 14.0)])
        self.assertAlmostEqual(dur, 8.0)
        self.assertTrue(all(0 <= w["s"] < 8.0 for w in words))
        self.assertTrue(any(w["s"] >= 4.0 for w in words), "second moment continues after the first")
        gs = groups(words)
        self.assertTrue(all(len(g) <= 3 for g in gs))
        self.assertTrue(all(len(" ".join(x["t"] for x in g)) <= 16 or len(g) == 1 for g in gs))
        ass = build_ass(words, dur, "Nobody tells you this about money", VARIANTS["tiktok"])
        self.assertIn("Style: Hook", ass)
        self.assertEqual(ass.count(",Hook,"), 1)
        self.assertNotIn("—", ass)
        y = int(ass.split(r"\pos(540,")[1].split(")")[0])
        self.assertLess(y, 1920 * 2 / 3, "captions stay above the bottom third")

    def test_render_vertical_right_length_unique_per_platform(self):
        hashes = set()
        for p in VARIANTS:
            out = self.tmp / f"r-{p}.mp4"
            res = render(self.src, [(1.0, 5.0), (10.0, 14.5)], self.tr["words"], "Nobody tells you this", p, out, "fit", self.tmp / "w")
            info = probe(out)
            self.assertEqual((info["width"], info["height"]), (1080, 1920))
            self.assertAlmostEqual(info["duration"], 8.5, delta=0.5)
            self.assertTrue(info["audio"])
            self.assertEqual(res["layout"], "fit")
            hashes.add(hashlib.sha256(out.read_bytes()).hexdigest())
        self.assertEqual(len(hashes), 3, "no two platforms get the same file")
        with self.assertRaises(ValueError):
            render(self.src, [(35.0, 60.0)], self.tr["words"], "x", "tiktok", self.tmp / "bad.mp4", "fit", self.tmp / "w")

    def test_broll_without_a_face_is_shown_whole(self):
        seen = [(t / 2, not (6 <= t / 2 < 9)) for t in range(0, 24)]  # face lost from 6 to 9 s
        self.assertEqual(no_face_spans(seen, 12.0), [(6.0, 9.0)])
        self.assertEqual(no_face_spans([(0, True), (0.5, False), (1, True)], 2.0), [], "one missed frame is not b-roll")
        key = (str(self.src), ((1.0, 9.0),))
        rendermod._TRACKS[key] = {"steps": [(0, 100.0), (4, 500.0)], "fit": [(2.0, 5.0)]}
        try:
            res = render(self.src, [(1.0, 9.0)], self.tr["words"], "Nobody tells you this", "youtube", self.tmp / "mix.mp4", "auto", self.tmp / "w")
        finally:
            rendermod._TRACKS.pop(key, None)
        self.assertEqual(res["layout"], "crop+fit")
        self.assertAlmostEqual(probe(self.tmp / "mix.mp4")["duration"], 8.0, delta=0.5)
        y = int((self.tmp / "w" / "mix.ass").read_text().split(r"\pos(540,")[1].split(")")[0])
        self.assertEqual(y, VARIANTS["youtube"]["cap_y_wide"], "landscape captions sit under the video")

    def test_fix_words(self):
        ws = [{"w": "Zeng,", "s": 0, "e": 1}, {"w": "this", "s": 1, "e": 2}, {"w": "ID", "s": 2, "e": 3}, {"w": "loveable.", "s": 3, "e": 4}]
        out = jobmod.fix_words(ws, {"Zeng": "Zain", "ID": "idea", "loveable": "Lovable"})
        self.assertEqual([w["w"] for w in out], ["Zain,", "this", "idea", "Lovable."])

    def test_text_anchored_segments(self):
        words = self.tr["words"]
        a, b = jobmod.resolve_segment(words, {"from": "Nobody tells you", "to": "lose it all in one day."})
        self.assertLess(a, b)
        self.assertAlmostEqual(a, next(w["s"] for w in words if w["w"] == "Nobody") - 0.12, places=2)
        self.assertGreater(b, next(w["e"] for w in words if w["w"] == "day."))
        with self.assertRaises(ValueError):
            jobmod.resolve_segment(words, {"from": "not in the text", "to": "day."})
        job = {"id": "t-2", "sources": [{"id": "s1", "url": "x"}], "clips": [{"id": "01", "source": "s1", "hook": "h",
               "segments": [{"from": "Nobody tells you", "to": "one day."}]}]}
        self.assertEqual(jobmod.check_job(job), [])

    def test_job_checks_and_post_text(self):
        bad = {"id": "Bad ID", "sources": [], "clips": [{"id": "1", "source": "s9", "segments": [[5, 3]], "hook": "x" * 95}]}
        problems = jobmod.check_job(bad)
        self.assertGreaterEqual(len(problems), 4)
        good = {"id": "t-1", "campaign": {"name": "Test", "mustInclude": ["@brand"]}, "sources": [{"id": "s1", "url": "x"}],
                "clips": [{"id": "01", "source": "s1", "segments": [[1, 12]], "hook": "Nobody tells you this", "hashtags": ["#money"]}]}
        self.assertEqual(jobmod.check_job(good), [])
        pt = jobmod.post_text(good, good["clips"][0])
        self.assertTrue(pt["caption"].endswith("#ad #money @brand"), pt["caption"])
        self.assertEqual(pt["title"], "Nobody tells you this")

    def test_job_end_to_end_candidates_then_render_then_album_text(self):
        work, out = self.tmp / "work", self.tmp / "out"
        job = {"id": "e2e-1", "campaign": {"name": "Test campaign", "platforms": ["tiktok", "instagram"]},
               "sources": [{"id": "s1", "url": str(self.src)}]}
        write_json(work / "e2e-1" / "s1.words.json", self.tr)  # stands in for the speech model
        jp = self.tmp / "job.json"
        jp.write_text(json.dumps(job))
        res = jobmod.run_job(jp, work, out)
        self.assertEqual(res["stage"], "candidates")
        self.assertTrue((out / "e2e-1" / "candidates-s1.json").exists())
        job["clips"] = [{"id": "01", "source": "s1", "segments": [[1.0, 9.5]], "hook": "Nobody tells you this about money",
                         "caption": "The rule nobody follows", "hashtags": ["#money"]}]
        jp.write_text(json.dumps(job))
        m = jobmod.run_job(jp, work, out)
        self.assertEqual([f["platform"] for f in m["files"]], ["tiktok", "instagram"])
        al = albums(m)
        self.assertEqual(len(al), 1)
        self.assertIn("Post on: TikTok, Instagram Reels", al[0]["text"])
        self.assertIn("#ad", al[0]["text"])
        self.assertLessEqual(len(al[0]["text"]), 1024)


class Story(unittest.TestCase):
    def test_story_job_renders_with_fake_voice(self):
        import os
        from PIL import Image
        tmp = Path(tempfile.mkdtemp(prefix="storytest-"))
        Image.new("RGB", (1075, 1900), (240, 240, 240)).save(tmp / "a.png")
        Image.new("RGB", (1280, 720), (30, 90, 200)).save(tmp / "b.png")
        job = {"id": "s-1", "type": "story", "ownerVoice": True, "campaign": {"name": "T", "platforms": ["tiktok", "youtube"]},
               "stories": [{"id": "01", "hook": "Built in 90 days", "caption": "c", "hashtags": ["#ai"], "scenes": [
                   {"say": "Rafael built his platform in ninety days with an AI app builder, no code at all.", "image": {"path": str(tmp / "a.png")}},
                   {"say": "Last year it did around five million dollars and this year they aim for twenty.", "image": {"path": str(tmp / "b.png")}, "label": "$5,000,000"}]}]}
        self.assertEqual(jobmod.check_job(job), [])
        bad = {"id": "s-2", "type": "story", "stories": [{"id": "01", "hook": "", "scenes": [{"say": "x"}]}]}
        self.assertGreaterEqual(len(jobmod.check_job(bad)), 4)
        self.assertTrue(any("owner's own voice" in p for p in jobmod.check_job({**job, "ownerVoice": False})))
        jp = tmp / "job.json"
        jp.write_text(json.dumps(job))
        os.environ["CLIPS_FAKE_TTS"] = "1"
        try:
            m = jobmod.run_job(jp, tmp / "work", tmp / "out")
        finally:
            del os.environ["CLIPS_FAKE_TTS"]
        self.assertEqual([f["platform"] for f in m["files"]], ["tiktok", "youtube"])
        for f in m["files"]:
            info = probe(f["out"])
            self.assertEqual((info["width"], info["height"]), (1080, 1920))
            self.assertTrue(info["audio"])
            self.assertIn("#ad", f["caption"])
        ass = (tmp / "work" / "s-1" / "01-tiktok.ass").read_text()
        self.assertIn("Style: Stat", ass)
        self.assertIn("$5,000,000", ass)
        shutil.rmtree(tmp, ignore_errors=True)


class BufferInput(unittest.TestCase):
    def test_platform_metadata(self):
        yt = post_input("youtube", "c1", "https://x.test/a.mp4", "caption #ad", "T" * 150)
        self.assertEqual(yt["metadata"]["youtube"]["title"], "T" * 100)
        self.assertIn("categoryId", yt["metadata"]["youtube"])
        self.assertFalse(yt["metadata"]["youtube"]["madeForKids"])
        ig = post_input("instagram", "c2", "https://x.test/b.mp4", "c", "t")
        self.assertEqual(ig["metadata"]["instagram"], {"type": "reel", "shouldShareToFeed": True})
        tt = post_input("tiktok", "c3", "https://x.test/c.mp4", "c", "t")
        self.assertNotIn("metadata", tt)
        self.assertEqual(tt["assets"][0]["video"]["url"], "https://x.test/c.mp4")
        self.assertEqual((tt["mode"], tt["schedulingType"]), ("addToQueue", "automatic"))


if __name__ == "__main__":
    unittest.main()
