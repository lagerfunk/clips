"""Render one vertical clip (1080x1920) from one or more moments of a source video.

- Moments are cut and joined in the given order (a re-cut structure, not one raw copy).
- Layout: a portrait source fills the frame; a landscape source is cropped around the speaker's face when faces are
  found, otherwise shown full width on a blurred copy of itself.
- Word-by-word captions (the spoken word lights up), kept above the bottom third where the app buttons sit.
- A hook line at the top, written per clip.
- Loudness normalised to -14 LUFS. Every platform gets its own render (slightly different framing, hook position
  and encode), so no two uploads are the same file.
- Optional overlays: a permanent "Werbung" label (German ad law), a lower-third naming the speaker, and an end card
  question over the last seconds. All of them stay inside the area the app buttons and labels leave free.
- Optional brand watermark (a campaign image, alpha kept) over every frame, in a fixed spot per layout that no caption
  or text overlay ever uses (watermark_box).
"""
import argparse
import bisect
import json
import math
import re
import struct
import subprocess
import tempfile
from pathlib import Path

from .common import FONT_DIR, FONT_NAME, OUT_H, OUT_W, probe, read_json, run, write_json

VARIANTS = {
    "tiktok": {"zoom": 1.00, "hook_y": 230, "cap_y": 1180, "cap_y_wide": 1215, "crf": 20, "hook_colour": "&H00FFFFFF&"},
    "youtube": {"zoom": 1.03, "hook_y": 260, "cap_y": 1150, "cap_y_wide": 1220, "crf": 21, "hook_colour": "&H0000FFFF&"},
    "instagram": {"zoom": 1.05, "hook_y": 300, "cap_y": 1210, "cap_y_wide": 1225, "crf": 19, "hook_colour": "&H00FFFFFF&"},
}
ACTIVE = "&H0000E1FF&"  # warm yellow (ASS colours are BGR)
MAX_WORDS, MAX_CHARS = 3, 16
HOOK_SIZE, HOOK_PAD = 74, 18  # hook font size and the padding of its black box (libass: line height = font size)
CAP_HALF = 60  # half the height a caption line takes at its pop-in scale, outline included
FADE = 0.04  # seconds of audio fade at each cut
CAP_SIZE, CAP_MIN, CAP_BORD = 92, 56, 7  # word caption font size (smallest for a long line) and outline in pixels

# Strips of the 1080x1920 frame that TikTok, Reels and Shorts cover with their own buttons and labels.
SAFE = {"top": 130, "right": 140, "bottom": 420}
OV_LEFT = 60  # left edge of the ad label and the lower-third boxes
AD_SIZE, AD_PAD, AD_TOP = 34, 10, SAFE["top"] + 10
LOW_TITLE, LOW_SUB, LOW_PAD, LOW_GAP = 52, 40, 12, 6
LOW_BOX_W = OUT_W - SAFE["right"] - OV_LEFT  # 880: the lower-third box never reaches under the side buttons
CAP_MAX_W = OUT_W - 2 * SAFE["right"]  # 800: centred word captions end where the right-hand buttons begin
END_SIZE, END_PAD, END_RIM, END_TEXT_W, END_Y = 60, 24, 5, 730, 800
NL = r"\N"  # ASS line break
# Brand watermark (an image, whole clip): centred, as a share of the 1080 px width. 0.74 is 800 px, the widest a centred
# image can be and still stay clear of the side buttons. "center-lower" sits just under the caption line, a strip no
# text overlay uses; "center-upper" sits just under the hook box and pushes the end card down.
WM_GAP, WM_MIN, WM_MAX, WM_UPPER_H = 20, 0.2, 0.74, 220
WM_POSITIONS = ("center-lower", "center-upper")


def _clean(text):
    return re.sub(r"[{}\\]", "", text).strip()


def _ov_text(text):
    """User text for an overlay: one line, no ASS override codes, no em dashes."""
    text = re.sub(r"\s*\u2014\s*", ", ", str(text or ""))
    return re.sub(r"\s+", " ", _clean(text)).strip(" ,")


