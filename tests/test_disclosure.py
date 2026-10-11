"""German ad labelling: caption first line, brand check, on-screen overlays passed to render, manifest flags,
overlay field limits, delivery and Buffer hints. No network, no ffmpeg: fetch, probe and render are stand-ins."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from clips import job as jobmod
from clips.buffer import APP_TOGGLE, post_input, queue
from clips.common import write_json
from clips.deliver import albums

WORDS = [{"w": w, "s": i * 0.5, "e": i * 0.5 + 0.4} for i, w in enumerate(("word " * 60).split())]


def base_job(**camp):
    return {"id": "d-1", "campaign": {"name": "Lovable Clipping", "brand": "Lovable", "platforms": ["youtube", "tiktok"],
                                      "mustInclude": ["@lovable"], **camp},
            "sources": [{"id": "s1", "url": "https://example.test/a.mp4"}],
            "clips": [{"id": "01", "source": "s1", "segments": [[1, 12]], "hook": "He built it in a day",
                       "caption": "Zain shipped his app in one day.", "hashtags": ["#ai", "#nocode"]}]}


class Caption(unittest.TestCase):
    def test_first_line_is_the_german_label_with_the_brand(self):
        job = base_job()
        pt = jobmod.post_text(job, job["clips"][0])
        lines = pt["caption"].split("\n")
        self.assertEqual(lines[0], "Werbung | Paid promotion for Lovable")
        self.assertEqual(lines[1], "")
        self.assertEqual(lines[2], "Zain shipped his app in one day.")
        self.assertEqual(lines[3], "")
        self.assertEqual(lines[4], "#ai #nocode #ad @lovable", "#ad after the clip's tags, before the required ones")
        self.assertEqual(len(lines), 5)
        self.assertEqual(pt["title"], "He built it in a day", "YouTube title stays the hook")

    def test_label_without_brand_and_custom_label(self):
        job = base_job(brand="")
        self.assertEqual(jobmod.post_text(job, job["clips"][0])["caption"].split("\n")[0], "Werbung | Paid promotion")
        job = base_job(adLabel="Anzeige")
        self.assertEqual(jobmod.post_text(job, job["clips"][0])["caption"].split("\n")[0], "Anzeige | Paid promotion for Lovable")

    def test_ad_tag_is_never_the_only_label_and_not_doubled(self):
        job = base_job(mustInclude=["#ad", "@lovable"])
        cap = jobmod.post_text(job, job["clips"][0])["caption"]
        self.assertFalse(cap.startswith("#ad"))
        self.assertTrue(cap.startswith("Werbung"))
        self.assertEqual(cap.count("#ad"), 1)
        self.assertTrue(cap.endswith("#ai #nocode #ad @lovable"))

    def test_disclosure_off_has_no_label(self):
        job = base_job(disclosure=False)
        pt = jobmod.post_text(job, job["clips"][0])
        self.assertEqual(pt["caption"], "Zain shipped his app in one day.\n\n#ai #nocode @lovable")
        self.assertNotIn("#ad", pt["tags"])

    def test_long_caption_is_cut_but_label_and_tags_stay(self):
        job = base_job()
        job["clips"][0]["caption"] = "x" * 3000
        cap = jobmod.post_text(job, job["clips"][0])["caption"]
        self.assertLessEqual(len(cap), 2200)
        self.assertTrue(cap.startswith("Werbung | Paid promotion for Lovable\n\n"))
        self.assertTrue(cap.endswith("#ai #nocode #ad @lovable"))


class Checks(unittest.TestCase):
    def test_valid_job_passes(self):
        self.assertEqual(jobmod.check_job(base_job()), [])

    def test_missing_brand_is_a_problem(self):
        for camp in (base_job(brand=""), base_job(brand="  ")):
            self.assertTrue(any("campaign.brand missing" in p for p in jobmod.check_job(camp)))
        job = base_job()
        del job["campaign"]["brand"]
        self.assertTrue(any("campaign.brand missing" in p for p in jobmod.check_job(job)))
        self.assertEqual(jobmod.check_job({**job, "campaign": {**job["campaign"], "disclosure": False}}), [],
                         "unpaid posts need no brand")

    def test_bad_disclosure_overlays_and_label_values(self):
        probs = jobmod.check_job(base_job(disclosure="yes", adLabel="", overlays={"ad": "on"}))
        self.assertTrue(any("disclosure must be true or false" in p for p in probs))
        self.assertTrue(any("adLabel" in p for p in probs))
        self.assertTrue(any("campaign.overlays" in p for p in probs))
        self.assertTrue(any(p.startswith("overlays") for p in jobmod.check_job({**base_job(), "overlays": ["ad"]})))

    def clip_problems(self, **fields):
        job = base_job()
        job["clips"][0].update(fields)
        return jobmod.check_job(job)

    def test_lower_third_limits(self):
        self.assertEqual(self.clip_problems(lower={"title": "T" * 32, "sub": "S" * 40}), [])
        self.assertEqual(self.clip_problems(lower={"title": "Zain", "sub": "Founder", "start": 0, "end": 3.5}), [])
        self.assertTrue(any("lower title" in p for p in self.clip_problems(lower={"title": "T" * 33, "sub": "s"})))
        self.assertTrue(any("lower sub" in p for p in self.clip_problems(lower={"title": "t", "sub": "S" * 41})))
        self.assertTrue(any("lower title" in p for p in self.clip_problems(lower={"sub": "s"})))
        self.assertTrue(any("lower start" in p for p in self.clip_problems(lower={"title": "t", "sub": "s", "start": "1"})))
        self.assertTrue(any("lower end" in p for p in self.clip_problems(lower={"title": "t", "sub": "s", "end": -1})))
        self.assertTrue(any("lower start" in p for p in self.clip_problems(lower={"title": "t", "sub": "s", "start": True})))
        self.assertTrue(any("after its start" in p for p in self.clip_problems(lower={"title": "t", "sub": "s", "start": 4, "end": 2})))
        self.assertTrue(any("lower must be" in p for p in self.clip_problems(lower="Zain")))
        self.assertTrue(any("em dash" in p for p in self.clip_problems(lower={"title": "Zain — founder", "sub": "s"})))

    def test_end_card_limits(self):
        self.assertEqual(self.clip_problems(end="E" * 40), [])
        self.assertEqual(self.clip_problems(end={"text": "Try it free", "secs": 2.5}), [])
        self.assertEqual(self.clip_problems(end={"text": "Try it free"}), [])
        self.assertTrue(any("end card text" in p for p in self.clip_problems(end="E" * 41)))
        self.assertTrue(any("end card text" in p for p in self.clip_problems(end={"secs": 2})))
        self.assertTrue(any("end card text" in p for p in self.clip_problems(end=5)))
        self.assertTrue(any("end card secs" in p for p in self.clip_problems(end={"text": "x", "secs": 0})))
        self.assertTrue(any("end card secs" in p for p in self.clip_problems(end={"text": "x", "secs": "2"})))
        self.assertTrue(any("em dash" in p for p in self.clip_problems(end="Build — now")))

    def test_story_jobs_are_untouched(self):
        story = {"id": "s-1", "type": "story", "ownerVoice": True, "campaign": {"name": "T"},
                 "stories": [{"id": "01", "hook": "h", "scenes": [{"say": "one two three four five six seven eight nine ten "
                              "eleven twelve thirteen", "image": {}}, {"say": "fourteen fifteen sixteen seventeen eighteen "
                              "nineteen twenty twentyone twentytwo twentythree twentyfour twentyfive", "image": {}}]}]}
        self.assertEqual(jobmod.check_job(story), [], "no brand check on story jobs")


class Run(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="disclosuretest-"))
        self.calls = []

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake_render(self, source, segments, words, hook, platform, out, layout="auto", workdir=None, **kw):
        self.calls.append({"platform": platform, "kw": kw})
        return {"out": str(out), "platform": platform, "duration": 11.0, "layout": "fit", "words": 10}

    def run_job(self, job):
        write_json(self.tmp / "work" / job["id"] / "s1.words.json", {"language": "en", "words": WORDS, "segments": []})
        jp = self.tmp / "job.json"
        jp.write_text(json.dumps(job))
        media = self.tmp / "a.mp4"
        with mock.patch.object(jobmod, "fetch", return_value=[media]), \
                mock.patch.object(jobmod, "probe", return_value={"duration": 30.0}), \
                mock.patch.object(jobmod, "render", side_effect=self.fake_render):
            return jobmod.run_job(jp, self.tmp / "work", self.tmp / "out")

    def test_overlays_passed_to_render_and_manifest_flags(self):
        job = base_job()
        job["clips"].append({**job["clips"][0], "id": "02", "lower": {"title": "Zain", "sub": "Founder, Saath", "start": 0.5,
                                                                     "end": 4}, "end": "Built with Lovable"})
        job["clips"].append({**job["clips"][0], "id": "03", "end": {"text": "Try it free", "secs": 2}})
        m = self.run_job(job)
        self.assertEqual(len(self.calls), 6)
        self.assertEqual(self.calls[0]["kw"], {"overlays": {"ad": "Werbung"}})
        self.assertEqual(self.calls[2]["kw"], {"overlays": {"ad": "Werbung", "lower": {"title": "Zain", "sub": "Founder, Saath",
                                                            "start": 0.5, "end": 4}, "end": {"text": "Built with Lovable"}}})
        self.assertEqual(self.calls[4]["kw"], {"overlays": {"ad": "Werbung", "end": {"text": "Try it free", "secs": 2}}})
        want = {"label": "Werbung", "brand": "Lovable", "youtubePaidPromotion": True, "tiktokBrandedContent": True,
                "instagramPaidPartnership": True}
        self.assertEqual(len(m["files"]), 6)
        for f in m["files"]:
            self.assertEqual(f["disclosure"], want)
            self.assertTrue(f["caption"].startswith("Werbung | Paid promotion for Lovable\n\n"))
        saved = json.loads((self.tmp / "out" / "d-1" / "manifest.json").read_text())
        self.assertEqual(saved["files"][0]["disclosure"], want)

    def test_no_overlays_means_plain_render_call(self):
        job = base_job(overlays={"ad": False})
        self.run_job(job)
        self.assertTrue(self.calls)
        self.assertTrue(all(c["kw"] == {} for c in self.calls), "render is called without the overlays keyword")

    def test_job_level_overlays_win_and_disclosure_off(self):
        job = {**base_job(overlays={"ad": True}), "overlays": {"ad": False}}
        self.run_job(job)
        self.assertTrue(all(c["kw"] == {} for c in self.calls))
        self.calls.clear()
        m = self.run_job(base_job(disclosure=False))
        self.assertTrue(all(c["kw"] == {} for c in self.calls), "no ad label on screen when the post is not paid")
        self.assertTrue(all("disclosure" not in f for f in m["files"]))
        self.assertTrue(all(not f["caption"].startswith("Werbung") for f in m["files"]))


class Delivery(unittest.TestCase):
    def manifest(self, flags):
        files = [{"clip": "01", "platform": p, "out": f"/x/01-{p}.mp4", "title": "T",
                  "caption": "Werbung | Paid promotion for Lovable\n\nc\n\n#ad", **flags} for p in ("youtube", "tiktok")]
        return {"id": "d-1", "stage": "rendered", "campaign": {"name": "Lovable Clipping"}, "files": files}

    def test_album_names_the_toggles_for_paid_clips(self):
        flags = {"disclosure": {"label": "Werbung", "brand": "Lovable", "youtubePaidPromotion": True,
                                "tiktokBrandedContent": True, "instagramPaidPartnership": True}}
        text = albums(self.manifest(flags))[0]["text"]
        self.assertIn("Turn on: YouTube Paid promotion, TikTok Branded content", text)
        self.assertIn("Werbung | Paid promotion for Lovable", text)
        self.assertNotIn("Turn on:", albums(self.manifest({}))[0]["text"])

    def test_buffer_sends_no_guessed_fields_and_flags_the_hand_toggle(self):
        yt = post_input("youtube", "c1", "https://x.test/a.mp4", "Werbung | Paid promotion for Lovable", "T")
        self.assertEqual(set(yt["metadata"]["youtube"]), {"title", "categoryId", "madeForKids", "privacy"})
        self.assertNotIn("metadata", post_input("tiktok", "c3", "https://x.test/c.mp4", "c", "t"))
        tmp = Path(tempfile.mkdtemp(prefix="buffertest-"))
        try:
            mp = tmp / "manifest.json"
            m = self.manifest({"disclosure": {"label": "Werbung"}})
            write_json(mp, m)
            res = queue(mp, "https://media.test/d-1", dry_run=True)
            self.assertEqual([r["setInApp"] for r in res], [APP_TOGGLE["youtube"], APP_TOGGLE["tiktok"]])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
