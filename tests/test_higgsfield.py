"""Higgsfield x 20VC campaign support: WeTransfer links (parsing, the request, a fake opener, zip), the watermark asset
and its render in every layout, per-platform caption tags, campaign clip length limits. No network."""
import email.message
import io
import json
import shutil
import struct
import subprocess
import sys
import tempfile
import types
import unittest
import urllib.error
import zipfile
import zlib
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

import numpy as np

from clips import fetch as fetchmod
from clips import job as jobmod
from clips import render as rendermod
from clips.common import OUT_H, OUT_W, write_json
from clips.deliver import albums
from clips.fetch import (WeTransferError, direct_link, download_request, extract_video, fetch_asset, fetch_wetransfer,
                         has_alpha, kind_of, parse_wetransfer, pick_image, stream_download)
from clips.render import CAP_HALF, SAFE, VARIANTS, hook_box, overlay_events, render, watermark_box

TID = "4f9c2e1d7a8b6c5d3e2f1a0b9c8d7e6f20261011093000"
RID = "9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d20261011093001"
HASH = "a1b2c3"
DL = f"https://wetransfer.com/downloads/{TID}/{HASH}"
SHORT = "https://we.tl/t-EXAMPLE12345"
DIRECT = "https://download.wetransfer.com/eugv/abc/def/20VC_Alex_Mashrabov_full.zip?token=xyz"
PAGE = b'<html><head><meta name="csrf-token" content="tok123=="></head><body>download</body></html>'


# ---------------------------------------------------------------- fakes

def headers(**kv):
    h = email.message.Message()
    for k, v in kv.items():
        h[k.replace("_", "-")] = v
    return h


class Resp(io.BytesIO):
    def __init__(self, body=b"", status=200, url="", hdrs=None, fail_after=None):
        super().__init__(body)
        self.status, self._url, self.headers, self.fail_after = status, url, hdrs or headers(), fail_after

    def geturl(self):
        return self._url

    def read(self, n=-1):
        if self.fail_after is not None and self.tell() >= self.fail_after:
            raise ConnectionResetError("connection reset by peer")
        if self.fail_after is not None and (n < 0 or self.tell() + n > self.fail_after):
            n = self.fail_after - self.tell()
        return super().read(n)


class FakeOpener:
    """Answers requests from a list of (method, url start, answer) rules in order; records every request."""

    def __init__(self, rules):
        self.rules, self.seen = list(rules), []

    def open(self, req, timeout=None):
        self.seen.append(req)
        for i, (method, start, answer) in enumerate(self.rules):
            if req.get_method() == method and req.full_url.startswith(start):
                self.rules.pop(i)
                answer = answer(req) if callable(answer) else answer
                if isinstance(answer, Exception):
                    raise answer
                return answer
        raise AssertionError(f"unexpected request {req.get_method()} {req.full_url}")


def http_error(url, code, body=b"", hdrs=None):
    return urllib.error.HTTPError(url, code, "error", hdrs or headers(), io.BytesIO(body))


def zip_bytes(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def png(path, w, h, rows):
    """An 8-bit RGBA PNG from a list of h rows of w*4 bytes (plain zlib, no image library)."""
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + r for r in rows)
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    return Path(path)


def logo(path, w=600, h=150, b=16, clear=True):
    """Magenta frame, see-through inside (or opaque magenta everywhere when clear is False)."""
    solid, hole = bytes((255, 0, 255, 255)), bytes((255, 0, 255, 0 if clear else 255))
    full, mid = solid * w, solid * b + hole * (w - 2 * b) + solid * b
    return png(path, w, h, [full] * b + [mid] * (h - 2 * b) + [full] * b)


# ---------------------------------------------------------------- WeTransfer

