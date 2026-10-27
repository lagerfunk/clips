"""Captions, sound and edit list for the Florida episodes (fl01 .. fl05), straight from scripts/gta/episodes.json.

    import fl01_uspost as P;  P.main("fl02", sys.argv[1])    -> OUTDIR/flNN_<lang>.ass, audio_flNN.wav, flNN_edit.json

Canonical timeline = the English segment order (HOOK, SITUATION, RULE, COST, CORRECT, END), which is also the order
the scene renders. Each language's captions are placed on that timeline (segment start + rel_t0), so kit/finish_ep.py
burns them in and kit/edit.py then cuts the segments into the language's own order. Numbers: only through
scripts/gta/facts_us.py and only for VERIFIED keys; a caption whose placeholder or req key is not VERIFIED shows its
fallback, an empty fallback shows nothing. No voice, no music: the sound is synthesised (kit/sfx.py plus the new cues
air_brake, toll_beep, siren_short and amb_road defined here)."""
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DL = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(DL, "kit"), os.path.join(DL, "scripts", "gta")]
import numpy as np  # noqa: E402

import facts_us as FU  # noqa: E402
import overlay as O  # noqa: E402
import sfx  # noqa: E402

EPISODES = os.path.join(DL, "scripts", "gta", "episodes.json")
PH = re.compile(r"\{(fine|val|pts):([a-z0-9_]+)\}")
US_RED, US_WHITE, US_BLUE = "&H00341EB2&", "&H00FFFFFF&", "&H00683C3C&"     # BGR
US_FLAG = (US_RED, US_WHITE, US_BLUE)    # kept for reference only: overlay.chip_events draws three bands (a Dutch
#                                          look), so the chip is drawn by us_chip below as stripes plus a canton
COUNTRY = {"en": "FLORIDA", "de": "FLORIDA", "fr": "FLORIDE"}
STYLE = {  # kind: (default y_top, size)
    "hook": (390, 70), "body": (560, 70), "sub": (470, 54), "rule": (560, 72), "slam": (520, 120),
    "step": (560, 64), "end": (520, 92), "end2": (760, 54)}


def release():
    d = json.load(open(EPISODES, encoding="utf-8"))
    by = {e["slug"]: e for e in d["episodes"]}
    return [by[r["slug"]] for r in d["release_plan"]]


def episode(code):
    """code 'fl01'..'fl05': release order (scripts/gta/episodes.json release_plan)."""
    return release()[int(code[2:]) - 1]


def canon(e):
    """Canonical segment spans (the English order) as {seg: (start, end)}."""
    sp = e["segment_order"]["en"]["spans"]
    assert [s["seg"] for s in sp] == [s["id"] for s in e["segments"]], "EN order must be the render order"
    return {s["seg"]: (s["start"], s["end"]) for s in sp}


def resolve(text, D, lang, used):
    """Replace placeholders; None if any key is not VERIFIED."""
    out = text
    for kind, key in PH.findall(text):
        if not D.ok(key):
            return None
        v = {"fine": D.fine, "val": D.val, "pts": D.points}[kind](key, lang)
        if v is None:
            return None
        used.add(key)
        out = out.replace("{%s:%s}" % (kind, key), v)
    return out


def lines_of(c, D, lang, used):
    """Resolved caption lines (list) or [] when nothing is shown."""
    if any(not D.ok(k) for k in c.get("req") or []):
        return [ln for ln in c.get("fb_lines") or []]
    res = [resolve(ln, D, lang, used) for ln in c["lines"]]
    if any(r is None for r in res):
        return [ln for ln in c.get("fb_lines") or []]
    used.update(c.get("req") or [])
    out = []
    for raw, r in zip(c["lines"], res):
        out += O.wrap(r, 26) if PH.search(raw) else [r]
    return out


def captions(e, lang, D=None):
    """[(t0, t1, kind, y, lines, keys)] on the canonical timeline; fine cards as kind 'fine' with lines =
    (lead, amount, extra)."""
    return timed(e, lang, D)[0]


