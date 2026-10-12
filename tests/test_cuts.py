"""Cut points, camera shots and caption lines (M-C4 renderer fixes, 2026-10-12): no clip ends on the next word, no wide
shot is cropped to an empty desk, no two caption lines share a frame, no caption runs under the side buttons."""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from clips import job as jobmod
from clips import render as rendermod
from clips.render import (CAP_MAX_W, VARIANTS, build_ass, cap_fit, find_cuts, map_words, plan_track, shots_from_cuts,
                          text_width)


def times(ass, style="Cap"):
    out = []
    for line in ass.splitlines():
        if line.startswith("Dialogue:") and f",{style}," in line:
            _, start, end = line.split(",")[:3]
            out.append((start, end, line))
    return out


def secs(t):
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


class SegmentEnds(unittest.TestCase):
    def test_end_never_reaches_into_the_next_word(self):
        words = [{"w": "the", "s": 0.0, "e": 0.2}, {"w": "answer.", "s": 0.25, "e": 0.6}, {"w": "What", "s": 0.7, "e": 0.9},
                 {"w": "next?", "s": 0.95, "e": 1.3}]
        a, b = jobmod.resolve_segment(words, {"from": "the", "to": "answer."})
        self.assertLessEqual(b, 0.7 - 0.03 + 1e-9, "stops 30 ms before the next word")
        self.assertGreaterEqual(b, 0.6)
        clip, _ = map_words(words, [(a, b)])
        self.assertEqual([w["w"] for w in clip], ["the", "answer."], "no dangling next word in the captions")

    def test_start_never_reaches_into_the_word_before(self):
        words = [{"w": "so.", "s": 0.0, "e": 1.0}, {"w": "Start", "s": 1.05, "e": 1.4}, {"w": "here.", "s": 1.45, "e": 1.8}]
        a, b = jobmod.resolve_segment(words, {"from": "Start", "to": "here."})
        self.assertGreaterEqual(a, 1.0)
        self.assertLessEqual(a, 1.05)
        self.assertAlmostEqual(b, 2.1, places=6, msg="nothing after: 0.3 s of room")

    def test_word_starting_at_the_cut_is_left_out(self):
        words = [{"w": "end.", "s": 0.0, "e": 0.5}, {"w": "Huh", "s": 0.52, "e": 0.55}]
        clip, _ = map_words(words, [(0.0, 0.53)])
        self.assertEqual([w["w"] for w in clip], ["end."])


class Tighten(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="cutstest-"))
        cls.src = cls.tmp / "talk.wav"
        # speech stand-in: tone 1-2 s, silence 2-4 s, tone 4-6 s with a 60 ms gap at 5.5 s, tone to 7 s
        expr = "if(between(t,1,2)+between(t,4,5.47)+between(t,5.53,7),0.5*sin(2*PI*220*t),0)"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"aevalsrc='{expr}':s=16000:d=8",
                        str(cls.src)], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_pause_is_trimmed_to_the_sound(self):
        # the speech model stretched "one." over the pause and started "two" early
        words = [{"w": "one.", "s": 1.0, "e": 3.0}, {"w": "two", "s": 3.5, "e": 4.6}, {"w": "three.", "s": 4.6, "e": 5.45},
                 {"w": "four.", "s": 5.6, "e": 7.0}]
        segs, cap = jobmod.cut_clip(words, [{"from": "one.", "to": "one."}, {"from": "two", "to": "three."}], self.src)
        (a1, b1), (a2, b2) = segs
        self.assertAlmostEqual(b1, 2.2, delta=0.06, msg="0.2 s after the last sound, not 0.3 s after the stamped end")
        self.assertAlmostEqual(a2, 3.88, delta=0.06, msg="0.12 s before the first sound")
        self.assertAlmostEqual(b2, 5.5, delta=0.04, msg="next word close: cut in the gap")
        clip, _ = map_words(cap, segs)
        self.assertEqual([w["w"] for w in clip], ["one.", "two", "three."], "tightened words keep their captions")

    def test_no_sound_reading_keeps_the_stamped_cut(self):
        words = [{"w": "a", "s": 1.0, "e": 1.5}, {"w": "b.", "s": 1.6, "e": 1.9}]
        segs, cap = jobmod.cut_clip(words, [{"from": "a", "to": "b."}], None)
        self.assertEqual(segs, [jobmod.resolve_segment(words, {"from": "a", "to": "b."})])
        self.assertIs(cap, words)

    def test_number_segments_are_left_alone(self):
        words = [{"w": "a", "s": 1.0, "e": 1.5}]
        segs, cap = jobmod.cut_clip(words, [[0.5, 3.25]], self.src)
        self.assertEqual(segs, [(0.5, 3.25)])


