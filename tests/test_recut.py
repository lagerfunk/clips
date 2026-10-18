"""Clips open on speech and carry no dead air (owner 2026-10-18: "the start of the clip is inaudible so people will
just scroll"); jobs may not open on a filler word."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from clips import job as jobmod
from clips import recut as rc


def curve(parts):
    """Level curve from [(seconds, dB)] pieces at the recut's 10 ms hop."""
    out = []
    for secs, db in parts:
        out += [db] * int(round(secs / rc.HOP))
    return out


class Plan(unittest.TestCase):
    def test_starts_on_speech_and_shortens_pauses(self):
        db = curve([(0.5, -80), (1.5, -20), (1.0, -80), (2.0, -20)])
        keep = rc.plan(db)
        self.assertAlmostEqual(keep[0][0], 0.47, places=2)  # 30 ms before the first sound
        self.assertEqual(len(keep), 2)
        gap = (keep[0][1] - 2.0) + (3.0 - keep[1][0])
        self.assertAlmostEqual(gap, rc.KEEP_PAUSE, places=2)  # 1 s pause left at 0.15 s
        self.assertAlmostEqual(sum(b - a for a, b in keep), 1.53 + 0.15 + 2.0, places=2)

    def test_short_gaps_between_words_stay(self):
        db = curve([(1.0, -20), (0.2, -80), (1.0, -20)])
        self.assertEqual(len(rc.plan(db)), 1)

    def test_start_moves_to_the_speech_after_the_nearest_gap(self):
        db = curve([(1.0, -20), (0.6, -80), (2.0, -20)])
        keep = rc.plan(db, start=1.5)
        self.assertAlmostEqual(keep[0][0], 1.57, places=2)


@unittest.skipUnless(shutil.which("ffmpeg"), "needs ffmpeg")
class Render(unittest.TestCase):
    def test_recut_file(self):
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d) / "in.mp4", Path(d) / "out.mp4"
            tone = r"if(between(t\,0.5\,2)+between(t\,3\,5)\,0.3*sin(2*PI*440*t)\,0)"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=gray:s=180x320:r=30:d=6",
                            "-f", "lavfi", "-i", f"aevalsrc={tone}:s=48000:d=6", "-shortest", "-c:v", "libx264",
                            "-c:a", "aac", str(src)], check=True)
            info = rc.recut(src, out)
            self.assertAlmostEqual(info["duration"], 4.69, delta=0.1)  # the closing second stays (end card)
            self.assertEqual(info["cuts"], 1)
            db = rc.levels(out)
            self.assertGreater(max(db[:8]), -40)  # sound within the first 80 ms
            with self.assertRaises(rc.TooShort):
                rc.recut(src, Path(d) / "short.mp4", min_dur=30)


class Openers(unittest.TestCase):
    def job(self, first):
        return {"id": "t-3", "sources": [{"id": "s1", "url": "x"}], "clips": [{"id": "01", "source": "s1",
                "hook": "h", "segments": [{"from": first, "to": "end."}]}]}

    def test_filler_opener_refused(self):
        for first in ("And we were chatting", "So you're saying", "Okay, so the spend", "but we also"):
            self.assertTrue(any("filler word" in p for p in jobmod.check_job(self.job(first))), first)

    def test_real_line_passes(self):
        self.assertEqual(jobmod.check_job(self.job("There are actually two incumbents")), [])


if __name__ == "__main__":
    unittest.main()