def timed(e, lang, D=None):
    """captions() plus the time map tm(t) of this language (canonical time -> time used), which the icons follow.

    Two rules on top of the episode file (QA round 6):
    - The hook owns the start of the segment that opens this language. Captions of that segment that would come up
      before the hook has left are moved, keeping their order and proportions, into [hook end + 0.1, their last end];
      captions that already start after the hook are untouched. So no two caption groups share the screen.
    - A caption may run past the end of its segment (step 2 of fl02 runs from the green light into the end card) only
      where this language plays the canonically next segment next; elsewhere it is clipped at the segment end."""
    D = D or FU.load()
    raw = _captions(e, lang, D)
    cs = canon(e)
    h = e["hooks"][lang]
    s0, s1 = cs[h["seg"]]
    h1 = s0 + h["rel_t1"]
    body = [c for c in raw if c[2] != "hook" and s0 <= c[0] < s1]
    late = [c for c in body if c[0] < h1 + 0.05]
    tm = (lambda t: t)
    if late:
        a = min(c[0] for c in late)
        b = max(c[1] for c in body if c[0] >= a)
        na = round(h1 + 0.1, 2)
        k = (b - na) / (b - a)
        tm = (lambda t: round(na + (t - a) * k, 2) if a <= t <= b else t)
    order = [s["seg"] for s in e["segment_order"][lang]["spans"]]
    canon_order = list(cs)
    out = []
    for c in raw:
        t0, t1 = c[0], c[1]
        if c[2] != "hook" and s0 <= t0 < s1:
            t0, t1 = tm(t0), tm(t1)
        seg = [s for s, (x0, x1) in cs.items() if x0 <= c[0] + 1e-6 < x1][0]
        if t1 > cs[seg][1] + 1e-6:
            i = order.index(seg)
            nxt = order[i + 1] if i + 1 < len(order) else None
            cnx = canon_order[canon_order.index(seg) + 1] if seg != canon_order[-1] else None
            if nxt is None or nxt != cnx:
                t1 = cs[seg][1]
        out.append((t0, t1) + tuple(c[2:]))
    return out, tm


def _captions(e, lang, D):
    cs = canon(e)
    out = []
    h = e["hooks"][lang]
    s0 = cs[h["seg"]][0]
    out.append((s0 + h["rel_t0"], s0 + h["rel_t1"], "hook", h.get("y", 390), h["lines"], set()))
    for c in e["captions"][lang]:
        a = cs[c["seg"]][0]
        t0, t1 = a + c["rel_t0"], a + c["rel_t1"]
        used = set()
        if c["kind"] == "fine":
            f = c["fine"]
            amt = resolve(f["amount"], D, lang, used)
            lead = [resolve(x, D, lang, used) for x in f["lead_lines"]]
            if amt is None or any(x is None for x in lead):
                fb = c.get("fb_lines") or []
                if fb:
                    out.append((t0, t1, "body", c.get("y", 640), fb, set()))
                continue
            extra = [resolve(x, D, lang, used) for x in f.get("extra", [])]
            out.append((t0, t1, "fine", c.get("y", 640), (lead, amt, [x for x in extra if x]), used))
            continue
        ls = lines_of(c, D, lang, used)
        if ls:
            out.append((t0, t1, c["kind"], c.get("y"), ls, used))
    return out


def build(code, lang, D=None):
    e = episode(code)
    T = e["duration_s"]
    o = O.Overlay(f"FL{int(code[2:])}", COUNTRY[lang], e["end_card"][lang], T)
    us_chip(o, chip_spans(e, lang))
    caps, tm = timed(e, lang, D)
    cards = []                                   # (t0, t1, bottom y of the red amount box) of every fine card
    for t0, t1, kind, y, ls, _k in caps:
        if kind == "fine":
            lead, amt, extra = ls
            cards.append((t0, t1, o.fine(t0, t1, lead, amt, extra, y_top=y)))
    for t0, t1, kind, y, ls, _k in caps:
        if kind == "fine":
            continue
        if kind == "note":
            # below the box of the card(s) up while the note shows, never on it (QA r6 fl02 DE)
            under = [b for a0, a1, b in cards if a0 < t1 and t0 < a1]
            yy = round(max(under)) + 12 if under else 800
            o.block(t0, t1, ls, yy, size=54, max_size=54, room=140, anim=O.POP)
        elif kind == "foot":
            foot(o, t0, t1, ls[0])
        else:
            y0, size = STYLE.get(kind, (560, 66))
            o.block(t0, t1, ls, y if y is not None else y0, size=size, max_size=size, room=300,
                    anim=O.SLAM if kind == "slam" else O.POP)
    if code in ICONS:
        ICONS[code](o, canon(e), tm)
    return o.text()


