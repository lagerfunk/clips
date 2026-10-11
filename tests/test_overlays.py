"""Overlay tests: ad label, lower-third and end card in the ASS file, their placement, and a real render of each layout."""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import numpy as np

from clips import render as rendermod
from clips.common import OUT_H, OUT_W, probe
from clips.render import (CAP_HALF, SAFE, VARIANTS, _ov_text, ass_time, build_ass, hook_box, overlay_events,
                          render, text_width)

OV = {"ad": "Werbung",
      "lower": {"title": "Zain, founder of Saath", "sub": "Turned down $250K at 23", "start": 0.3, "end": 4.5},
      "end": {"text": "Would you have taken the money?", "secs": 2.5}}
OV_STYLES = ("Ad", "LowerTitle", "LowerSub", "End")
HOOKS = ("", "Nobody tells you this", "He sold to Snap, then started again from zero at 30")


def words(n=40, step=0.4):
    return [{"w": w, "s": round(1.0 + i * step, 2), "e": round(1.0 + i * step + 0.3, 2)}
            for i, w in enumerate((["Nobody", "tells", "you", "this", "about", "money."] * 10)[:n])]


def secs(stamp):
    h, m, s = stamp.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def events(ass):
    """[(layer, style, start, end, text)] for every Dialogue line."""
    out = []
    for line in ass.splitlines():
        if line.startswith("Dialogue:"):
            layer, start, end, style, _, _, _, _, _, text = line[len("Dialogue: "):].split(",", 9)
            out.append((int(layer), style, secs(start), secs(end), text))
    return out


def overlay_only(ass):
    return [e for e in events(ass) if e[1] in OV_STYLES]


def variant(platform, wide):
    v = VARIANTS[platform]
    return dict(v, cap_y=v["cap_y_wide"] if wide else v["cap_y"])


def overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