class WeTransferLinks(unittest.TestCase):
    def test_wetransfer_preview_link_is_read_like_a_download_link(self):
        from clips.fetch import parse_wetransfer
        ids = parse_wetransfer("https://wetransfer.com/previews/0123456789abcdef0123456789abcdef20260101000000/f00ba7?auto_preview=true")
        self.assertEqual(ids["transfer_id"], "0123456789abcdef0123456789abcdef20260101000000")
        self.assertEqual(ids["security_hash"], "f00ba7")

    def test_kinds(self):
        self.assertEqual(kind_of(SHORT), "wetransfer")
        self.assertEqual(kind_of(DL), "wetransfer")
        self.assertEqual(kind_of(f"https://acme.wetransfer.com/downloads/{TID}/{HASH}"), "wetransfer")
        self.assertEqual(kind_of("https://drive.google.com/drive/folders/1EXAMPLEfolderIdForTests0000000000"), "drive-folder")
        self.assertEqual(kind_of("https://wetransfer.com.evil.test/downloads/x/y"), "direct")
        self.assertEqual(kind_of("https://example.test/we.tl/a.mp4"), "direct")

    def test_parse_two_and_three_parts(self):
        self.assertEqual(parse_wetransfer(DL), {"transfer_id": TID, "security_hash": HASH, "recipient_id": None})
        self.assertEqual(parse_wetransfer(DL + "?t_exp=1760000000&t_lsid=abc&t_network=link&utm_source=x"),
                         {"transfer_id": TID, "security_hash": HASH, "recipient_id": None})
        self.assertEqual(parse_wetransfer(DL + "/"), parse_wetransfer(DL))
        want = {"transfer_id": TID, "security_hash": HASH, "recipient_id": RID}
        self.assertEqual(parse_wetransfer(f"https://wetransfer.com/downloads/{TID}/{RID}/{HASH}"), want, "transferwee order")
        self.assertEqual(parse_wetransfer(f"https://wetransfer.com/downloads/{TID}/{HASH}/{RID}"), want, "hash first")
        for bad in ("https://wetransfer.com/", f"https://wetransfer.com/downloads/{TID}",
                    f"https://wetransfer.com/downloads/{TID}/a/b/c", "https://wetransfer.com/downloads/x/y%22z"):
            with self.assertRaises(WeTransferError, msg=bad):
                parse_wetransfer(bad)

    def test_download_request(self):
        req = download_request(parse_wetransfer(DL), "tok123==", DL)
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.full_url, f"https://wetransfer.com/api/v4/transfers/{TID}/download")
        self.assertEqual(json.loads(req.data), {"security_hash": HASH, "intent": "entire_transfer"})
        h = {k.lower(): v for k, v in req.header_items()}
        self.assertEqual(h["x-csrf-token"], "tok123==")
        self.assertEqual(h["x-requested-with"], "XMLHttpRequest")
        self.assertEqual(h["content-type"], "application/json")
        self.assertEqual(h["referer"], DL)
        req = download_request(parse_wetransfer(f"https://wetransfer.com/downloads/{TID}/{RID}/{HASH}"))
        self.assertEqual(json.loads(req.data), {"security_hash": HASH, "intent": "entire_transfer", "recipient_id": RID})
        self.assertNotIn("x-csrf-token", {k.lower() for k, _ in req.header_items()})

    def test_short_link_then_api(self):
        op = FakeOpener([("GET", SHORT, Resp(PAGE, url=DL + "?t_exp=1")),
                         ("POST", f"https://wetransfer.com/api/v4/transfers/{TID}/download",
                          Resp(json.dumps({"direct_link": DIRECT}).encode()))])
        self.assertEqual(direct_link(SHORT, op), DIRECT)
        post = op.seen[-1]
        self.assertEqual(json.loads(post.data), {"security_hash": HASH, "intent": "entire_transfer"})
        self.assertEqual(dict((k.lower(), v) for k, v in post.header_items())["x-csrf-token"], "tok123==")
        self.assertEqual(len(op.seen), 2, "token found on the download page, home page not needed")

    def test_token_from_home_page_or_none(self):
        api = f"https://wetransfer.com/api/v4/transfers/{TID}/download"
        op = FakeOpener([("GET", DL, Resp(b"<html>no token</html>", url=DL)),
                         ("GET", "https://wetransfer.com/", Resp(b'<meta content="home-tok" name="csrf-token">')),
                         ("POST", api, Resp(json.dumps({"direct_link": DIRECT}).encode()))])
        self.assertEqual(direct_link(DL, op), DIRECT)
        self.assertEqual(dict((k.lower(), v) for k, v in op.seen[-1].header_items())["x-csrf-token"], "home-tok")
        op = FakeOpener([("GET", DL, Resp(b"<html></html>", url=DL)), ("GET", "https://wetransfer.com/", Resp(b"")),
                         ("POST", api, Resp(json.dumps({"direct_link": DIRECT}).encode()))])
        self.assertEqual(direct_link(DL, op), DIRECT, "no token anywhere: try without, as transferwee does")

    def test_captcha_is_never_bypassed(self):
        api = f"https://wetransfer.com/api/v4/transfers/{TID}/download"
        page_block = FakeOpener([("GET", SHORT, http_error(DL, 403, b"<title>Just a moment...</title>",
                                                           headers(cf_mitigated="challenge")))])
        api_block = FakeOpener([("GET", DL, Resp(PAGE, url=DL)),
                                ("POST", api, http_error(api, 403, b'{"error":"captcha_required"}'))])
        for op, url in ((page_block, SHORT), (api_block, DL)):
            with self.assertRaises(WeTransferError) as cm:
                direct_link(url, op)
            msg = str(cm.exception)
            self.assertIn("captcha", msg)
            self.assertIn("not bypassed", msg)
            self.assertIn("re-upload it to Google Drive", msg)
            self.assertFalse([r for r in op.seen if "captcha" in r.full_url or "recaptcha" in r.full_url])
        ok_page = PAGE.replace(b"download", b'<script src="https://www.google.com/recaptcha/api.js"></script>')
        op = FakeOpener([("GET", DL, Resp(ok_page, url=DL)), ("POST", api, Resp(json.dumps({"direct_link": DIRECT}).encode()))])
        self.assertEqual(direct_link(DL, op), DIRECT, "a captcha script on a working page is not a block")

    def test_expired_or_wrong_link(self):
        api = f"https://wetransfer.com/api/v4/transfers/{TID}/download"
        op = FakeOpener([("GET", DL, Resp(PAGE, url=DL)),
                         ("POST", api, http_error(api, 404, b'{"message":"This transfer has expired"}'))])
        with self.assertRaises(WeTransferError) as cm:
            direct_link(DL, op)
        self.assertIn("HTTP 404: This transfer has expired", str(cm.exception))
        self.assertIn("Google Drive", str(cm.exception))
        op = FakeOpener([("GET", SHORT, Resp(b"<html>gone</html>", url="https://wetransfer.com/"))])
        with self.assertRaises(WeTransferError) as cm:
            direct_link(SHORT, op)
        self.assertIn("not to a download page", str(cm.exception))
        op = FakeOpener([("GET", DL, Resp(PAGE, url=DL)), ("POST", api, Resp(b""))])
        with self.assertRaises(WeTransferError) as cm:
            direct_link(DL, op)
        self.assertIn("HTTP 200: no direct_link in the answer", str(cm.exception))