def chip_spans(e, lang):
    """[(t0, t1, fade)] on the canonical timeline for the chip: the segment that opens this language's cut fades the
    chip in (its canonical start is 0.0 of the cut), every other span shows it solid. The spans touch, so the chip
    never drops out or fades again where kit/edit.py joins two segments (QA r9: DE/FR joins into HOOK)."""
    cs = canon(e)
    T = e["duration_s"]
    a, b = cs[e["segment_order"][lang]["order"][0]]
    return [(t0, t1, f) for t0, t1, f in ((0.0, a, False), (a, b, True), (b, T, False)) if t1 - t0 > 1e-6]


def us_chip(o, spans=None):
    """Series chip with a simplified US flag in the 64 x 48 flag box of overlay.chip_events (x 100..164, y 302..350):
    seven red and white stripes and a blue canton over the top four, no stars (too small to read). The text part is
    the same event chip_events writes, so the chip looks like every other episode's. spans: chip_spans(e, lang)."""
    x, y, h, w = O.CHIP_X, O.CHIP_Y, O.CHIP_H, 64
    ch = round(4 * h / 7)
    for t0, t1, fade in spans or [(0.0, o.T, True)]:
        fd, a, b = ("\\fad(200,0)" if fade else ""), O.ts(t0), O.ts(t1)
        for k in range(7):
            y0, y1 = round(k * h / 7), round((k + 1) * h / 7)
            o.ev.append(f"Dialogue: 2,{a},{b},Box,,0,0,0,,{{\\pos({x},{y + y0})\\an7\\bord0\\shad0"
                        f"\\1c{US_RED if k % 2 == 0 else US_WHITE}{fd}\\p1}}m 0 0 l {w} 0 {w} {y1 - y0} 0 {y1 - y0}{{\\p0}}")
        o.ev.append(f"Dialogue: 3,{a},{b},Box,,0,0,0,,{{\\pos({x},{y})\\an7\\bord0\\shad0"
                    f"\\1c{US_BLUE}{fd}\\p1}}m 0 0 l 28 0 28 {ch} 0 {ch}{{\\p0}}")
        o.ev.append(f"Dialogue: 1,{a},{b},Box,,0,0,0,,{{\\pos({x + 76},{y + 10})\\an7\\fs28{fd}}}"
                    f"DRIVE LIKE A LOCAL  {{\\c&H0000C8FF&}}#{o.number}  {o.country}")


def foot(o, t0, t1, text):
    """End-card source line, readable at 1080 x 1920: split at ' · ' into two lines (date, then source), each about
    44 px, centred at y 1415 and 1463 (ink inside y 1500). A footer without the separator stays one line."""
    parts = text.split(" · ", 1)
    size = min(46, min(O.fit(46, p_, 860, 0.6) for p_ in parts))
    for k, p_ in enumerate(parts):
        yy = 1463 - (len(parts) - 1 - k) * round(size * 1.1)
        o.add(t0, t1, "Foot", O.X0, yy, p_, size, "\\bord5\\shad2\\fad(200,0)", layer=4)


# ------------------------------------------------------------------ flat icons (ASS drawings, no text, no clip art)
# Every shape is drawn here from plain geometry: no picture, no font glyph, no logo. They sit below the captions
# (y 950..1480) inside the safe zone and are the same in every language.
WHITE, GREY, LIGHT, DARK = "&H00FFFFFF&", "&H00A8A8A8&", "&H00D8D8D8&", "&H00302A26&"
RED, GREEN, AMBER, ORANGE, YELLOW = "&H002A1FE0&", "&H0050C81E&", "&H0000B4FF&", "&H000080FF&", "&H0000DCFF&"
FADE = "\\fad(120,160)"
NUM = re.compile(r"-?\d+(?:\.\d+)?")


def shp(o, t0, t1, x, y, path, col, extra=FADE, layer=3, move=None):
    """One flat shape. path: ASS drawing commands in pixels relative to (x, y). The drawing is shifted so its own
    top-left is (0, 0) and its position shifted to match, so every renderer places it the same way. move:
    (dx, dy, ms0, ms1) slides the shape by (dx, dy) between ms0 and ms1 milliseconds."""
    vals = [float(v) for v in NUM.findall(path)]
    mx, my = min(vals[0::2]), min(vals[1::2])
    it = iter(range(len(vals)))
    path = NUM.sub(lambda m_: "%d" % round(float(m_.group()) - (mx if next(it) % 2 == 0 else my)), path)
    px, py = x + mx, y + my
    where = (f"\\move({px:.0f},{py:.0f},{px + move[0]:.0f},{py + move[1]:.0f},{move[2]},{move[3]})" if move else
             f"\\pos({px:.0f},{py:.0f})")
    o.ev.append(f"Dialogue: {layer},{O.ts(t0)},{O.ts(t1)},Cap,,0,0,0,,{{{where}\\an7\\bord0\\shad0\\1c{col}{extra}"
                f"\\p1}}{path}{{\\p0}}")