class OverlayAss(unittest.TestCase):
    def test_styles_and_event_times(self):
        ass = build_ass(words(), 10.0, "Nobody tells you this", VARIANTS["tiktok"], OV)
        for s in OV_STYLES:
            self.assertIn(f"Style: {s},", ass)
        title_style = next(x for x in ass.splitlines() if x.startswith("Style: LowerTitle,")).split(",")
        sub_style = next(x for x in ass.splitlines() if x.startswith("Style: LowerSub,")).split(",")
        self.assertEqual(title_style[3], "&H0000E1FF&", "title line is #FFE100")
        self.assertEqual(sub_style[3], "&H00FFFFFF&", "sub line is white")
        ad_style = next(x for x in ass.splitlines() if x.startswith("Style: Ad,")).split(",")
        self.assertEqual(ad_style[3], "&H00FFFFFF&")
        self.assertNotIn(ad_style[5][2:4], ("00", "FF"), "ad box is semi-opaque, neither solid nor invisible")
        ev = overlay_only(ass)
        by = {}
        for _, style, a, b, text in ev:
            by.setdefault(style, []).append((a, b, text))
        self.assertEqual(by["Ad"], [(0.0, 10.0, by["Ad"][0][2])])
        self.assertTrue(by["Ad"][0][2].endswith("Werbung"))
        self.assertEqual([(a, b) for a, b, _ in by["LowerTitle"]], [(0.3, 4.5)])
        self.assertEqual([(a, b) for a, b, _ in by["LowerSub"]], [(0.3, 4.5)])
        self.assertIn(r"\fad(150,150)", by["LowerTitle"][0][2])
        self.assertTrue(all((a, b) == (7.5, 10.0) for a, b, _ in by["End"]))
        self.assertIn(r"\fad(250,0)", by["End"][0][2])
        self.assertTrue(by["End"][-1][2].endswith(r"Would you have taken\Nthe money?"), by["End"][-1][2])
        self.assertNotIn("\u2014", ass)

    def test_defaults_and_custom_times(self):
        ass = build_ass([], 20.0, "", VARIANTS["youtube"], {"lower": {"title": "Zain"}, "end": {"text": "Would you?"}})
        ev = overlay_only(ass)
        self.assertEqual([(s, a, b) for _, s, a, b, _ in ev if s == "LowerTitle"], [("LowerTitle", 0.3, 4.5)])
        self.assertEqual({(a, b) for _, s, a, b, _ in ev if s == "End"}, {(17.5, 20.0)})
        self.assertFalse([e for e in ev if e[1] in ("Ad", "LowerSub")], "keys left out add nothing")
        ass = build_ass([], 20.0, "", VARIANTS["youtube"], {"lower": {"sub": "only a sub", "start": 2, "end": 6.25},
                                                            "end": {"text": "x", "secs": 4}, "ad": True})
        ev = overlay_only(ass)
        self.assertEqual([(a, b) for _, s, a, b, _ in ev if s == "LowerSub"], [(2.0, 6.25)])
        self.assertEqual({(a, b) for _, s, a, b, _ in ev if s == "End"}, {(16.0, 20.0)})
        self.assertTrue(next(e for e in ev if e[1] == "Ad")[4].endswith("Werbung"), "ad: true means Werbung")

    def test_no_overlays_changes_nothing(self):
        v = VARIANTS["instagram"]
        base = build_ass(words(), 8.0, "Nobody tells you this", v)
        self.assertEqual(base, build_ass(words(), 8.0, "Nobody tells you this", v, None))
        self.assertEqual(base, build_ass(words(), 8.0, "Nobody tells you this", v, {}))
        self.assertEqual(overlay_only(base), [])
        self.assertIn("\n\n[Events]", base, "story.py inserts its Stat style before this marker")

    def test_text_escaping(self):
        ov = {"ad": "Wer{bung}\\", "lower": {"title": "{\\fs200}Zain\\N \u2014 founder", "sub": "line\nbreak {x}\r\n"},
              "end": {"text": "Really?\\h {\\c&HFF&} \u2014 sure"}}
        ass = build_ass([], 9.0, "", VARIANTS["tiktok"], ov)
        ev = overlay_only(ass)
        self.assertEqual(len(ev), 5, "ad, title, sub, end rim and end card; a newline in the text adds no event")
        for _, style, _, _, text in ev:
            self.assertTrue(text.startswith("{"))
            body = text[text.index("}") + 1:]
            self.assertNotRegex(body, r"[{}]", f"{style}: no override block survives")
            self.assertEqual(body.replace(r"\N", ""), body.replace(r"\N", "").replace("\\", ""), f"{style}: only our own line breaks")
        self.assertNotIn("\u2014", ass, "no em dashes")
        self.assertEqual(_ov_text("Zain \u2014 founder"), "Zain, founder")
        self.assertEqual(_ov_text("{\\b1}Zain\\N\n of {Saath}"), "b1ZainN of Saath")
        self.assertEqual(len([x for x in ass.splitlines() if x.startswith("Dialogue:")]), 5)

    def test_no_overlay_event_extends_past_duration(self):
        self.assertEqual(ass_time(59.996), "0:01:00.00")
        self.assertEqual(ass_time(3723.456), "1:02:03.46")
        ov = {"ad": "Werbung", "lower": {"title": "T", "sub": "S", "start": 0.3, "end": 100}, "end": {"text": "Q?", "secs": 2.5}}
        for d in (0.5, 1.999, 3.237, 4.4, 10.0, 59.996, 61.5):
            for p in VARIANTS:
                ev = overlay_only(build_ass(words(), d, "Hook here", VARIANTS[p], ov))
                self.assertTrue(ev)
                for _, style, a, b, _ in ev:
                    self.assertLessEqual(b, d, f"{style} ends at {b} after the clip ({d})")
                    self.assertTrue(0 <= a < b, f"{style} {a}-{b}")
        ev = overlay_only(build_ass([], 3.0, "", VARIANTS["tiktok"], {"lower": {"title": "late", "start": 5}}))
        self.assertEqual(ev, [], "a lower-third that starts after the clip is dropped")

    def test_placement_safe_area_and_no_overlap(self):
        long_ov = {"ad": "Werbung", "lower": {"title": "Alexander Mashrabov, founder and CEO of Higgsfield AI",
                                              "sub": "Sold his first company to Snap for $166M and then started over"},
                   "end": {"text": "Would you sell your company to Snap for $166M or keep building it yourself?", "secs": 3}}
        right, bottom = OUT_W - SAFE["right"], OUT_H - SAFE["bottom"]
        for p in VARIANTS:
            for wide in (False, True):
                v = variant(p, wide)
                cap = (0, v["cap_y"] - CAP_HALF, OUT_W, v["cap_y"] + CAP_HALF)
                for hook in HOOKS:
                    for ov in (OV, long_ov):
                        _, boxes = overlay_events(ov, 6.0, hook, v)
                        self.assertEqual(set(boxes), {"ad", "lower", "end"})
                        hb = hook_box(hook, v)
                        hook_rect = (0, hb[0], OUT_W, hb[1]) if hb else None
                        for name, b in boxes.items():
                            msg = f"{p} wide={wide} hook={hook!r} {name} {tuple(round(x) for x in b[:4])}"
                            self.assertGreaterEqual(b[0], 0, msg)
                            self.assertGreaterEqual(b[1], SAFE["top"], msg)
                            self.assertLessEqual(b[2], right, msg)
                            self.assertLessEqual(b[3], bottom, msg)
                            self.assertFalse(overlap(b, cap), "covers the captions: " + msg)
                            if hook_rect and name != "end":  # the end card replaces the hook for the last seconds
                                self.assertFalse(overlap(b, hook_rect), "covers the hook: " + msg)
                        self.assertLessEqual(boxes["lower"][3], v["cap_y"] - CAP_HALF - 10, "lower-third sits above the captions")
                        self.assertLessEqual(boxes["lower"][2] - boxes["lower"][0], 900)
                        self.assertEqual(boxes["lower"][0], 60, "left-aligned, 60 px in")
                        self.assertFalse(overlap(boxes["end"], boxes["lower"]), "end card and lower-third meet: " + msg)
                        self.assertFalse(overlap(boxes["end"], boxes["ad"]))
                        self.assertLess(boxes["end"][1], OUT_H / 2, "end card sits in the upper middle")
                        if hook:
                            ass = build_ass([], 6.0, hook, v, ov)
                            hook_line = next(x for x in ass.splitlines() if ",Hook,," in x and x.startswith("Dialogue"))
                            self.assertEqual(hook_line.split(",")[2], ass_time(boxes["end"][4]), "hook gives way to the end card")

    def test_long_text_wraps_or_shrinks_to_fit(self):
        _, boxes = overlay_events({"lower": {"title": "W" * 40}}, 6.0, "", VARIANTS["tiktok"])
        self.assertLessEqual(boxes["lower"][2], OUT_W - SAFE["right"], "one unbreakable word is cut, not run off the frame")
        self.assertAlmostEqual(text_width("HHHHHHHHHH", 100), 719 * 1.02, delta=8, msg="matches libass for DejaVu Sans Bold")