class WeTransferDownload(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wttest-"))
        self.api = f"https://wetransfer.com/api/v4/transfers/{TID}/download"
        self.sleep = mock.patch.object(fetchmod, "_sleep", lambda s: None)
        self.sleep.start()
        self.quiet = redirect_stdout(io.StringIO())
        self.quiet.__enter__()

    def tearDown(self):
        self.quiet.__exit__(None, None, None)
        self.sleep.stop()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def rules(self, body, name="20VC_Alex_Mashrabov_full.zip"):
        cd = headers(Content_Length=str(len(body)), Content_Disposition=f'attachment; filename="{name}"')
        return [("GET", SHORT, Resp(PAGE, url=DL)),
                ("POST", self.api, Resp(json.dumps({"direct_link": DIRECT}).encode())),
                ("GET", DIRECT, Resp(body, hdrs=cd))]

    def test_zip_keeps_the_largest_video_and_reuses_it(self):
        z = zip_bytes({"20VC/trailer.mp4": b"t" * 100, "20VC/Full Episode (4K).mov": b"f" * 5000,
                       "__MACOSX/20VC/._Full Episode (4K).mov": b"x" * 9000, "20VC/notes.txt": b"n" * 8000})
        op = FakeOpener(self.rules(z))
        got = fetch_wetransfer(SHORT, self.tmp / "s1", opener=op)
        self.assertEqual(got.name, "Full Episode (4K).mov")
        self.assertEqual(got.read_bytes(), b"f" * 5000)
        self.assertEqual(sorted(p.name for p in (self.tmp / "s1").iterdir()), [".wetransfer.json", "Full Episode (4K).mov"],
                         "the zip is deleted after extraction")
        again = fetch_wetransfer(SHORT, self.tmp / "s1", opener=FakeOpener([]))
        self.assertEqual(again, got, "a finished download is reused")
        op = FakeOpener(self.rules(z))
        self.assertEqual(fetch_wetransfer(SHORT, self.tmp / "s2", want="trailer.mp4", opener=op).name, "trailer.mp4")

    def test_single_video_and_fetch_dispatch(self):
        op = FakeOpener(self.rules(b"v" * 300, name="episode.mp4"))
        with mock.patch.object(fetchmod, "make_opener", return_value=op):
            files = fetchmod.fetch(SHORT, self.tmp / "s1")
        self.assertEqual([f.name for f in files], ["episode.mp4"])
        op = FakeOpener(self.rules(b"%PDF", name="brief.pdf"))
        with self.assertRaises(WeTransferError) as cm:
            fetch_wetransfer(SHORT, self.tmp / "s3", opener=op)
        self.assertIn("neither a zip nor a video", str(cm.exception))

    def test_zip_without_video(self):
        arc = self.tmp / "a.zip"
        arc.write_bytes(zip_bytes({"logo.png": b"p", "brief.pdf": b"d"}))
        with self.assertRaises(WeTransferError) as cm:
            extract_video(arc, self.tmp)
        self.assertIn("no video file", str(cm.exception))
        self.assertIn("logo.png", str(cm.exception))

    def test_dropped_connection_resumes_with_range(self):
        body = bytes(range(256)) * 40
        first = Resp(body, hdrs=headers(Content_Length=str(len(body))), fail_after=4000)

        def second(req):
            self.assertEqual(req.get_header("Range"), "bytes=4000-")
            return Resp(body[4000:], status=206, hdrs=headers(Content_Range=f"bytes 4000-{len(body) - 1}/{len(body)}"))
        out = io.StringIO()
        with redirect_stdout(out):
            got = stream_download("https://download.wetransfer.com/x/episode.mp4?sig=1", self.tmp,
                                  FakeOpener([("GET", "https://download.wetransfer.com/", first),
                                              ("GET", "https://download.wetransfer.com/", second)]))
        self.assertEqual(got.read_bytes(), body)
        self.assertIn("attempt 1 of 3", out.getvalue())
        short = Resp(body[:100], hdrs=headers(Content_Length=str(len(body))))
        never = [("GET", "https://download.wetransfer.com/", short)] + [
            ("GET", "https://download.wetransfer.com/", Resp(b"", status=206, hdrs=headers(Content_Range="bytes 100-/9999")))
            for _ in range(2)]
        with redirect_stdout(io.StringIO()), self.assertRaises(WeTransferError) as cm:
            stream_download("https://download.wetransfer.com/x/e.mp4", self.tmp / "", FakeOpener(never))
        self.assertIn("kept failing", str(cm.exception))


# ---------------------------------------------------------------- watermark asset

class WatermarkAsset(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="wmtest-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_pick_png_with_transparency(self):
        d = self.tmp / "folder"
        d.mkdir()
        opaque = logo(d / "a_banner.png", 60, 20, 4, clear=False)
        clear = logo(d / "b_watermark.png", 60, 20, 4)
        subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=40x20", "-frames:v", "1",
                        str(d / "0_photo.jpg")], check=True)
        self.assertFalse(has_alpha(opaque), "an alpha channel with no see-through pixel does not count")
        self.assertTrue(has_alpha(clear))
        self.assertFalse(has_alpha(d / "0_photo.jpg"))
        files = list(d.iterdir())
        self.assertEqual(pick_image(files, "png").name, "b_watermark.png")
        self.assertEqual(pick_image([opaque, d / "0_photo.jpg"], "png").name, "0_photo.jpg", "else the first image")
        self.assertEqual(pick_image(files, "a_banner.png"), opaque)
        self.assertEqual(pick_image(files, "WATERMARK"), clear, "a part of the name, case ignored")
        self.assertIsNone(pick_image(files, "missing.png"))

    def test_local_folder_fetched_once(self):
        src = self.tmp / "brand"
        src.mkdir()
        logo(src / "higgsfield.png", 60, 20, 4)
        dest = self.tmp / "work" / "assets" / "watermark"
        got = fetch_asset(str(src), dest)
        self.assertEqual(got, dest / "higgsfield.png")
        (src / "higgsfield.png").write_bytes(b"changed")
        self.assertEqual(fetch_asset(str(src), dest).read_bytes()[:4], b"\x89PNG", "fetched once, then reused")
        with self.assertRaises(RuntimeError):
            fetch_asset(str(src), dest, "nothing-like-this")

    def test_drive_folder_downloads_only_images(self):
        Item = types.SimpleNamespace
        calls = []

        def download_folder(url, output, quiet, skip_download):
            self.assertTrue(skip_download)
            return [Item(id="v1", path="Higgsfield/reference.mp4", local_path=f"{output}/Higgsfield/reference.mp4"),
                    Item(id="p1", path="Higgsfield/Higgsfield_watermark.png", local_path=f"{output}/Higgsfield/Higgsfield_watermark.png")]

        def download(id, output, quiet):
            calls.append(id)
            logo(output, 60, 20, 4)
            return output
        fake = types.SimpleNamespace(download_folder=download_folder, download=download)
        url = "https://drive.google.com/drive/folders/1EXAMPLEfolderIdForTests0000000000"
        with mock.patch.dict(sys.modules, {"gdown": fake}):
            got = fetch_asset(url, self.tmp / "wm")
            self.assertEqual(got.name, "Higgsfield_watermark.png")
            self.assertEqual(calls, ["p1"], "the reference video in the folder is not downloaded")
            fetch_asset(url, self.tmp / "wm")
            self.assertEqual(calls, ["p1"], "second call reuses the stored file")