def poly_path(pts):
    return "m " + " l ".join(f"{px:.0f} {py:.0f}" for px, py in pts)


def rect(x0, y0, x1, y1):
    return poly_path([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])


def rot_rect(cx, cy, w, h, ang):
    a = math.radians(ang)
    c_, s_ = math.cos(a), math.sin(a)
    return poly_path([(cx + px * c_ - py * s_, cy + px * s_ + py * c_)
                      for px, py in ((-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2))])


def circle(cx, cy, r):
    k = 0.5523 * r
    return (f"m {cx + r:.0f} {cy:.0f} b {cx + r:.0f} {cy + k:.0f} {cx + k:.0f} {cy + r:.0f} {cx:.0f} {cy + r:.0f} "
            f"b {cx - k:.0f} {cy + r:.0f} {cx - r:.0f} {cy + k:.0f} {cx - r:.0f} {cy:.0f} "
            f"b {cx - r:.0f} {cy - k:.0f} {cx - k:.0f} {cy - r:.0f} {cx:.0f} {cy - r:.0f} "
            f"b {cx + k:.0f} {cy - r:.0f} {cx + r:.0f} {cy - k:.0f} {cx + r:.0f} {cy:.0f}")


def arc_band(cx, cy, r0, r1, a0, a1, n=18):
    """Ring sector between radii r0 < r1 from angle a0 to a1 (degrees, 0 = right, counter-clockwise on screen)."""
    out = [(cx + r1 * math.cos(math.radians(a0 + (a1 - a0) * k / n)),
            cy - r1 * math.sin(math.radians(a0 + (a1 - a0) * k / n))) for k in range(n + 1)]
    out += [(cx + r0 * math.cos(math.radians(a1 - (a1 - a0) * k / n)),
             cy - r0 * math.sin(math.radians(a1 - (a1 - a0) * k / n))) for k in range(n + 1)]
    return poly_path(out)


def sheet(o, t0, t1, x, y, head, move=None, layer=3):
    """Flat paper sheet 180 x 236 with its top-left at (x, y): header bar in `head`, five grey line bars."""
    shp(o, t0, t1, x, y, rect(0, 0, 180, 236), WHITE, FADE, layer, move)
    shp(o, t0, t1, x, y, rect(0, 0, 180, 40), head, FADE, layer + 1, move)
    for k in range(5):
        shp(o, t0, t1, x, y, rect(25, 70 + 30 * k, 155 if k < 4 else 105, 82 + 30 * k), GREY, FADE, layer + 1, move)


def tick(o, t0, t1, x, y, layer=6):
    shp(o, t0, t1, x, y, poly_path([(0, 76), (30, 46), (62, 78), (140, 0), (170, 30), (62, 138)]), GREEN,
        "\\bord5\\3c&H00FFFFFF&" + FADE, layer)


def meter(o, t0, t1, appear=0.0, hot=None, pulse_top=False, x0=170, base=1440):
    """fl01 mph band meter: four steps rising left to right (green, yellow, orange, red), no numbers. appear: seconds
    between steps popping in; hot: index of the step the current fine refers to (the others dim, a marker on it)."""
    for k, col in enumerate((GREEN, YELLOW, ORANGE, RED)):
        h = 70 + 50 * k
        ta = t0 + appear * k
        ex = FADE + ("" if hot is None or hot == k else "\\1a&H90&")
        if pulse_top and k == 3:
            ex += "".join(f"\\t({i * 500},{i * 500 + 250},\\1a&H70&)\\t({i * 500 + 250},{i * 500 + 500},\\1a&H00&)"
                          for i in range(6))
        shp(o, ta, t1, x0 + 170 * k, base - h, rect(0, 0, 150, h), col, ex, 3)
        if hot == k:
            shp(o, ta, t1, x0 + 170 * k + 49, base - h - 44, poly_path([(0, 0), (52, 0), (26, 30)]), WHITE,
                FADE + "\\bord3\\3c&H00000000&", 4)