class Shots(unittest.TestCase):
    def test_cut_is_a_single_frame_jump(self):
        diffs = [None, 1.0, 1.2, 40.0, 1.1, 0.9, 12.0, 14.0, 13.0, 1.0]  # a cut at 3, a fast hand at 6 to 8
        self.assertEqual(find_cuts(diffs), [3])

    def test_short_flash_joins_the_shot_before(self):
        self.assertEqual(shots_from_cuts(100, [30, 33, 60]), [(0, 33), (33, 60), (60, 100)])
        self.assertEqual(shots_from_cuts(10, []), [(0, 10)])

    def test_wide_shot_is_shown_whole_however_short(self):
        # close-up 0-2 s (face at x 1900), wide two-shot 2-2.5 s (no face found), close-up of the host 2.5-5 s
        samples = {k: (1900.0 if k < 60 else None if k < 75 else 2900.0) for k in range(0, 150, 3)}
        track = plan_track([(0, 60), (60, 75), (75, 150)], samples, 3840, 1215)
        self.assertEqual(track["fit"], [(round(60 / 30 - 1 / 60, 3), round(75 / 30 - 1 / 60, 3))])
        xs = [x + 1215 / 2 for _, x in track["steps"]]
        self.assertEqual(xs, [1900.0, 2900.0], "the host shot is cropped on the host from its first frame")
        self.assertAlmostEqual(track["steps"][1][0], 75 / 30 - 1 / 60, places=3)

    def test_face_kept_inside_the_frame(self):
        samples = {k: 100.0 for k in range(0, 60, 3)}
        track = plan_track([(0, 60)], samples, 3840, 1215)
        self.assertEqual(track["steps"], [(0.0, 0.0)], "crop never leaves the source")


class CaptionLines(unittest.TestCase):
    def test_no_two_lines_share_a_frame(self):
        # fast speech: the next line starts before the 0.12 s minimum of the last word would end
        words = [{"w": "One", "s": 0.0, "e": 0.1}, {"w": "two.", "s": 0.1, "e": 0.15}, {"w": "Three", "s": 0.2, "e": 0.4},
                 {"w": "four.", "s": 0.4, "e": 0.8}]
        caps = times(build_ass(words, 1.0, "", VARIANTS["youtube"]))
        spans = sorted((secs(s), secs(e)) for s, e, _ in caps)
        for (s1, e1), (s2, e2) in zip(spans, spans[1:]):
            self.assertLessEqual(e1, s2 + 1e-9, f"lines overlap: {spans}")

    def test_long_line_stays_left_of_the_buttons(self):
        size, pop = cap_fit("MICROMANAGEMENT.")
        self.assertLess(size, 92)
        self.assertLessEqual(text_width("MICROMANAGEMENT.", size) + 14, CAP_MAX_W)
        self.assertLessEqual((text_width("MICROMANAGEMENT.", size) + 14) * pop / 100, CAP_MAX_W + 1)
        self.assertEqual(cap_fit("SO"), (92, 112), "short lines keep the full size and pop")
        ass = build_ass([{"w": "micromanagement.", "s": 0.0, "e": 0.8}], 1.0, "", VARIANTS["youtube"])
        self.assertIn(rf"\fs{size}", ass)

    def test_every_cut_fades_the_sound(self):
        tmp = Path(tempfile.mkdtemp(prefix="fadetest-"))
        try:
            src = tmp / "s.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x568:rate=30:duration=6",
                            "-f", "lavfi", "-i", "sine=frequency=220:duration=6", "-c:v", "libx264", "-preset",
                            "ultrafast", "-c:a", "aac", "-shortest", str(src)], check=True)
            rendermod.render(src, [(0.5, 2.0), (3.0, 4.5)], [], "", "tiktok", tmp / "o.mp4", "fill", tmp / "w")
            script = (tmp / "w" / "o.filter").read_text()
            self.assertEqual(len(re.findall(r"afade=t=in", script)), 2)
            self.assertEqual(len(re.findall(r"afade=t=out", script)), 2)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