# ---------------------------------------------------------------- render

OV = {"ad": "Werbung",
      "lower": {"title": "Alex Mashrabov", "sub": "Founder and CEO, Higgsfield AI", "start": 0.3, "end": 4.5},
      "end": {"text": "Would you build it again?", "secs": 2.5}}
HOOKS = ("", "Snap paid $166M for his first startup", "He sold to Snap for $166M, then started over from zero at 30")


def overlap(a, b):
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


class WatermarkPlacement(unittest.TestCase):
    def test_never_covered_and_inside_the_safe_area(self):
        with redirect_stdout(io.StringIO()):  # a dropped end card prints a note
            self._placement()

    def _placement(self):
        # a 30 s clip; the long lower-third stays up to the end, under the end card's time, the hardest case
        long_lower = {**OV, "lower": {"title": "Alexander Mashrabov, Higgsfield", "sub": "Sold his first company to Snap",
                                      "start": 0.3, "end": 30.0}}
        for p in VARIANTS:
            for wide in (False, True):
                v = dict(VARIANTS[p], cap_y=VARIANTS[p]["cap_y_wide"] if wide else VARIANTS[p]["cap_y"])
                cap = (0, v["cap_y"] - CAP_HALF, OUT_W, v["cap_y"] + CAP_HALF)
                for hook in HOOKS:
                    hb = hook_box(hook, v)
                    for size in ((1200, 240), (800, 800), (300, 900), (2000, 200)):
                        for pos in ("center-lower", "center-upper"):
                            for ov in (OV, long_lower):
                                wm = {"path": "x.png", "size": size, "width": 0.55, "position": pos}
                                _, boxes = overlay_events({**ov, "watermark": wm}, 30.0, hook, v)
                                b = boxes["watermark"]
                                msg = f"{p} wide={wide} hook={hook!r} size={size} {pos} wm={b[:4]}"
                                self.assertEqual(b[4:], (0.0, 30.0), "the whole clip")
                                self.assertGreaterEqual(b[0], 0, msg)
                                self.assertGreaterEqual(b[1], SAFE["top"], msg)
                                self.assertLessEqual(b[2], OUT_W - SAFE["right"], msg)
                                self.assertLessEqual(b[3], OUT_H - SAFE["bottom"], msg)
                                self.assertAlmostEqual((b[0] + b[2]) / 2, OUT_W / 2, delta=1, msg=msg)
                                self.assertFalse(overlap(b, cap), "captions: " + msg)
                                if hb:
                                    self.assertFalse(overlap(b, (0, hb[0], OUT_W, hb[1])), "hook: " + msg)
                                for name in ("ad", "lower", "end"):
                                    if name in boxes:
                                        self.assertFalse(overlap(b, boxes[name]), f"{name}: " + msg)
                                if ov is OV:
                                    self.assertIn("end", boxes, "the end card still fits: " + msg)

    def test_size_follows_width_share(self):
        v = VARIANTS["instagram"]
        x0, y0, x1, y1 = watermark_box({"size": (1200, 240)}, "Hook", v)
        self.assertEqual((x1 - x0, y1 - y0), (594, 118), "0.55 of 1080 px wide, proportions kept")
        self.assertEqual(y0, v["cap_y"] + CAP_HALF + 20, "just under the caption line")
        x0, _, x1, _ = watermark_box({"size": (1200, 240), "width": 0.9}, "", v)
        self.assertLessEqual(x1, OUT_W - SAFE["right"], "capped clear of the side buttons")
        _, y0, _, y1 = watermark_box({"size": (800, 800)}, "", v)
        self.assertLessEqual(y1, OUT_H - SAFE["bottom"], "a square logo is made smaller to fit its strip")
        with self.assertRaises(ValueError):
            watermark_box({"size": (10, 10), "position": "top-left"}, "", v)


