"""Shared caption, edit and sound code for the a3b Autobahn episodes (post_ep09, post_ep17, post_ep19); not a scene.
Captions sit on the canonical (English-order) timeline; kit/finish_ep.py composes each language and cuts it into that
language's segment order (epNN_edit.json). Numbers only through kit/facts.py and only when VERIFIED, else the episode
shows its no-number line. German "du", French "vous", at most 17 characters per second (epNN_cps.json lists every
line). Sound: synthesised only (kit/sfx.py plus the road cues below), no voice, no music.
"""
import json
import os
import re
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
for _p in (os.path.join(HERE, "..", "kit"), HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import facts as F  # noqa: E402
import overlay as O  # noqa: E402
import sfx  # noqa: E402

D = F.load("de")
LANGS = ("en", "de", "fr")
COUNTRY = {"en": "GERMANY", "de": "DEUTSCHLAND", "fr": "ALLEMAGNE"}
PRICE = {"en": ["The price:"], "de": ["Der Preis:"], "fr": ["Le prix :"]}
RULE = {"en": ["The rule:"], "de": ["Die Regel:"], "fr": ["La règle :"]}
INSTEAD = {"en": ["Do this instead:"], "de": ["Besser so:"], "fr": ["À la place :"]}
MISTAKE = {"en": ["The mistake:"], "de": ["Der Fehler:"], "fr": ["L'erreur :"]}
END1 = {"en": ["Now you drive", "[y]like a local.[/]"], "de": ["Jetzt fährst du", "[y]wie ein Einheimischer.[/]"],
        "fr": ["Vous conduisez", "[y]comme un local.[/]"]}
# END2 (follow line) dropped: with END1 it read at 20 to 24 cps (QA rule: one block at most 17)
END2 = {"en": ["Follow for more rules."], "de": ["Mehr Regeln? Folgen!"], "fr": ["Abonnez-vous pour plus."]}
CPS_MAX = 17.0
SR = sfx.SR


def spans(segs):
    out, t = {}, 0.0
    for k, d in segs:
        out[k] = (t, t + d)
        t += d
    return out, t


def kmh(key):
    """'130 km/h' from a VERIFIED number fact (its on-screen text), else None."""
    if not D.ok(key):
        return None
    m = re.search(r"(\d+)\s*km/h", D.value(key, "on_screen_en") or "")
    return f"{m.group(1)} km/h" if m else None


class Cut:
    """Captions of one language on the canonical timeline. lead=True lines are dropped when their segment opens this
    language's cut (the hook takes those first seconds)."""

    def __init__(self, ep, lang, segs, order, footer):
        self.lang, self.order = lang, order
        self.sp, self.T = spans(segs)
        self.o = O.Overlay(ep, COUNTRY[lang], footer, self.T)
        self.o.chip()
        self.cps = []

    def t(self, seg, rel):
        return self.sp[seg][0] + rel

    def opens(self, seg):
        return self.order[0] == seg

    def _rate(self, kind, lines, t0, t1):
        n = len(" ".join(O.plain(x) for x in lines))
        self.cps.append(dict(kind=kind, t0=round(t0, 2), text=" / ".join(O.plain(x) for x in lines), chars=n,
                             cps=round(n / max(0.01, t1 - t0), 1)))

    def block(self, seg, r0, r1, lines, y, size=66, kind="body", lead=False, anim=O.POP, room=None):
        if lead and self.opens(seg):
            return
        t0, t1 = self.t(seg, r0), self.t(seg, r1)
        self.o.block(t0, t1, lines, y, size=size, anim=anim, room=room)
        self._rate(kind, lines, t0, t1)

    def hook(self, lines, size=74):
        seg = self.order[0]
        t0, t1 = self.t(seg, 0.15), self.t(seg, 2.1)
        self.o.block(t0, t1, lines, 390, size=size, room=230)
        self._rate("hook", lines, t0, t1)

    def card(self, seg, r0, r1, key, lead, box, y_top=640):
        """Fine card: amount, points and ban from facts (VERIFIED only), else the no-number box."""
        t0, t1 = self.t(seg, r0), self.t(seg, r1)
        amount = D.fine(key, self.lang)
        extra = [x for x in (D.points(key, self.lang), D.ban(key, self.lang)) if x]
        self.o.fine(t0, t1, lead, amount or box, extra if amount else [], y_top=y_top)
        self._rate("card", lead + [amount or box] + (extra if amount else []), t0, t1)

    def end(self, seg="END"):
        a, b = self.t(seg, 0.2), self.sp[seg][1]
        self.o.block(a, b - 0.05, END1[self.lang], 520, size=96)
        self.o.foot(a, b)
        self._rate("end", END1[self.lang], a, b - 0.05)

    def standard(self, L, price=(0.2, 2.05)):
        """The standard episode frame: hook, mistake lead over HOOK, sub leads of RULE, COST and CORRECT, end card."""
        self.hook(L["hook"])
        self.block("HOOK", 0.2, 2.1, MISTAKE[self.lang], 470, lead=True)
        self.block("RULE", 0.2, 1.2, RULE[self.lang], 470, 70, kind="sub", lead=True)
        self.block("COST", price[0], price[1], PRICE[self.lang], 640, 74, kind="sub", lead=True)
        self.block("CORRECT", 0.2, 1.2, INSTEAD[self.lang], 470, 70, kind="sub", lead=True)
        self.end()

    def text(self):
        return self.o.text()


def write_all(out, ep, segs, orders, titles, footers, build, audio):
    os.makedirs(out, exist_ok=True)
    sp, T = spans(segs)
    report = {}
    for lang in LANGS:
        c = Cut(ep, lang, segs, orders[lang], footers[lang])
        build(c, lang)
        with open(os.path.join(out, f"ep{ep:02d}_{lang}.ass"), "w", encoding="utf-8") as f:
            f.write(c.text())
        fast = [r for r in c.cps if r["cps"] > CPS_MAX]
        report[lang] = dict(max=max(r["cps"] for r in c.cps), fast=fast, all=c.cps)
        for r in fast:
            print(f"WARN {lang} {r['cps']} cps: {r['text']}")
    json.dump(report, open(os.path.join(out, f"ep{ep:02d}_cps.json"), "w", encoding="utf-8"), indent=1,
              ensure_ascii=False)
    edit = {"title": titles, "segments": {k: [round(a, 3), round(b, 3)] for k, (a, b) in sp.items()},
            "order": orders, "facts_used": sorted(D.used)}
    json.dump(edit, open(os.path.join(out, f"ep{ep:02d}_edit.json"), "w", encoding="utf-8"), indent=1,
              ensure_ascii=False)
    print(audio(os.path.join(out, f"audio_ep{ep:02d}.wav"), sp, T))


# ---------------------------------------------------------------- road cues (synthesised, no samples, no voice)
def _t(n):
    return np.arange(n) / SR


def road(m, t0, t1, gain=0.18, wind=0.0, rain=0.0):
    """Motorway bed: tyre roar (low-passed noise, slow swell), optional wind roar and rain hiss."""
    n = int((t1 - t0) * SR)
    if n <= 0:
        return
    tt = _t(n)
    w = m.rng.standard_normal(n)
    s = sfx.lowpass(w, 40) * 6.0 * (0.8 + 0.2 * np.sin(2 * np.pi * 0.23 * tt))
    if wind:
        s += wind * sfx.lowpass(m.rng.standard_normal(n), 12) * 4.0 * (0.7 + 0.3 * np.sin(2 * np.pi * 0.7 * tt))
    if rain:
        h = m.rng.standard_normal(n)
        s += rain * (h - sfx.lowpass(h, 6)) * 0.6
    m.place(s * sfx.env(n, 0.15, 0.15), t0, gain)


def cough(m, at, gain=0.35):
    """Engine splutter: three uneven low bursts with a falling pitch."""
    for k, d in enumerate((0.0, 0.17, 0.41)):
        n = int(0.14 * SR)
        tt = _t(n)
        s = np.sin(2 * np.pi * (70 - 120 * tt) * tt) * (1 + 0.5 * sfx.lowpass(m.rng.standard_normal(n), 20))
        m.place(s * sfx.env(n, 0.005, 0.08), at + d, gain * (1 - 0.2 * k))


def chirp(m, at, gain=0.16, dur=0.9):
    """Short police siren chirp: a quick two-tone sweep."""
    n = int(dur * SR)
    tt = _t(n)
    f = 650 + 500 * (0.5 + 0.5 * np.sign(np.sin(2 * np.pi * 3.3 * tt)))
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * sfx.env(n, 0.02, 0.2)
    m.place(s, at, gain)


def pump(m, at, gain=0.2):
    """Fuel nozzle click."""
    n = int(0.06 * SR)
    s = m.rng.standard_normal(n) * np.exp(-_t(n) * 120)
    m.place(s - sfx.lowpass(s, 4), at, gain)


def thud(m, at, gain=0.5):
    n = int(0.4 * SR)
    tt = _t(n)
    m.place(np.sin(2 * np.pi * (80 - 40 * tt) * tt) * np.exp(-tt * 10), at, gain)


def end_sounds(m, sp):
    e = sp["END"][0]
    m.chime(e, 0.12, (1046.5,))
    m.pop(e + 0.2, 0.25)