def ass_time(t):
    cs = int(round(max(0.0, t) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _floor_cs(t):
    """Round down to the 1/100 s an ASS time can hold, so an overlay never ends after the clip."""
    return math.floor(t * 100 + 1e-6) / 100


def wrap(text, width=18, max_lines=3):
    lines, cur = [], ""
    for w in _clean(text).split():
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".,;:") + "..."
    return r"\N".join(lines)


def map_words(words, segments):
    """Words inside the chosen moments, moved onto the clip's own timeline. A word that starts at or after a cut
    belongs to what comes next and is left out."""
    out, offset = [], 0.0
    for a, b in segments:
        for w in words:
            if w["s"] >= a - 0.05 and w["e"] <= b + 0.05 and w["s"] < b - 0.02 and w["e"] > a + 0.02:
                out.append({"w": w["w"], "s": max(0.0, w["s"] - a) + offset, "e": min(b, w["e"]) - a + offset})
        offset += b - a
    return out, offset


def groups(words):
    """Split words into short caption groups (up to 3 words or 16 characters, break after punctuation)."""
    gs, cur = [], []
    for w in words:
        text = _clean(w["w"])
        if not text:
            continue
        if cur and (len(cur) >= MAX_WORDS or len(" ".join(x["t"] for x in cur)) + 1 + len(text) > MAX_CHARS):
            gs.append(cur)
            cur = []
        cur.append({"t": text, "s": w["s"], "e": w["e"]})
        if re.search(r"[.!?,;:]$", text):
            gs.append(cur)
            cur = []
    if cur:
        gs.append(cur)
    return gs


def _font_file(path):
    """(names, advance) for a .ttf/.otf file: names {1: family, 2: style, 16, 17}, advance(char) = glyph width per pixel
    of libass font size (libass makes the line, Windows ascent plus descent, as tall as the font size). None when the
    file cannot be read. Plain table reading, so the runners need no Pillow."""
    try:
        d = Path(path).read_bytes()
        if d[:4] not in (b"\x00\x01\x00\x00", b"OTTO", b"true"):
            return None
        t = {}
        for i in range(struct.unpack_from(">H", d, 4)[0]):
            tag, _, off, _ = struct.unpack_from(">4sIII", d, 12 + 16 * i)
            t[tag] = off
        if b"OS/2" in t:
            asc, desc = struct.unpack_from(">HH", d, t[b"OS/2"] + 74)
        else:
            asc, desc = struct.unpack_from(">hh", d, t[b"hhea"] + 4)
            desc = -desc
        names, nt = {}, t[b"name"]
        count, base = struct.unpack_from(">HH", d, nt + 2)
        for i in range(count):
            pid, _, lid, nid, length, off = struct.unpack_from(">6H", d, nt + 6 + 12 * i)
            if nid in (1, 2, 16, 17) and (pid, lid) in ((3, 0x409), (1, 0)) and (nid not in names or pid == 3):
                raw = d[nt + base + off: nt + base + off + length]
                names[nid] = raw.decode("utf-16-be" if pid == 3 else "latin-1", "replace")
        n_metrics = struct.unpack_from(">H", d, t[b"hhea"] + 34)[0]
        adv = struct.unpack_from(f">{2 * n_metrics}H", d, t[b"hmtx"])[0::2]
        cm, sub = t[b"cmap"], None
        for i in range(struct.unpack_from(">H", d, t[b"cmap"] + 2)[0]):
            pid, _, off = struct.unpack_from(">HHI", d, cm + 4 + 8 * i)
            if pid in (0, 3) and struct.unpack_from(">H", d, cm + off)[0] == 4:
                sub = cm + off
                break
        seg2 = struct.unpack_from(">H", d, sub + 6)[0]
        seg = seg2 // 2
        ends = struct.unpack_from(f">{seg}H", d, sub + 14)
        starts = struct.unpack_from(f">{seg}H", d, sub + 16 + seg2)
        deltas = struct.unpack_from(f">{seg}h", d, sub + 16 + 2 * seg2)
        ranges_at = sub + 16 + 3 * seg2
        ranges = struct.unpack_from(f">{seg}H", d, ranges_at)
    except (OSError, KeyError, TypeError, struct.error):
        return None
    line = float(asc + desc)
    cache = {}

    def advance(ch):
        if ch not in cache:
            c, g = ord(ch), 0
            i = bisect.bisect_left(ends, c)
            if c <= 0xFFFF and i < seg and starts[i] <= c:
                if ranges[i] == 0:
                    g = (c + deltas[i]) & 0xFFFF
                else:
                    g = struct.unpack_from(">H", d, ranges_at + 2 * i + ranges[i] + 2 * (c - starts[i]))[0]
                    g = (g + deltas[i]) & 0xFFFF if g else 0
            cache[ch] = adv[min(g, n_metrics - 1)] / line if g else 0.62
        return cache[ch]
    return names, advance


_MEASURE = {}


def _measure():
    """advance(char) for the bold caption font, with a factor for libass's fake bold when only a regular face exists;
    None when the font file is not found."""
    if "m" not in _MEASURE:
        found, regular = None, None
        key = re.sub(r"\W", "", FONT_NAME).lower()
        files = sorted((p for p in Path(FONT_DIR).rglob("*") if p.suffix.lower() in (".ttf", ".otf")),
                       key=lambda p: (not re.sub(r"\W", "", p.stem).lower().startswith(key), str(p)))[:300]
        for p in files:
            info = _font_file(p)
            if not info or FONT_NAME not in (info[0].get(1), info[0].get(16)):
                continue
            styles = (info[0].get(2), info[0].get(17))
            if "Bold" in styles:
                found = (info[1], 1.0)
                break
            if regular is None and "Regular" in styles:
                regular = (info[1], 1.05)
        _MEASURE["m"] = found or regular
    return _MEASURE["m"]


def text_width(text, size):
    """Width in pixels of bold text as libass draws it at this font size, with 2% to spare (kerning is ignored)."""
    m = _measure()
    if m is None:
        return 0.66 * size * len(text)
    advance, bold = m
    return sum(advance(ch) for ch in text) * size * bold * 1.02


def _wrap_px(words, size, max_w):
    lines, cur = [], ""
    for w in words:
        if cur and text_width(f"{cur} {w}", size) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines


def fit_text(text, size, min_size, max_w, max_lines):
    """(size, lines) for text in at most max_lines lines no wider than max_w: one line at up to 20% smaller first,
    then more lines, then down to min_size; text that still does not fit is cut with "..."."""
    words = text.split()
    for n in range(1, max_lines + 1):
        floor = min_size if n == max_lines else max(min_size, int(size * 0.8))
        for s in range(size, floor - 1, -2):
            lines = _wrap_px(words, s, max_w)
            if len(lines) <= n and all(text_width(x, s) <= max_w for x in lines):
                return s, lines
    s = min_size
    lines = _wrap_px(words, s, max_w)[:max_lines]
    last = lines[-1]
    while len(last) > 1 and text_width(last + "...", s) > max_w:
        last = last[:-1]
    lines[-1] = last.rstrip(" .,;:") + "..."
    return s, lines


def hook_box(hook, variant):
    """(top, bottom) of the hook's black box, or None without a hook."""
    if not hook:
        return None
    n = wrap(hook).count(r"\N") + 1
    return variant["hook_y"] - HOOK_PAD, variant["hook_y"] + n * HOOK_SIZE + HOOK_PAD


def _even(v):
    """Round down to an even pixel count (never past a limit it was fitted to)."""
    return max(2, int(v + 1e-6) // 2 * 2)


def watermark_box(wm, hook, variant):
    """(x0, y0, x1, y1) of the watermark image in the frame. wm = {"size": (width, height) of the image in pixels,
    "width": share of 1080 px (default 0.55), "position": "center-lower" (default) or "center-upper"}.
    The image keeps its proportions; a tall one is made smaller so it fits its strip."""
    iw, ih = wm["size"]
    frac = min(WM_MAX, max(WM_MIN, float(wm.get("width") or 0.55)))
    pos = wm.get("position") or WM_POSITIONS[0]
    if pos == "center-lower":  # between the caption line and the strip the app covers at the bottom
        top = variant["cap_y"] + CAP_HALF + WM_GAP
        max_h = OUT_H - SAFE["bottom"] - top
    elif pos == "center-upper":  # under the hook box, or under the ad label when there is no hook
        hb = hook_box(hook, variant)
        top = (hb[1] if hb else AD_TOP + AD_SIZE + 2 * AD_PAD) + WM_GAP
        max_h = WM_UPPER_H
    else:
        raise ValueError(f"watermark position must be one of {WM_POSITIONS}, not {pos!r}")
    w = frac * OUT_W
    h = w * ih / iw
    if h > max_h:
        h, w = max_h, max_h * iw / ih
    w, h = _even(w), _even(h)
    x = (OUT_W - w) // 2
    return x, top, x + w, top + h


def overlay_events(overlays, duration, hook, variant):
    """ASS events for the optional overlays, and the box each one covers ({name: (x0, y0, x1, y1, start, end)}).

    overlays = {"ad": "Werbung",
                "lower": {"title": "...", "sub": "...", "start": 0.3, "end": 4.5},
                "end": {"text": "...", "secs": 2.5},
                "watermark": {"path": "...", "size": (w, h), "width": 0.55, "position": "center-lower"}};
    every key optional. The watermark is an image laid over the finished frame by render(), not an ASS event; its box
    is here so the end card keeps clear of it."""
    overlays = overlays or {}
    events, boxes = [], {}
    clip_end = _floor_cs(duration)
    hb = hook_box(hook, variant)
    cap_top = variant["cap_y"] - CAP_HALF
    wm = overlays.get("watermark")
    if wm and wm.get("size") and clip_end > 0:
        boxes["watermark"] = (*watermark_box(wm, hook, variant), 0.0, clip_end)

    ad = overlays.get("ad")
    ad = _ov_text("Werbung" if ad is True else ad) if ad else ""
    if ad and clip_end > 0:
        size = AD_SIZE
        if hb:  # the label sits between the hidden top strip and the hook box, with room to spare
            size = max(22, min(AD_SIZE, hb[0] - 14 - AD_TOP - 2 * AD_PAD))
        size, lines = fit_text(ad, size, 22, LOW_BOX_W - 2 * AD_PAD, 1)
        x, y = OV_LEFT + AD_PAD, AD_TOP + AD_PAD
        events.append(f"Dialogue: 3,{ass_time(0)},{ass_time(clip_end)},Ad,,0,0,0,,{{\\an7\\pos({x},{y})\\fs{size}}}{lines[0]}")
        boxes["ad"] = (OV_LEFT, AD_TOP, x + text_width(lines[0], size) + AD_PAD, y + size + AD_PAD, 0.0, clip_end)

    low = overlays.get("lower") or {}
    title, sub = _ov_text(low.get("title")), _ov_text(low.get("sub"))
    start = max(0.0, float(low.get("start", 0.3) if low.get("start") is not None else 0.3))
    end = min(clip_end, float(low.get("end", 4.5) if low.get("end") is not None else 4.5))
    if (title or sub) and end - start >= 0.2:
        text_w = LOW_BOX_W - 2 * LOW_PAD
        bottom = cap_top - 24  # just above the caption line
        stack = []  # (style, size, lines), drawn bottom up
        if sub:
            stack.append(("LowerSub", *fit_text(sub, LOW_SUB, 30, text_w, 2)))
        if title:
            stack.append(("LowerTitle", *fit_text(title, LOW_TITLE, 38, text_w, 2)))
        y_bottom = bottom
        for i, (style, size, lines) in enumerate(stack):
            y_bottom -= LOW_GAP if i else 0
            x, y = OV_LEFT + LOW_PAD, y_bottom - LOW_PAD
            # slides in 30 px from the left while it fades in, fades out at the end
            events.append(f"Dialogue: 2,{ass_time(start)},{ass_time(end)},{style},,0,0,0,,"
                          f"{{\\an1\\move({x - 30},{y},{x},{y},0,200)\\fad(150,150)\\fs{size}}}{NL.join(lines)}")
            y_bottom -= len(lines) * size + 2 * LOW_PAD
        width = max(text_width(t, s) for _, s, ls in stack for t in ls)
        boxes["lower"] = (OV_LEFT, y_bottom, OV_LEFT + width + 2 * LOW_PAD, bottom, start, end)

    card = overlays.get("end") or {}
    if isinstance(card, str):
        card = {"text": card}
    text = _ov_text(card.get("text"))
    secs = float(card.get("secs") or 2.5)
    if text and secs > 0 and clip_end > 0:
        start = max(0.0, clip_end - secs)
        size, lines = fit_text(text, END_SIZE, 40, END_TEXT_W, 3)
        h = len(lines) * size + 2 * (END_PAD + END_RIM)
        lo = (hb[1] if hb else SAFE["top"]) + 30
        hi = cap_top - 30
        if "lower" in boxes and boxes["lower"][5] > start:
            hi = min(hi, boxes["lower"][1] - 30)
        wmb = boxes.get("watermark")
        if wmb and wmb[1] < cap_top:  # an upper watermark: the card goes below it
            lo = max(lo, wmb[3] + 30)
        if wmb and lo + h > hi:
            # the watermark must never be covered: rather no end card than one on top of it
            print(f"  end card left out: no room between the watermark and the text below it ({text!r})")
            return events, boxes
        if hb and not (wmb and wmb[1] < cap_top):
            # the closing question takes the hook's place for the last seconds, so faces stay clear
            floor = boxes["ad"][3] if "ad" in boxes else SAFE["top"]
            cy = max(floor + 10 + h / 2, (hb[0] + hb[1]) / 2)
        else:
            cy = min(max(END_Y, lo + h / 2), hi - h / 2) if lo + h <= hi else (lo + hi) / 2
        cy = int(round(cy))
        tags = f"\\an5\\pos({OUT_W // 2},{cy})\\fs{size}\\fad(250,0)\\fscx90\\fscy90\\t(0,250,\\fscx100\\fscy100)"
        # a black rim under the yellow card keeps it readable on yellow footage
        events.append(f"Dialogue: 2,{ass_time(start)},{ass_time(clip_end)},End,,0,0,0,,"
                      f"{{{tags}\\bord{END_PAD + END_RIM}\\3c&H000000&}}{NL.join(lines)}")
        events.append(f"Dialogue: 3,{ass_time(start)},{ass_time(clip_end)},End,,0,0,0,,{{{tags}}}{NL.join(lines)}")
        half_w = max(text_width(x, size) for x in lines) / 2 + END_PAD + END_RIM
        boxes["end"] = (OUT_W / 2 - half_w, cy - h / 2, OUT_W / 2 + half_w, cy + h / 2, start, clip_end)
    return events, boxes


def build_ass(words, duration, hook, variant, overlays=None):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{FONT_NAME},{CAP_SIZE},&H00FFFFFF&,&H00FFFFFF&,&H00000000&,&H80000000&,-1,0,0,0,100,100,0,0,1,{CAP_BORD},3,5,60,60,0,1
Style: Hook,{FONT_NAME},{HOOK_SIZE},{variant['hook_colour']},&H00FFFFFF&,&H00000000&,&HC8000000&,-1,0,0,0,100,100,0,0,3,{HOOK_PAD},0,8,80,80,{variant['hook_y']},1
Style: Ad,{FONT_NAME},{AD_SIZE},&H00FFFFFF&,&H00FFFFFF&,&H40000000&,&H00000000&,-1,0,0,0,100,100,0,0,3,{AD_PAD},0,7,0,0,0,1
Style: LowerTitle,{FONT_NAME},{LOW_TITLE},{ACTIVE},&H00FFFFFF&,&H00000000&,&H00000000&,-1,0,0,0,100,100,0,0,3,{LOW_PAD},0,1,0,0,0,1
Style: LowerSub,{FONT_NAME},{LOW_SUB},&H00FFFFFF&,&H00FFFFFF&,&H00000000&,&H00000000&,-1,0,0,0,100,100,0,0,3,{LOW_PAD},0,1,0,0,0,1
Style: End,{FONT_NAME},{END_SIZE},&H00000000&,&H00000000&,{ACTIVE},&H00000000&,-1,0,0,0,100,100,0,0,3,{END_PAD},0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines, ov_events, boxes = [], [], {}
    if overlays:
        ov_events, boxes = overlay_events(overlays, duration, hook, variant)
    if hook:
        hook_end = boxes["end"][4] if "end" in boxes else duration  # the end card replaces the hook
        lines.append(f"Dialogue: 1,{ass_time(0)},{ass_time(hook_end)},Hook,,0,0,0,,{wrap(hook)}")
    lines += ov_events
    gs = groups(words)
    x, y = OUT_W // 2, variant["cap_y"]
    for gi, g in enumerate(gs):
        g_end = max(g[-1]["e"] + 0.25, g[-1]["s"] + 0.12)
        if gi + 1 < len(gs):  # last: two caption lines never share a frame
            g_end = min(g_end, gs[gi + 1][0]["s"])
        size, pop_scale = cap_fit(" ".join(x2["t"].upper() for x2 in g))
        fs = f"\\fs{size}" if size != CAP_SIZE else ""
        for wi, w in enumerate(g):
            start = w["s"] if wi else min(w["s"], g[0]["s"])
            end = g[wi + 1]["s"] if wi + 1 < len(g) else g_end
            if end <= start:
                if wi + 1 == len(g) and gi + 1 < len(gs):
                    continue  # no time left before the next line: this word's highlight is skipped, not drawn over it
                end = start + 0.08
            parts = [(f"{{\\c{ACTIVE}}}{x2['t'].upper()}{{\\c&H00FFFFFF&}}" if k == wi else x2["t"].upper()) for k, x2 in enumerate(g)]
            pop = (f"\\fscx{pop_scale}\\fscy{pop_scale}\\t(0,90,\\fscx100\\fscy100)" if wi == 0 and pop_scale > 100 else "")
            lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Cap,,0,0,0,,{{\\pos({x},{y}){fs}{pop}}}{' '.join(parts)}")
    return head + "\n".join(lines) + "\n"


def cap_fit(text):
    """(font size, pop-in scale %) for one caption line: as big as CAP_SIZE allows while the line, outline included,
    stays inside the CAP_MAX_W centre strip (never under the like and comment buttons on the right), also at the
    moment it pops in."""
    size = CAP_SIZE
    while size > CAP_MIN and text_width(text, size) + 2 * CAP_BORD > CAP_MAX_W:
        size -= 2
    width = text_width(text, size) + 2 * CAP_BORD
    pop = max(100, min(112, int(100 * CAP_MAX_W / max(width, 1))))
    return size, pop


_TRACKS = {}


def face_track(source, segments, info, every=None):
    """{"steps": piecewise crop left edge (source pixels) on the clip timeline, "fit": spans shown whole}, or None when
    faces are not reliable. Shot by shot (camera cuts found from frame differences): a shot with the speaker's face is
    cropped around it, a shot without one is shown whole. Cached per source and moments: every platform render of a
    clip reuses the same track."""
    key = (str(source), tuple(tuple(x) for x in segments))
    if key not in _TRACKS:
        _TRACKS[key] = _face_track(source, segments, info, every)
    return _TRACKS[key]


FPS = 30
CUT_DIFF, CUT_RATIO, CUT_FLOOR = 10.0, 3.0, 1.5  # a camera cut: one frame-to-frame jump this big and this many times its neighbours
MIN_SHOT = 6        # frames (0.2 s): a shorter "shot" is a flash or a false cut and joins the one before it
FACE_EVERY = 3      # look for faces on every 3rd frame (10 a second) and on the first frame of every shot
FACE_SHARE = 0.34   # a shot is cropped around a face found in at least a third of its samples (side views are missed often)


def find_cuts(diffs):
    """Frame indexes where a new camera shot starts. diffs[k] is the mean difference between frame k-1 and k (None
    for k = 0) on a small grey thumbnail. A cut is a single-frame jump: big, and several times the frame-to-frame
    change just before and after it (a hand or head moving fast spreads its change over several frames)."""
    cuts = []
    for k in range(1, len(diffs)):
        d = diffs[k] or 0.0
        around = max(diffs[k - 1] or 0.0, (diffs[k + 1] or 0.0) if k + 1 < len(diffs) else 0.0, CUT_FLOOR)
        if d >= CUT_DIFF and d >= CUT_RATIO * around:
            cuts.append(k)
    return cuts


def shots_from_cuts(n, cuts, min_frames=MIN_SHOT):
    """[(k0, k1)] frame ranges of the shots of a moment n frames long; shots under min_frames join the one before."""
    bounds = [0] + [k for k in sorted(set(cuts)) if 0 < k < n] + [n]
    shots = []
    for k0, k1 in zip(bounds, bounds[1:]):
        if shots and (k1 - k0 < min_frames or shots[-1][1] - shots[-1][0] < min_frames):
            shots[-1] = (shots[-1][0], k1)
        else:
            shots.append((k0, k1))
    return [s for s in shots if s[1] > s[0]]


def plan_track(shots, samples, width, crop_w, fps=FPS, move=0.08, hold=2.0):
    """Crop plan for a landscape source from its shots and face samples, all on the clip timeline in frames.

    shots: [(k0, k1)]; samples: {frame: face centre x in source pixels, or None when no face was found}.
    A shot where a face shows in at least a third of the samples is cropped around that face (the median position, moving
    only when the face moves more than 8% of the width for 2 s or more); any other shot (a wide two-shot, b-roll, a
    text card) is shown whole, however short, so a crop never lands on an empty desk.
    Returns {"steps": [(seconds, crop left edge)], "fit": [(start, end) seconds shown whole]}."""
    lo, hi = crop_w / 2, width - crop_w / 2
    steps, fit = [], []
    for k0, k1 in shots:
        got = [(k, samples[k]) for k in sorted(samples) if k0 <= k < k1]
        xs = [(k, x) for k, x in got if x is not None]
        t0, t1 = k0 / fps, k1 / fps
        if not got or len(xs) < FACE_SHARE * len(got):
            # frames k0..k1-1 sit at k/fps; the window ends half a frame before the next shot's first frame
            fit.append((max(0.0, t0 - 0.5 / fps), t1 - 0.5 / fps))
            continue
        def med(vals):
            vals = sorted(vals)
            return min(hi, max(lo, vals[len(vals) // 2]))
        first = med([x for k, x in xs if k < k0 + hold * fps] or [x for _, x in xs])
        shot_steps = [(max(0.0, t0 - 0.5 / fps), first)]  # half a frame early: frame k0 itself gets the new position
        bins = {}
        for k, x in xs:
            bins.setdefault(int((k - k0) / fps), []).append(x)
        for sec in sorted(bins):
            x, t = med(bins[sec]), t0 + sec
            if abs(x - shot_steps[-1][1]) > move * width and t - shot_steps[-1][0] >= hold:
                shot_steps.append((t, x))
        steps += shot_steps
    if not steps:
        return {"steps": [], "fit": fit}
    steps[0] = (0.0, steps[0][1])
    merged = [steps[0]]
    for t, x in steps[1:]:
        if abs(x - merged[-1][1]) >= 1:
            merged.append((t, x))
    return {"steps": [(round(t, 3), x - crop_w / 2) for t, x in merged], "fit": [(round(a, 3), round(b, 3)) for a, b in fit]}


def _face_track(source, segments, info, every=None):
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    cascade_path = Path(getattr(cv2, "data", None).haarcascades if hasattr(cv2, "data") else "") / "haarcascade_frontalface_default.xml"
    if not cascade_path.exists():
        return None
    det = cv2.CascadeClassifier(str(cascade_path))
    sw = 640
    sh = int(round(sw * info["height"] / info["width"] / 2)) * 2
    size = sw * sh
    shots, samples, base, hits, total = [], {}, 0, 0, 0
    for a, b in segments:
        # the moment decoded exactly as render() cuts it (same seek, same 30 fps), 640 px wide and grey, read frame by
        # frame: every frame for the cut finder, every 3rd frame (and each cut) for the face finder
        proc = subprocess.Popen(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(source),
                                 "-vf", f"setpts=PTS-STARTPTS,fps={FPS},scale={sw}:{sh}", "-f", "rawvideo",
                                 "-pix_fmt", "gray", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        diffs, prev, k = [], None, 0
        while True:
            buf = proc.stdout.read(size)
            if len(buf) < size:
                break
            frame = np.frombuffer(buf, dtype=np.uint8).reshape(sh, sw)
            small = cv2.resize(frame, (64, 36), interpolation=cv2.INTER_AREA).astype(np.float32)
            d = float(np.mean(np.abs(small - prev))) if prev is not None else None
            diffs.append(d)
            prev = small
            if k % FACE_EVERY == 0 or (d or 0) >= CUT_DIFF:
                total += 1
                faces = det.detectMultiScale(frame, 1.1, 5, minSize=(40, 40))
                if len(faces):
                    fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])
                    samples[base + k] = (fx + fw / 2) * info["width"] / sw
                    hits += 1
                else:
                    samples[base + k] = None
            k += 1
        proc.stdout.close()
        proc.wait()
        shots += [(base + k0, base + k1) for k0, k1 in shots_from_cuts(k, find_cuts(diffs))]
        base += k  # the next moment starts where this one's frames end, as in the joined clip
    if total == 0 or hits / total < 0.4:
        return None
    return plan_track(shots, samples, info["width"], info["height"] * 9 / 16)


def no_face_spans(seen, duration, min_len=2):
    """Seconds with no face (b-roll, screenshots, text cards) as (start, end) spans of at least min_len seconds.
    Those spans are shown whole on the blurred background instead of being cropped around a face that is not there."""
    per_sec = {}
    for t, hit in seen:
        per_sec.setdefault(int(t), []).append(hit)
    secs = sorted(per_sec)
    flags = [sum(per_sec[k]) / len(per_sec[k]) >= 0.5 for k in secs]
    spans, start = [], None
    for k, ok in zip(secs + [None], flags + [True]):
        if not ok and start is None:
            start = k
        elif ok and start is not None:
            end = k if k is not None else duration
            if end - start >= min_len:
                spans.append((float(start), float(min(end, duration))))
            start = None
    return spans


def crop_expr(steps):
    expr = f"{steps[-1][1]:.0f}"
    for i in range(len(steps) - 1, 0, -1):
        expr = f"if(lt(t,{steps[i][0]}),{steps[i - 1][1]:.0f},{expr})"
    return expr


def audio_levels(source, a, b, hop=0.01, win=0.03):
    """[(seconds in the source, level in dBFS)] every hop seconds from a to b: the RMS of a win-second window around
    each point, from the source's sound mixed down to 16 kHz mono. Empty without sound."""
    import numpy as np
    a = max(0.0, a)
    if b <= a:
        return []
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(source), "-vn",
                          "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], capture_output=True).stdout
    x = np.frombuffer(raw[: len(raw) // 2 * 2], dtype=np.int16).astype(np.float64) / 32768.0
    if not len(x):
        return []
    sr = 16000
    step, half = max(1, int(sr * hop)), max(1, int(sr * win / 2))
    sq = np.concatenate([[0.0], np.cumsum(x * x)])
    out = []
    for c in range(0, len(x), step):
        i0, i1 = max(0, c - half), min(len(x), c + half)
        out.append((a + c / sr, float(10 * np.log10((sq[i1] - sq[i0]) / max(1, i1 - i0) + 1e-12))))
    return out


def image_size(path):
    """(width, height) of an image file."""
    out = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
               "-of", "json", str(path)])
    s = (json.loads(out).get("streams") or [{}])[0]
    if not s.get("width") or not s.get("height"):
        raise ValueError(f"not an image: {path}")
    return int(s["width"]), int(s["height"])


def render(source, segments, words, hook, platform, out, layout="auto", workdir=None, overlays=None):
    """overlays: optional {"ad": "Werbung", "lower": {"title", "sub", "start", "end"}, "end": {"text", "secs"},
    "watermark": {"path", "width", "position"}}, see overlay_events and watermark_box."""
    variant = VARIANTS[platform]
    info = probe(source)
    wm = (overlays or {}).get("watermark")
    if wm:
        wm_path = Path(wm["path"])
        if not wm_path.is_file():
            raise FileNotFoundError(f"watermark image not found: {wm_path}")
        overlays = {**overlays, "watermark": {**wm, "size": image_size(wm_path)}}
    segments = [(float(a), float(b)) for a, b in segments]
    for a, b in segments:
        if not (0 <= a < b <= info["duration"] + 0.01):
            raise ValueError(f"moment {a}-{b} is outside the source (0-{info['duration']:.1f})")
    clip_words, duration = map_words(words, segments)
    work = Path(workdir or tempfile.mkdtemp(prefix="clip-"))
    work.mkdir(parents=True, exist_ok=True)

    # one input per moment, opened with a seek (-ss before -i): ffmpeg jumps to the moment instead of decoding the
    # whole source up to it, which made long 4K podcasts take minutes per clip
    parts, labels, inputs = [], [], []
    for k, (a, b) in enumerate(segments):
        inputs += ["-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", str(source)]
        parts.append(f"[{k}:v]setpts=PTS-STARTPTS,fps=30[v{k}]")
        if info["audio"]:
            # a 40 ms fade in and out at every cut, so no cut clicks or chops a sound
            fd = min(FADE, (b - a) / 4)
            parts.append(f"[{k}:a]asetpts=PTS-STARTPTS,afade=t=in:st=0:d={fd:.3f},"
                         f"afade=t=out:st={max(0.0, b - a - fd):.3f}:d={fd:.3f}[a{k}]")
            labels.append(f"[v{k}][a{k}]")
        else:
            labels.append(f"[v{k}]")
    n = len(segments)
    parts.append(f"{''.join(labels)}concat=n={n}:v=1:a={1 if info['audio'] else 0}[vc]" + ("[ac]" if info["audio"] else ""))

    portrait = info["width"] / info["height"] < 0.75
    z = variant["zoom"]
    mode = layout
    track = None
    if layout == "auto":
        track = None if portrait else face_track(source, segments, info)
        mode = "fill" if portrait else ("crop" if track else "fit")
    elif layout == "crop":
        track = face_track(source, segments, info)

    def fit_chain(src, dst):
        fg_w = int(OUT_W * z) // 2 * 2
        parts.append(f"[{src}]split[bgs][fgs]")
        parts.append(f"[bgs]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},gblur=sigma=28,eq=brightness=-0.12[bg]")
        parts.append(f"[fgs]scale={fg_w}:-2[fg]")
        parts.append(f"[bg][fg]overlay=x=(W-w)/2:y=(H-h)/2-140,setsar=1[{dst}]")

    if mode == "crop":
        steps = (track or {}).get("steps") or [(0, (info["width"] - info["height"] * 9 / 16) / 2)]
        spans = (track or {}).get("fit") or []
        cw = int(info["height"] * 9 / 16) // 2 * 2
        crop = f"crop={cw}:ih:x='{crop_expr(steps)}':y=0,scale={math.ceil(OUT_W * z / 2) * 2}:{math.ceil(OUT_H * z / 2) * 2},crop={OUT_W}:{OUT_H},setsar=1"
        if spans:
            # face shots cropped around the speaker; b-roll and text cards shown whole so nothing gets cut off
            parts.append("[vc]split[cin][fin]")
            parts.append(f"[cin]{crop}[cropped]")
            fit_chain("fin", "fitted")
            on = "+".join(f"between(t,{a:.2f},{b:.2f})" for a, b in spans)
            parts.append(f"[cropped][fitted]overlay=0:0:enable='{on}'[base]")
            mode = "crop+fit"
        else:
            parts.append(f"[vc]{crop}[base]")
        print(f"  {Path(out).name}: face crop, {len(steps)} position(s), {len(spans)} b-roll span(s) shown whole")
    elif mode == "fill":
        parts.append(f"[vc]scale={OUT_W * z:.0f}:{OUT_H * z:.0f}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},setsar=1[base]")
    else:  # fit: full-width video on a blurred, darkened copy of itself
        fit_chain("vc", "base")
    # landscape sources: captions sit just under the full-width video, so they never cover it
    cap = dict(variant, cap_y=variant["cap_y"] if mode == "fill" else variant["cap_y_wide"])
    ass_path = work / f"{Path(out).stem}.ass"
    ass_path.write_text(build_ass(clip_words, duration, hook, cap, overlays), encoding="utf-8")
    wm_box = None
    if wm:
        # the brand image goes over the finished frame (captions and overlays included), for the whole clip, alpha kept;
        # its box is one no text overlay uses, so nothing covers it and it covers nothing
        wm_box = overlay_events(overlays, duration, hook, cap)[1]["watermark"][:4]
        x0, y0, x1, y1 = (int(v) for v in wm_box)
        parts.append(f"[base]ass={ass_path}:fontsdir={FONT_DIR}[subbed]")
        parts.append(f"[{len(segments)}:v]format=rgba,scale={x1 - x0}:{y1 - y0}:flags=lanczos[wm]")
        parts.append(f"[subbed][wm]overlay=x={x0}:y={y0}:eof_action=repeat:format=auto,format=yuv420p[vout]")
    else:
        parts.append(f"[base]ass={ass_path}:fontsdir={FONT_DIR}[vout]")
    if info["audio"]:
        parts.append("[ac]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")
    script = work / f"{Path(out).stem}.filter"
    script.write_text(";\n".join(parts), encoding="utf-8")

    cmd = ["ffmpeg", "-y", "-v", "error", *inputs]
    if wm:  # one still frame, repeated by the overlay; read as a single file even if its name holds a "%"
        cmd += ["-f", "image2", "-pattern_type", "none", "-i", str(wm_path)]
    cmd += ["-filter_complex_script", str(script), "-map", "[vout]"]
    if info["audio"]:
        cmd += ["-map", "[aout]", "-c:a", "aac", "-b:a", "160k"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", str(variant["crf"]), "-pix_fmt", "yuv420p", "-r", "30",
            "-movflags", "+faststart", "-metadata", f"comment=clip-{platform}", str(out)]
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    run(cmd)
    got = probe(out)
    if (got["width"], got["height"]) != (OUT_W, OUT_H) or abs(got["duration"] - duration) > 0.6:
        raise RuntimeError(f"render check failed for {out}: {got}, expected {duration:.1f}s at {OUT_W}x{OUT_H}")
    res = {"out": str(out), "platform": platform, "duration": round(got["duration"], 2), "layout": mode, "words": len(clip_words)}
    if wm_box:
        res["watermark"] = [int(v) for v in wm_box]
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("transcript")
    ap.add_argument("out")
    ap.add_argument("--seg", action="append", required=True, help="start:end in seconds, repeatable, in clip order")
    ap.add_argument("--hook", default="")
    ap.add_argument("--platform", default="tiktok", choices=list(VARIANTS))
    ap.add_argument("--layout", default="auto", choices=["auto", "fit", "crop", "fill"])
    ap.add_argument("--overlays", help='JSON, e.g. {"ad": "Werbung", "end": {"text": "Would you?"}}')
    a = ap.parse_args()
    segs = [tuple(float(x) for x in s.split(":")) for s in a.seg]
    res = render(a.source, segs, read_json(a.transcript)["words"], a.hook, a.platform, a.out, a.layout,
                 overlays=json.loads(a.overlays) if a.overlays else None)
    write_json(Path(a.out).with_suffix(".json"), res)
    print(res)


if __name__ == "__main__":
    main()