def rgb_frame(path, t):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t}", "-i", str(path), "-frames:v", "1", "-f", "rawvideo",
                          "-pix_fmt", "rgb24", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(OUT_H, OUT_W, 3).astype(int)


def magenta(img):
    return (img[..., 0] > 170) & (img[..., 1] < 100) & (img[..., 2] > 170)


class WatermarkRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="wmrender-"))
        cls.logo = logo(cls.tmp / "Higgsfield 100% logo.png")  # a "%" in the name must not read as an image sequence
        for name, size in (("land", "1280x720"), ("port", "720x1280")):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x204060:s={size}:rate=30:duration=5",
                            "-f", "lavfi", "-i", "sine=frequency=220:duration=5", "-c:v", "libx264", "-preset", "ultrafast",
                            "-c:a", "aac", str(cls.tmp / f"{name}.mp4")], check=True)
        cls.words = [{"w": w, "s": 0.6 + i * 0.35, "e": 0.9 + i * 0.35}
                     for i, w in enumerate("Snap paid for it and then he started again from zero".split())]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_every_layout_shows_the_watermark_on_every_frame(self):
        ov = {**OV, "end": {"text": "Would you build it again?", "secs": 1.0},
              "watermark": {"path": str(self.logo), "width": 0.55, "position": "center-lower"}}
        cases = (("fit", "land", "youtube", "fit", "fit"), ("fill", "port", "instagram", "fill", "fill"),
                 ("crop", "land", "instagram", "crop", "crop"), ("cropfit", "land", "youtube", "auto", "crop+fit"))
        for name, src, platform, layout, expect in cases:
            source = self.tmp / f"{src}.mp4"
            key = (str(source), ((0.5, 3.5),))
            if expect == "crop+fit":
                rendermod._TRACKS[key] = {"steps": [(0, 100.0), (2, 500.0)], "fit": [(1.0, 2.5)]}
            out = self.tmp / f"{name}.mp4"
            try:
                with redirect_stdout(io.StringIO()):
                    res = render(source, [(0.5, 3.5)], self.words, HOOKS[1], platform, out, layout, self.tmp / "w", ov)
            finally:
                rendermod._TRACKS.pop(key, None)
            self.assertEqual(res["layout"], expect)
            x0, y0, x1, y1 = res["watermark"]
            v = dict(VARIANTS[platform], cap_y=VARIANTS[platform]["cap_y" if expect == "fill" else "cap_y_wide"])
            self.assertEqual(tuple(res["watermark"]), watermark_box({"size": (600, 150)}, HOOKS[1], v), name)
            for t in (0.0, 1.6, 2.9):  # first frame, middle (lower-third and captions up), under the end card
                img = rgb_frame(out, t)
                m = magenta(img)
                self.assertGreater(m[y0 + 4:y0 + 12, x0 + 40:x1 - 40].mean(), 0.9, f"{name} at {t}s: frame visible")
                self.assertGreater(m[y0 + 20:y1 - 20, x0 + 4:x0 + 12].mean(), 0.9, f"{name} at {t}s: left edge")
                self.assertLess(m[y0 + 40:y1 - 40, x0 + 60:x1 - 60].mean(), 0.02, f"{name} at {t}s: alpha kept")
                outside = m.copy()
                outside[y0 - 2:y1 + 2, x0 - 2:x1 + 2] = False
                self.assertEqual(int(outside.sum()), 0, f"{name} at {t}s: nothing magenta outside its box")
            ass = (self.tmp / "w" / f"{name}.ass").read_text()
            self.assertIn("Style: End,", ass)
            self.assertIn("Werbung", ass)