def frame(path, t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t}", "-i", str(path), "-frames:v", "1", "-f", "rawvideo",
                          "-pix_fmt", "gray", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(OUT_H, OUT_W).astype(int)


class OverlayRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="overlaytest-"))
        cls.src = cls.tmp / "src.mp4"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30:duration=7",
                        "-f", "lavfi", "-i", "sine=frequency=220:duration=7", "-c:v", "libx264", "-preset", "ultrafast",
                        "-c:a", "aac", str(cls.src)], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def go(self, name, platform, layout, overlays):
        out = self.tmp / f"{name}.mp4"
        res = render(self.src, [(1.0, 5.0)], words(), "Nobody tells you this", platform, out, layout, self.tmp / "w", overlays)
        info = probe(out)
        self.assertEqual((info["width"], info["height"]), (OUT_W, OUT_H))
        self.assertAlmostEqual(info["duration"], 4.0, delta=0.5)
        return out, res

    def test_overlays_show_up_in_the_frame(self):
        plain, _ = self.go("plain", "tiktok", "fit", None)
        with_ov, res = self.go("ov", "tiktok", "fit", OV)
        a, b = frame(plain, 1.0), frame(with_ov, 1.0)
        _, boxes = overlay_events(OV, 4.0, "Nobody tells you this", variant("tiktok", True))
        for name in ("ad", "lower"):
            x0, y0, x1, y1 = (int(v) for v in boxes[name][:4])
            self.assertGreater(np.abs(a[y0:y1, x0:x1] - b[y0:y1, x0:x1]).mean(), 20, f"{name} is visible at 1.0 s")
        self.assertLess(np.abs(a[1500:, :] - b[1500:, :]).mean(), 4, "nothing else moves")
        last_a, last_b = frame(plain, 3.6), frame(with_ov, 3.6)
        x0, y0, x1, y1 = (int(v) for v in boxes["end"][:4])
        self.assertGreater(np.abs(last_a[y0:y1, x0:x1] - last_b[y0:y1, x0:x1]).mean(), 20, "end card is visible at the end")
        ass = (self.tmp / "w" / "ov.ass").read_text()
        self.assertTrue(overlay_only(ass))

    def test_every_layout_renders_with_overlays(self):
        for name, platform, layout, expect in (("fill", "tiktok", "fill", "fill"), ("crop", "instagram", "crop", "crop"),
                                               ("cropfit", "youtube", "auto", "crop+fit")):
            key = (str(self.src), ((1.0, 5.0),))
            if expect == "crop+fit":
                rendermod._TRACKS[key] = {"steps": [(0, 100.0), (2, 500.0)], "fit": [(1.0, 3.0)]}
            try:
                _, res = self.go(name, platform, layout, OV)
            finally:
                rendermod._TRACKS.pop(key, None)
            self.assertEqual(res["layout"], expect)
            ass = (self.tmp / "w" / f"{name}.ass").read_text()
            self.assertEqual({e[1] for e in overlay_only(ass)}, set(OV_STYLES))


if __name__ == "__main__":
    unittest.main()