def gavel(o, t0, t1, x, y):
    """Flat gavel (head, handle, block), white with a dark outline; top-left of its box near (x, y)."""
    ex = "\\bord4\\3c&H00000000&" + FADE
    shp(o, t0, t1, x, y, rot_rect(90, 70, 150, 66, -35), WHITE, ex, 5)
    shp(o, t0, t1, x, y, rot_rect(145, 150, 170, 22, 55), WHITE, ex, 4)
    shp(o, t0, t1, x, y, rect(60, 220, 240, 252), WHITE, ex, 4)


def icons_fl01(o, cs, tm=lambda t: t):
    """tm: the language's time map (see timed); the COST meters follow the fine cards when the hook moves them."""
    r, c = cs["RULE"][0], cs["COST"][0]
    meter(o, r + 0.3, r + 3.5, appear=0.4)
    meter(o, r + 3.5, r + 6.4, pulse_top=True)
    gavel(o, r + 3.7, r + 6.4, 640, 930)
    meter(o, tm(c + 1.3), tm(c + 3.9), hot=0)
    meter(o, tm(c + 4.0), tm(c + 6.6), hot=2)
    meter(o, tm(c + 6.7), tm(c + 9.3), hot=3, pulse_top=True)


def icons_fl03(o, cs, tm=lambda t: t):
    """RULE top shot: a speed dial (two bands, no numbers) whose needle drops from the high band to the lower band,
    with a flat down arrow beside it ('slow down')."""
    t0, t1 = cs["RULE"][0] + 3.6, cs["RULE"][0] + 7.9
    cx, cy = 430, 1400
    shp(o, t0, t1, 0, 0, arc_band(cx, cy, 130, 175, 180, 75), GREEN, FADE, 3)
    shp(o, t0, t1, 0, 0, arc_band(cx, cy, 130, 175, 75, 0), RED, FADE, 3)
    shp(o, t0, t1, 0, 0, circle(cx, cy, 22), WHITE, FADE, 5)
    # needle drawn pointing up from the pivot, turned with \frz about \org (positive = counter-clockwise)
    shp(o, t0, t1, 0, 0, poly_path([(cx - 9, cy), (cx, cy - 160), (cx + 9, cy)]), WHITE,
        f"\\org({cx},{cy})\\frz-60\\t(900,2200,\\frz35)\\bord3\\3c&H00000000&" + FADE, 4)
    shp(o, t0 + 0.9, t1, 700, 1170, poly_path([(-34, -90), (34, -90), (34, 0), (80, 0), (0, 90), (-80, 0), (-34, 0)]),
        AMBER, "\\bord4\\3c&H00000000&" + FADE, 4, move=(0, 110, 0, 900))


def envelope(o, t0, t1, x, y, opened_at, move=None):
    """Flat letter: white envelope 240 x 160 (top-left at x, y) with a grey flap; at `opened_at` the flap swings up
    and a sheet with a red header rises out of it."""
    shp(o, t0, t1, x, y, rect(0, 0, 240, 160), WHITE, FADE, 3, move)
    shp(o, t0, opened_at, x, y, poly_path([(0, 0), (240, 0), (120, 92)]), GREY, "\\fad(120,0)", 5, move)
    shp(o, t0, t1, x, y, poly_path([(0, 160), (120, 76), (240, 160)]), LIGHT, FADE, 5, move)
    y = y + (move[1] if move else 0)                    # where the drop ends
    shp(o, opened_at, t1, x, y, poly_path([(0, 0), (120, -92), (240, 0)]), GREY, "\\fad(0,160)", 2)
    shp(o, opened_at, t1, x + 30, y + 10, rect(0, 0, 180, 130), "&H00F4F4F4&", "\\fad(0,160)", 4, (0, -100, 0, 450))
    shp(o, opened_at, t1, x + 50, y + 26, rect(0, 0, 140, 22), RED, "\\fad(0,160)", 4, (0, -100, 0, 450))