# ---------------------------------------------------------------- captions and length

WORDS = [{"w": w, "s": i * 0.5, "e": i * 0.5 + 0.4} for i, w in enumerate(
    ("intro " * 10 + "Snap paid us a lot. " + "middle " * 100 + "We started again from zero. " + "outro " * 10).split())]


def hf_job(**camp):
    return {"id": "hf-1",
            "campaign": {"name": "Higgsfield 20VC Clipping", "brand": "Higgsfield", "platforms": ["youtube", "instagram"],
                         "tagsByPlatform": {"youtube": ["@HiggsfieldAI", "@20VC"], "instagram": ["@higgsfield.ai", "@20vchq"]},
                         "minSecs": 30, "maxSecs": 60, **camp},
            "assets": {"watermark": {"url": "https://drive.google.com/drive/folders/1EXAMPLEfolderIdForTests0000000000",
                                     "pick": "png"}},
            "sources": [{"id": "s1", "url": "https://we.tl/t-EXAMPLE12345"}],
            "clips": [{"id": "01", "source": "s1", "segments": [[10, 55]], "hook": "Snap paid $166M for his first startup",
                       "caption": "Alex Mashrabov on starting over after Snap.", "hashtags": ["#ai", "#founders"]}]}


class Captions(unittest.TestCase):
    def test_tags_per_platform(self):
        job = hf_job()
        clip = job["clips"][0]
        yt = jobmod.post_text(job, clip, "youtube")["caption"].split("\n")
        ig = jobmod.post_text(job, clip, "instagram")["caption"].split("\n")
        self.assertEqual(yt[0], "Werbung | Paid promotion for Higgsfield")
        self.assertEqual(ig[0], "Werbung | Paid promotion for Higgsfield")
        self.assertEqual(yt[-1], "#ai #founders #ad @HiggsfieldAI @20VC")
        self.assertEqual(ig[-1], "#ai #founders #ad @higgsfield.ai @20vchq")
        self.assertEqual(jobmod.post_text(job, clip, "youtube")["tags"], ["#ai", "#founders", "#ad", "@HiggsfieldAI", "@20VC"])
        self.assertEqual(jobmod.post_text(job, clip)["caption"].split("\n")[-1], "#ai #founders #ad", "no platform, no tags")
        self.assertEqual(jobmod.post_text(job, clip, "tiktok")["caption"].split("\n")[-1], "#ai #founders #ad")
        job["campaign"]["mustInclude"] = ["@20VC"]
        self.assertEqual(jobmod.post_text(job, clip, "youtube")["caption"].count("@20VC"), 1, "not doubled")
        job = hf_job(disclosure=False)
        self.assertEqual(jobmod.post_text(job, clip, "instagram")["caption"],
                         "Alex Mashrabov on starting over after Snap.\n\n#ai #founders @higgsfield.ai @20vchq")

    def test_tag_and_asset_checks(self):
        self.assertEqual(jobmod.check_job(hf_job()), [])
        probs = jobmod.check_job(hf_job(tagsByPlatform={"youtube": ["@Higgsfield AI"], "facebook": ["@x"]}))
        self.assertTrue(any("tagsByPlatform.youtube" in p for p in probs), probs)
        self.assertTrue(any("unknown platform 'facebook'" in p for p in probs), probs)
        self.assertTrue(any("no entry for instagram" in p for p in probs), probs)
        self.assertTrue(any("tagsByPlatform must" in p for p in jobmod.check_job(hf_job(tagsByPlatform=["@x"]))))
        self.assertEqual(jobmod.check_job(hf_job(tagsByPlatform={"youtube": [], "instagram": []})), [])
        job = hf_job()
        job["assets"] = {"watermark": {"url": "", "width": 0.9}}
        self.assertTrue(any("needs a \"url\"" in p for p in jobmod.check_job(job)))
        job["assets"] = {"watermark": {"url": "https://x.test/w.png", "width": 0.9, "position": "top"}}
        probs = jobmod.check_job(job)
        self.assertTrue(any("width" in p for p in probs) and any("position" in p for p in probs), probs)
        job["assets"] = {"logo": {}}
        self.assertTrue(any(p.startswith("assets must") for p in jobmod.check_job(job)))


class Length(unittest.TestCase):
    def clip_problems(self, segs, **camp):
        job = hf_job(**camp)
        job["clips"][0]["segments"] = segs
        return jobmod.check_job(job)

    def test_number_segments_checked_up_front(self):
        self.assertEqual(self.clip_problems([[10, 40]]), [])
        self.assertEqual(self.clip_problems([[10, 70]]), [])
        self.assertEqual(self.clip_problems([[0, 20], [30, 40]]), [], "30 s in two moments")
        self.assertTrue(any("20.0s long, keep it between 30 and 60s" in p for p in self.clip_problems([[10, 30]])))
        self.assertTrue(any("61.0s long" in p for p in self.clip_problems([[10, 71]])))
        self.assertEqual(self.clip_problems([{"from": "Snap paid", "to": "zero."}]), [], "text: checked at run time")
        self.assertTrue(any("campaign.minSecs must be" in p for p in self.clip_problems([[10, 40]], minSecs="30")))
        self.assertTrue(any("must be below" in p for p in self.clip_problems([[10, 40]], minSecs=60, maxSecs=30)))
        job = hf_job()
        del job["campaign"]["minSecs"], job["campaign"]["maxSecs"]
        job["clips"][0]["segments"] = [[0, 5]]
        self.assertTrue(any("between 8 and 90s" in p for p in jobmod.check_job(job)), "defaults stay 8 to 90 s")