def icons_fl05(o, cs, tm=lambda t: t):
    r, c, k = cs["RULE"][0], cs["COST"][0], cs["CORRECT"][0]
    # RULE 0-4: the citation sheet leaves the gantry and flies off towards the owner's house (up and right)
    sheet(o, r + 0.4, r + 3.9, 380, 1100, RED, move=(330, -150, 300, 3300))
    # RULE 4-7.6: a red lock over the plate sticker
    ex = "\\bord4\\3c&H00FFFFFF&" + FADE
    lx, ly = 465, 1150
    shp(o, r + 4.2, r + 7.5, lx, ly, "m 25 62 l 25 40 b 25 -12 125 -12 125 40 l 125 62 l 100 62 l 100 40 "
        "b 100 10 50 10 50 40 l 50 62", RED, ex, 4)
    shp(o, r + 4.2, r + 7.5, lx, ly, rect(0, 58, 150, 178), RED, ex, 4)
    shp(o, r + 4.2, r + 7.5, lx, ly, circle(75, 104, 13), DARK, FADE, 5)
    shp(o, r + 4.2, r + 7.5, lx, ly, poly_path([(69, 110), (81, 110), (85, 146), (65, 146)]), DARK, FADE, 5)
    # COST: the letter drops in, then opens (the fine card sits above it)
    envelope(o, c + 0.2, tm(c + 5.1), 420, 1000, opened_at=tm(c + 1.6), move=(0, 220, 0, 500))
    # CORRECT 0-3.6: a green beep pops as the tagged car passes under the gantry (1.4 s)
    bx, by = 470, 1080
    shp(o, k + 1.3, k + 2.6, bx, by, circle(70, 70, 70), GREEN, "\\fad(80,200)", 4)
    shp(o, k + 1.3, k + 2.6, bx, by, circle(56, 70, 10), WHITE, "\\fad(80,200)", 5)
    for j, rr in enumerate((26, 46)):
        shp(o, k + 1.3 + 0.12 * j, k + 2.6, bx, by, arc_band(56, 70, rr, rr + 11, -50, 50, 10), WHITE, "\\fad(60,200)",
            5)
    # CORRECT 3.6-6: no invoice icon any more (QA r9: it read as an uncaptioned step 2, and a mailed-invoice caption
    # needs fl_toll_invoice_mail VERIFIED); the transponder step holds over the drive-on instead


ICONS = {"fl01": icons_fl01, "fl03": icons_fl03, "fl05": icons_fl05}


# ------------------------------------------------------------------ sound
class Mix(sfx.Mix):
    def amb_road(self, t0, t1, gain=0.22):
        """Arterial or freeway bed: tyre roar (low band noise) with slow swells of passing traffic."""
        n0, n1 = int(t0 * sfx.SR), int(min(self.T, t1) * sfx.SR)
        n = n1 - n0
        if n <= 0:
            return
        x = sfx.lowpass(self.rng.standard_normal(n), 40) - 0.6 * sfx.lowpass(self.rng.standard_normal(n), 400)
        tt = np.arange(n) / sfx.SR
        sw = 0.6 + 0.4 * np.sin(2 * np.pi * 0.17 * tt + self.rng.uniform(0, 6)) ** 2
        fade = np.clip(np.minimum(tt / 0.3, (tt[-1] - tt) / 0.3), 0, 1)
        self.place(x * sw * fade / (np.abs(x).max() + 1e-9), t0, gain, 0.0)

    def siren_short(self, at, gain=0.2):
        """Two-tone chirp of a patrol car (two short sweeps), no full siren."""
        for k in range(2):
            n = int(0.22 * sfx.SR)
            tt = np.arange(n) / sfx.SR
            f = 700 + 900 * tt / tt[-1]
            s = np.sign(np.sin(2 * np.pi * np.cumsum(f) / sfx.SR)) * sfx.env(n, 0.01, 0.05)
            self.place(sfx.lowpass(s, 3), at + k * 0.26, gain)

    def air_brake(self, at, gain=0.3):
        """Bus air brake: a short pop, then a falling hiss."""
        n = int(0.9 * sfx.SR)
        tt = np.arange(n) / sfx.SR
        hiss = (self.rng.standard_normal(n) - sfx.lowpass(self.rng.standard_normal(n), 6)) * np.exp(-tt * 3.2)
        pop = np.sin(2 * np.pi * 90 * tt) * np.exp(-tt * 30)
        self.place((0.5 * hiss + pop) * sfx.env(n, 0.005, 0.2), at, gain, 0.2)

    def toll_beep(self, at, gain=0.22):
        """Two short sine beeps (a reader confirming a pass)."""
        for k in range(2):
            n = int(0.09 * sfx.SR)
            tt = np.arange(n) / sfx.SR
            self.place(np.sin(2 * np.pi * 2093 * tt) * sfx.env(n, 0.004, 0.03), at + k * 0.14, gain)