class Run(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="hfrun-"))
        self.calls = []
        self.wm = logo(self.tmp / "wm.png", 60, 20, 4)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def fake_render(self, source, segments, words, hook, platform, out, layout="auto", workdir=None, **kw):
        self.calls.append({"platform": platform, "segments": segments, "kw": kw})
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(b"mp4")
        return {"out": str(out), "platform": platform, "duration": 40.0, "layout": "crop", "words": 10}

    def run_job(self, job, asset=None):
        write_json(self.tmp / "work" / job["id"] / "s1.words.json", {"language": "en", "words": WORDS, "segments": []})
        jp = self.tmp / "job.json"
        jp.write_text(json.dumps(job))
        out = io.StringIO()
        with mock.patch.object(jobmod, "fetch", return_value=[self.tmp / "a.mp4"]) as f, \
                mock.patch.object(jobmod, "fetch_asset", side_effect=asset or (lambda url, dest, pick: self.wm)) as fa, \
                mock.patch.object(jobmod, "probe", return_value={"duration": 120.0}), \
                mock.patch.object(jobmod, "render", side_effect=self.fake_render), redirect_stdout(out):
            try:
                return jobmod.run_job(jp, self.tmp / "work", self.tmp / "out"), out.getvalue(), f, fa
            except SystemExit as e:
                return e, out.getvalue(), f, fa

    def test_watermark_on_every_clip_and_captions_per_platform(self):
        job = hf_job()
        job["clips"].append({**job["clips"][0], "id": "02", "segments": [[60, 100]], "end": "Would you sell to Snap?"})
        m, log, f, fa = self.run_job(job)
        self.assertEqual(fa.call_count, 1, "fetched once per job")
        self.assertEqual(fa.call_args[0][1], self.tmp / "work" / "hf-1" / "assets" / "watermark")
        self.assertEqual(f.call_args[1], {"want": None})
        self.assertEqual(len(self.calls), 4)
        for c in self.calls:
            self.assertEqual(c["kw"]["overlays"]["watermark"], {"path": str(self.wm), "width": 0.55, "position": "center-lower"})
            self.assertEqual(c["kw"]["overlays"]["ad"], "Werbung")
        self.assertIn("watermark: wm.png", log)
        by = {(e["clip"], e["platform"]): e for e in m["files"]}
        self.assertTrue(by[("01", "youtube")]["caption"].endswith("@HiggsfieldAI @20VC"))
        self.assertTrue(by[("01", "instagram")]["caption"].endswith("@higgsfield.ai @20vchq"))
        self.assertNotIn("@20vchq", by[("01", "youtube")]["caption"])
        saved = json.loads((self.tmp / "out" / "hf-1" / "manifest.json").read_text())
        self.assertEqual(saved["files"][1]["caption"], by[("01", "instagram")]["caption"])
        text = albums(m)[0]["text"]
        self.assertIn("YouTube Shorts:\nWerbung | Paid promotion for Higgsfield", text)
        self.assertIn("Instagram Reels:\nWerbung | Paid promotion for Higgsfield", text)
        self.assertLessEqual(len(text), 1024)

    def test_text_clip_out_of_range_fails_alone(self):
        job = hf_job()
        job["clips"] = [
            {**job["clips"][0], "id": "short", "segments": [{"from": "Snap paid", "to": "a lot."}]},
            {**job["clips"][0], "id": "ok", "segments": [{"from": "Snap paid", "to": "from zero."}]},
            {**job["clips"][0], "id": "missing", "segments": [{"from": "never said", "to": "zero."}]},
        ]
        m, log, _, _ = self.run_job(job)
        self.assertEqual(m["stage"], "rendered")
        self.assertEqual({e["clip"] for e in m["files"]}, {"ok"})
        self.assertEqual(set(m["failedClips"]), {"short", "missing"})
        self.assertIn("the campaign takes 30 to 60s", m["failedClips"]["short"])
        self.assertIn("start text not found", m["failedClips"]["missing"])
        self.assertIn("ERROR clip short failed", log)
        self.assertIn("ERROR clip missing failed", log)
        self.assertEqual({c["platform"] for c in self.calls}, {"youtube", "instagram"})
        self.assertTrue(all(c["kw"]["overlays"]["watermark"] for c in self.calls))
        with mock.patch.dict("os.environ", {"GITHUB_ACTIONS": "true"}):
            _, log, _, _ = self.run_job(job)
        self.assertIn("::error title=clip short failed::", log)

    def test_all_clips_failed_exits_with_a_failed_manifest(self):
        job = hf_job()
        job["clips"][0]["segments"] = [{"from": "Snap paid", "to": "a lot."}]  # 3.5 s: under 30 s
        res, log, _, _ = self.run_job(job)
        self.assertIsInstance(res, SystemExit)
        saved = json.loads((self.tmp / "out" / "hf-1" / "manifest.json").read_text())
        self.assertEqual(saved["stage"], "failed")
        self.assertIn("01", saved["failedClips"])
        self.assertEqual(self.calls, [])

    def test_partial_render_is_removed(self):
        job = hf_job()
        real = self.fake_render

        def flaky(source, segments, words, hook, platform, out, *a, **kw):
            if platform == "instagram":
                raise RuntimeError("command failed (ffmpeg): boom")
            return real(source, segments, words, hook, platform, out, *a, **kw)
        self.fake_render = flaky
        job["clips"].append({**job["clips"][0], "id": "02"})
        res, log, _, _ = self.run_job(job)
        self.assertIsInstance(res, SystemExit, "every clip failed on instagram")
        self.assertFalse(list((self.tmp / "out" / "hf-1").glob("*.mp4")), "no half-rendered clip is left")
        self.assertIn("boom", log)

    def test_watermark_fetch_failure_stops_before_the_source(self):
        def fail(url, dest, pick):
            raise RuntimeError("Drive folder is not public")
        res, log, f, _ = self.run_job(hf_job(), asset=fail)
        self.assertIsInstance(res, SystemExit)
        self.assertIn("watermark is required", str(res))
        self.assertEqual(f.call_count, 0, "the long WeTransfer download never starts")
        self.assertEqual(self.calls, [])
        saved = json.loads((self.tmp / "out" / "hf-1" / "manifest.json").read_text())
        self.assertEqual(saved, {"id": "hf-1", "stage": "failed", "failed": {"watermark": "Drive folder is not public"}})

    def test_no_watermark_asset_changes_nothing(self):
        job = hf_job()
        del job["assets"]
        m, _, _, fa = self.run_job(job)
        self.assertEqual(fa.call_count, 0)
        self.assertTrue(all("watermark" not in c["kw"]["overlays"] for c in self.calls))
        self.assertNotIn("failedClips", m)


if __name__ == "__main__":
    unittest.main()