def audio(code, path, extra=None):
    """Sound on the canonical timeline: the English cue list (English order = render order), no music. extra(m) adds
    the episode's own engine passes."""
    e = episode(code)
    T = e["duration_s"]
    cs = canon(e)
    m = Mix(T, seed=int(code[2:]) * 7)
    m.amb_road(0.0, cs["END"][0] + 0.4)
    for cue in e["sound"]["en"]:
        t, k = cue["t"], cue["cue"]
        if k in ("music_stop", "amb_road"):
            continue
        fn = {"whoosh": lambda: m.whoosh(t, 0.28), "tick": lambda: m.tick(t, 0.3), "horn": lambda: m.horn(t, 0.5, 0.22),
              "squeak": lambda: m.squeak(t, 0.04), "buzz": lambda: m.buzz(t, 0.16), "chime": lambda: m.chime(t, 0.2),
              "pop": lambda: m.pop(t, 0.25), "hit": lambda: m.hit(t, 0.7), "indicator": lambda: m.indicator(t, t + 2.0),
              "siren_short": lambda: m.siren_short(t), "air_brake": lambda: m.air_brake(t),
              "toll_beep": lambda: m.toll_beep(t)}.get(k)
        if fn is None:
            raise SystemExit(f"unknown cue {k}")
        fn()
    if extra:
        extra(m, cs)
    return m.write(path)


def edit(code):
    e = episode(code)
    first = {lang: O.plain(e["hooks"][lang]["lines"][0]).rstrip(" ,;:") for lang in ("en", "de", "fr")}
    return {"title": {"en": e["post"]["title"], "de": "Drive Like a Local Florida: " + first["de"],
                      "fr": "Drive Like a Local Floride : " + first["fr"]},
            "segments": {k: list(v) for k, v in canon(e).items()},
            "order": {lang: e["segment_order"][lang]["order"] for lang in ("en", "de", "fr")},
            "slug": e["slug"], "disclaimer": json.load(open(EPISODES))["rules"]["disclaimer"]}


def facts_md(code):
    """flNN_facts.md: each claim on screen, its fact key, status and sources (from facts/us-fl.json)."""
    e = episode(code)
    D = FU.load()
    out = [f"# {code}: {e['slug']} (claims on screen)", "",
           f"Statute on the end card: {e['statute']}. Numbers come only from VERIFIED keys of facts/us-fl.json "
           "through scripts/gta/facts_us.py; anything else shows its no-number fallback.", ""]
    for lang in ("en",):
        for t0, t1, kind, y, ls, keys in captions(e, lang, D):
            if not keys:
                continue
            txt = " / ".join(O.plain(x) for x in (ls[0] + [ls[1]] + ls[2] if kind == "fine" else ls))
            out.append(f"- {t0:.1f} to {t1:.1f} s ({kind}): \"{txt}\" -> {', '.join(sorted(keys))}")
    out += ["", "| key | status | on screen (EN) | sources |", "|---|---|---|---|"]
    for k in e["fact_keys"]:
        ent = D.data["keys"].get(k, {})
        src = "; ".join(f"{s.get('publisher', '')} ({s.get('date') or s.get('read') or s.get('accessed', '')})"
                        for s in ent.get("sources", []))
        out.append(f"| {k} | {ent.get('status')} | {ent.get('on_screen_en') or ent.get('label_en') or ''} | {src} |")
    out += ["", "Not affiliated with Rockstar Games or Take-Two Interactive.", ""]
    return "\n".join(out)


def main(code, out, extra=None):
    os.makedirs(out, exist_ok=True)
    for lang in ("en", "de", "fr"):
        with open(os.path.join(out, f"{code}_{lang}.ass"), "w", encoding="utf-8") as f:
            f.write(build(code, lang))
    json.dump(edit(code), open(os.path.join(out, f"{code}_edit.json"), "w", encoding="utf-8"), indent=1,
              ensure_ascii=False)
    print(audio(code, os.path.join(out, f"audio_{code}.wav"), extra))


if __name__ == "__main__":
    # python fl01_uspost.py --facts   rewrites every flNN/flNN_facts.md
    if "--facts" in sys.argv:
        for n in range(1, 6):
            code = f"fl{n:02d}"
            p = os.path.join(DL, code, f"{code}_facts.md")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "w", encoding="utf-8").write(facts_md(code))
            print("wrote", p)
