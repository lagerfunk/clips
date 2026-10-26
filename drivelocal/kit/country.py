"""Track B (countries other than Germany): captions, sound and edit list from scripts/trackb/episodes.json, plus the
small country restyles of the town kit (palettes, cobbles, terraces, red cycle lanes, the mirrored world for left-hand
traffic, blank local plates, flat teaching graphics and the end card).

Post side (no Blender):
    import country as CY
    E = CY.Episode("B02", overrides={...})
    E.write(OUTDIR)          -> bNN_en.ass, bNN_de.ass, bNN_fr.ass, audio_bNN.wav, bNN_edit.json
    E.segments               -> canonical segment spans (the render's timeline), END last
Every number comes from facts/<cc>.json through kit/facts.py and only when VERIFIED; otherwise the script's fallback
line (or nothing, when the script gives none). Captions are re-timed inside their segment so no line runs faster than
17 characters per second; a line that cannot fit must be shortened in the episode's overrides (never sped up).

Scene side (Blender): see the second half of the file (palette, terrace, cobbles, mirror_world, blank_plates, flat,
end_card)."""
import json
import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CPS = 17.0
END_DUR = 4.2       # the end card is held longer than the script's 2.7 s so the closing lines can be read
HOOK_DUR = 2.6      # the hook shot runs 0.4 s longer than scripted so the hook line can be read at 17 cps
# canonical render timeline (segment order of the scripts, HOOK and END lengthened as above); the scene scripts read
# it from here because episodes.json is not copied to the runners. tests/test_trackb_town.py checks it against the json.
TIMELINE = {
    "B02": [("HOOK", 2.6), ("SITUATION", 9.5), ("RULE", 7.5), ("COST", 6.5), ("CORRECT", 6.5), ("END", 4.2)],
    "B05": [("HOOK", 2.6), ("SITUATION", 9.5), ("RULE", 8.0), ("COST", 5.5), ("CORRECT", 6.5), ("END", 4.2)],
    "B06": [("HOOK", 2.6), ("SITUATION", 9.5), ("RULE", 8.0), ("COST", 4.5), ("CORRECT", 6.5), ("END", 4.2)],
    "B08": [("HOOK", 2.6), ("SITUATION", 9.5), ("RULE", 8.0), ("COST", 5.0), ("CORRECT", 7.5), ("END", 4.2)],
    # motorway episodes (dl/trackb-motorway)
    "B01": [("HOOK", 2.6), ("SITUATION", 9.0), ("RULE", 7.5), ("COST", 5.5), ("CORRECT", 6.5), ("END", 4.2)],
    "B03": [("HOOK", 2.6), ("SITUATION", 9.0), ("RULE", 8.0), ("COST", 5.0), ("CORRECT", 7.5), ("END", 4.2)],
    "B04": [("HOOK", 2.6), ("SITUATION", 9.5), ("RULE", 8.0), ("COST", 6.5), ("CORRECT", 6.0), ("END", 4.2)],
    "B07": [("HOOK", 2.6), ("SITUATION", 9.0), ("RULE", 8.0), ("COST", 6.0), ("CORRECT", 7.0), ("END", 4.2)],
}


def spans(eid):
    """{segment: (t0, t1)} on the canonical timeline and the total length T."""
    out, t = {}, 0.0
    for k, d in TIMELINE[eid]:
        out[k] = (round(t, 3), round(t + d, 3))
        t += d
    return out, round(t, 3)

COUNTRY = {
    "it": dict(en="ITALY", de="ITALIEN", fr="ITALIE", flag=("&H00469200&", "&H00FFFFFF&", "&H00372BCE&"), vert=True),
    "uk": dict(en="UNITED KINGDOM", de="GROSSBRITANNIEN", fr="ROYAUME-UNI", flag="union", vert=False),
    "nl": dict(en="NETHERLANDS", de="NIEDERLANDE", fr="PAYS-BAS", flag=("&H00281CAE&", "&H00FFFFFF&", "&H008B4621&"),
               vert=False),
    "es": dict(en="SPAIN", de="SPANIEN", fr="ESPAGNE", flag="spain", vert=False),
    # motorway episodes (dl/trackb-motorway): AT red-white-red, FR blue-white-red, CH white cross on red
    "at": dict(en="AUSTRIA", de="ÖSTERREICH", fr="AUTRICHE", flag=("&H002E10C8&", "&H00FFFFFF&", "&H002E10C8&"),
               vert=False),
    "fr": dict(en="FRANCE", de="FRANKREICH", fr="FRANCE", flag=("&H00952300&", "&H00FFFFFF&", "&H003929ED&"), vert=True),
    "ch": dict(en="SWITZERLAND", de="SCHWEIZ", fr="SUISSE", flag="swiss", vert=False),
}
LAYOUT = {   # kind: (default y_top, size, animation)
    "hook": (390, 66, "pop"), "sub": (560, 60, "pop"), "body": (560, 64, "pop"), "rule": (560, 72, "pop"),
    "slam": (520, 110, "slam"), "step": (560, 62, "pop"), "end": (520, 92, "pop"), "end2": (760, 54, "pop"),
}


# the closing lines are the same in every episode; shortened so the end card reads at 17 cps or slower
GENERIC = {
    "de": {"Mehr Verkehrsregeln?": {"lines": ["Mehr Regeln? Folge uns."]}},
    "fr": {"Désormais, vous pouvez": {"lines": ["Vous conduisez", "[y]comme un local.[/]"]},
           "Suivez-nous pour en savoir": {"lines": ["Suivez-nous pour", "d'autres règles."]}},
}


def plain_len(text):
    import overlay as O
    return len(O.plain(text.replace("|", " ")).strip())


def load_episode(eid):
    d = json.load(open(os.path.join(ROOT, "scripts", "trackb", "episodes.json"), encoding="utf-8"))
    return next(e for e in d["episodes"] if e["id"] == eid)


class Episode:
    """overrides: {lang: {original text prefix: {"lines": [...]} | None}} replaces (or drops) a caption whose resolved
    or template text starts with the prefix. Placeholders allowed in override lines: {val:key} {fine:key} and
    {num:key} (the first number in the key's on-screen text; VERIFIED only, else the override is skipped and the
    script's fallback is used)."""

    def __init__(self, eid, overrides=None, titles=None, extra_sound=None):
        import facts as F
        self.e = load_episode(eid)
        self.eid, self.cc, self.n = eid, self.e["cc"], self.e["number"]
        self.F = F.load(self.cc)
        self.ovr = {lang: dict(GENERIC.get(lang, {}), **(overrides or {}).get(lang, {})) for lang in ("en", "de", "fr")}
        self.titles = titles or {}
        self.extra_sound = extra_sound
        self.segments, self.T = spans(eid)
        self.missing, self.nofit = [], []

    # ---------------------------------------------------------- placeholders
    def _fill(self, text, lang):
        def rep(m):
            kind, key = m.group(1), m.group(2)
            if kind == "fine":
                v = self.F.fine(key, lang)
            elif kind == "val":
                v = self.F.value(key, f"on_screen_{lang}")
            else:
                v = self.F.value(key, "on_screen_en")
                nums = re.findall(r"\d+", v or "")
                k = 1 if kind == "num" else int(kind[3:])
                v = nums[k - 1] if len(nums) >= k else None
            if v is None:
                self.missing.append(key)
                raise KeyError(key)
            return v
        return re.sub(r"\{(fine|val|num|num2):([a-z0-9_]+)\}", rep, text)

    def resolve(self, cap, lang):
        """The caption as shown: dict(kind, lines, t0, t1, y, fine=(lead, amount, extra)) or None (nothing shown)."""
        import overlay as O
        cap = dict(cap)
        for pre, rep in self.ovr.get(lang, {}).items():
            pre = O.plain(pre)
            if O.plain(cap.get("text", "")).startswith(pre) or O.plain(cap.get("fb", "")).startswith(pre):
                if rep is None:
                    return None
                try:
                    lines = [self._fill(ln, lang) for ln in rep["lines"]]
                    out = dict(cap, lines=lines)
                    if "amount" in rep:
                        out["fine"] = dict(lead_lines=lines, amount=self._fill(rep["amount"], lang), extra=[])
                    return out
                except KeyError:
                    break
        ok = all(self.F.ok(k) for k in cap.get("req", []))
        try:
            if not ok:
                raise KeyError("req")
            if cap["kind"] == "fine":
                f = cap["fine"]
                return dict(cap, fine=dict(lead_lines=f["lead_lines"], amount=self._fill(f["amount"], lang),
                                           extra=[self._fill(x, lang) for x in f.get("extra", [])]))
            lines = cap["lines"]
            if any("{" in ln for ln in lines):
                import overlay as O
                full = self._fill(" ".join(lines), lang)
                lines = O.wrap(full, 24)
            return dict(cap, lines=lines)
        except KeyError:
            if not cap.get("fb_lines"):
                return None
            return dict(cap, kind="body" if cap["kind"] == "fine" else cap["kind"], lines=cap["fb_lines"],
                        fine=None)

    # ---------------------------------------------------------- timing
    @staticmethod
    def nchars(c):
        if c.get("fine"):
            f = c["fine"]
            return sum(plain_len(x) for x in f["lead_lines"] + [f["amount"]] + f["extra"])
        return sum(plain_len(x) for x in c["lines"])

    def timed(self, lang):
        """Captions of one language on the canonical timeline, re-timed per segment to at most 17 cps."""
        out = []
        hook = dict(self.e["hooks"][lang])
        if hook["seg"] == "HOOK":
            hook["rel_t1"] = HOOK_DUR - 0.05
        caps = [hook] + [c for c in self.e["captions"][lang]]
        for seg, (a, b) in self.segments.items():
            items = [r for r in (self.resolve(c, lang) for c in caps if c["seg"] == seg and c["kind"] != "foot") if r]
            items.sort(key=lambda c: c["rel_t0"])
            dur = b - a
            if seg == "END":
                for c in items:
                    t0 = c["rel_t0"] + (0.4 if c["kind"] == "end2" else 0.0)
                    out.append(dict(c, t0=a + t0, t1=b - 0.05))
                continue
            if not items:
                continue

            def fits(its, floor):
                return sum(max(floor, self.nchars(c) / (CPS - 0.5)) for c in its) + 0.1 * len(its) + 0.2 <= dur
            if not fits(items, 1.0) and any(c["kind"] == "sub" for c in items):
                items = [c for c in items if c["kind"] != "sub"]      # cut the lead-in ("The rule:") first
            need = [max(c["rel_t1"] - c["rel_t0"], self.nchars(c) / (CPS - 0.5)) for c in items]
            if sum(need) + 0.1 * len(items) + items[0]["rel_t0"] > dur:
                need = [max(1.0, self.nchars(c) / (CPS - 0.5)) for c in items]
            t0s, prev = [], 0.0
            for c, nd in zip(items, need):
                t0 = max(c["rel_t0"], prev + 0.1 if t0s else c["rel_t0"])
                t0s.append(t0)
                prev = t0 + nd
            # pull back from the segment end if needed
            end = dur - 0.05
            for i in range(len(items) - 1, -1, -1):
                lim = end if i == len(items) - 1 else t0s[i + 1] - 0.1
                if t0s[i] + need[i] > lim:
                    t0s[i] = lim - need[i]
            for c, t0, nd in zip(items, t0s, need):
                if t0 < 0.1 - 1e-6:
                    self.nofit.append((lang, seg, [x["lines"] for x in items]))
                    t0 = 0.1
                t1 = min(end, max(t0 + nd, t0 + (c["rel_t1"] - c["rel_t0"])))
                out.append(dict(c, t0=a + t0, t1=a + t1))
        return out

    # ---------------------------------------------------------- captions
    def ass(self, lang):
        import overlay as O
        C = COUNTRY[self.cc]
        footer = self.e["end_card"][lang]
        o = O.Overlay(f"B{self.n}", C[lang], footer, self.T)
        chip(o, C, f"B{self.n}", C[lang])
        for c in self.timed(lang):
            k = c["kind"]
            y0, size, anim = LAYOUT.get(k, (560, 64, "pop"))
            y = c.get("y") or y0
            if c.get("fine"):
                f = c["fine"]
                o.fine(c["t0"], c["t1"], f["lead_lines"], f["amount"], f["extra"], y_top=y)
                continue
            lines = list(c["lines"])
            if k == "step" and lines and re.match(r"^\d\s", O.plain(lines[0])):
                lines[0] = "[y]" + lines[0][0] + "[/] " + lines[0][1:].lstrip()
            o.block(c["t0"], c["t1"], lines, y, size=size, anim=O.SLAM if anim == "slam" else O.POP,
                    room=360 if k not in ("hook", "end2") else None)
        a, b = self.segments["END"]
        o.foot(a + 0.2, b - 0.05)
        return o.text()

    # ---------------------------------------------------------- sound
    def audio(self, path, seed=7):
        import numpy as np
        import sfx
        m = sfx.Mix(self.T, seed=seed)
        m.suburb(0.28)
        for s in self.e["segments"]:
            a, b = self.segments[s["id"]]
            for q in s.get("sound", []):
                cue(m, q["cue"], a + q["t"], (a, b), q.get("note", ""), np)
        if self.extra_sound:
            self.extra_sound(m, self.segments)
        return m.write(path)

    def edit(self):
        title = {"en": self.e["post"]["title"]}
        title.update(self.titles)
        order = {lang: v["order"] for lang, v in self.e["segment_order"].items()}
        return {"title": title, "segments": {k: list(v) for k, v in self.segments.items()}, "order": order,
                "T": self.T, "cps_max": CPS}

    def facts_md(self, signs_dir="/home/claude/assets/signs", credits=()):
        """bNN_facts.md: every on-screen claim with its fact key, status today and sources; the sign credits."""
        e, F = self.e, self.F
        L = [f"# B{self.n} facts: {e['post']['title']}", "",
             f"Facts file facts/{self.cc}.json, read with kit/facts.py at build time. Only VERIFIED keys put a number or "
             "a claim on screen; any other key shows the script's no-number fallback line (or nothing).", "",
             "| on screen (EN, as rendered) | key | status | sources (publisher, page date) |", "|---|---|---|---|"]
        for c in self.timed("en"):
            keys = set(c.get("req", []))
            raw = [c0 for c0 in e["captions"]["en"] if c0["seg"] == c["seg"] and c0["rel_t0"] == c["rel_t0"]]
            if raw:
                keys |= set(re.findall(r"\{(?:val|fine):([a-z0-9_]+)\}", raw[0]["text"] + json.dumps(raw[0].get("fine"))))
                keys |= set(raw[0].get("req", []))
            if not keys:
                continue
            shown = " / ".join(c["lines"]) + (" " + c["fine"]["amount"] if c.get("fine") else "")
            import overlay as O
            for k in sorted(keys):
                ent = F.keys.get(k, {})
                srcs = "; ".join(f"{s.get('publisher')} ({s.get('page_date')})" for s in ent.get("sources", []))
                L.append(f"| {O.plain(shown)} | {k} | {ent.get('status')} | {srcs} |")
        L += ["", "Keys of the script not VERIFIED today (fallback shown, no claim):"]
        L += [f"- {k}: {F.keys.get(k, {}).get('status')}" for k in e["fact_keys"] if not F.ok(k)] or ["- none"]
        L += ["", f"End card: {e['end_card']['en']}", "", "## Description credits", ""]
        sj = os.path.join(signs_dir, self.cc, "sources.json")
        if os.path.exists(sj):
            for sid, s in json.load(open(sj, encoding="utf-8")).items():
                L.append(f"- Sign {sid}: {s.get('title', '').replace('File:', '')}, {s.get('licence')}, "
                         f"{s.get('page')}")
        L += [f"- {x}" for x in credits]
        return "\n".join(L) + "\n"

    def write(self, out):
        os.makedirs(out, exist_ok=True)
        tag = f"b{self.n:02d}"
        for lang in ("en", "de", "fr"):
            with open(os.path.join(out, f"{tag}_{lang}.ass"), "w", encoding="utf-8") as f:
                f.write(self.ass(lang))
        json.dump(self.edit(), open(os.path.join(out, f"{tag}_edit.json"), "w", encoding="utf-8"), indent=1,
                  ensure_ascii=False)
        return self.audio(os.path.join(out, f"audio_{tag}.wav"))


def chip(o, C, number, country):
    """Series chip with the country's flag (64 x 48 box at x 100, y 302)."""
    import overlay as O
    x, y, h = O.CHIP_X, O.CHIP_Y, O.CHIP_H
    T = o.T
    ev = o.ev

    def shape(col, pts, clip=True):
        d = "m " + " l ".join(f"{px:.1f} {py:.1f}" for px, py in pts)
        cl = f"\\clip({x},{y + 8},{x + 64},{y + 40})" if clip else ""
        ev.append(f"Dialogue: 2,{O.ts(0)},{O.ts(T)},Box,,0,0,0,,{{\\pos({x},{y})\\an7\\bord0\\shad0\\1c{col}"
                  f"{cl}\\fad(200,0)\\p1}}{d}{{\\p0}}")
    flag = C["flag"]
    if flag == "union":
        W_, H_ = 64.0, 32.0
        oy = 8.0

        def band(x0, y0, x1, y1, hw):
            L = math.hypot(x1 - x0, y1 - y0)
            nx, ny = -(y1 - y0) / L * hw, (x1 - x0) / L * hw
            return [(x0 + nx, y0 + ny + oy), (x1 + nx, y1 + ny + oy), (x1 - nx, y1 - ny + oy), (x0 - nx, y0 - ny + oy)]
        shape("&H007D2401&", [(0, oy), (W_, oy), (W_, oy + H_), (0, oy + H_)])
        for hw, col in ((3.2, "&H00FFFFFF&"), (1.1, "&H00341AC8&")):
            shape(col, band(-4, -2, W_ + 4, H_ + 2, hw))
            shape(col, band(-4, H_ + 2, W_ + 4, -2, hw))
        for hw, col in ((5.4, "&H00FFFFFF&"), (3.2, "&H00341AC8&")):
            shape(col, [(W_ / 2 - hw, oy), (W_ / 2 + hw, oy), (W_ / 2 + hw, oy + H_), (W_ / 2 - hw, oy + H_)])
            shape(col, [(0, oy + H_ / 2 - hw), (W_, oy + H_ / 2 - hw), (W_, oy + H_ / 2 + hw), (0, oy + H_ / 2 + hw)])
    elif flag == "swiss":
        shape("&H001C29DA&", [(8, 0), (56, 0), (56, 48), (8, 48)], clip=False)
        shape("&H00FFFFFF&", [(29, 9), (35, 9), (35, 39), (29, 39)], clip=False)
        shape("&H00FFFFFF&", [(17, 21), (47, 21), (47, 27), (17, 27)], clip=False)
    elif flag == "spain":
        for y0, y1, col in ((0, 12, "&H001B15AA&"), (12, 36, "&H0000BFF1&"), (36, 48, "&H001B15AA&")):
            shape(col, [(0, y0), (64, y0), (64, y1), (0, y1)], clip=False)
    else:
        for k, col in enumerate(flag):
            if C["vert"]:
                shape(col, [(k * 21.33, 0), ((k + 1) * 21.33, 0), ((k + 1) * 21.33, h), (k * 21.33, h)], clip=False)
            else:
                shape(col, [(0, k * 16), (64, k * 16), (64, (k + 1) * 16), (0, (k + 1) * 16)], clip=False)
    ev.append(f"Dialogue: 1,{O.ts(0)},{O.ts(T)},Box,,0,0,0,,{{\\pos({x + 76},{y + 10})\\an7\\fs28\\fad(200,0)}}"
              f"DRIVE LIKE A LOCAL  {{\\c&H0000C8FF&}}#{number}  {country}")


# -------------------------------------------------------------- synthesised cues (no samples, no voice, no music)
def cue(m, name, at, span, note, np):
    SR = 48000
    rng = m.rng

    def sig(dur):
        n = int(dur * SR)
        return n, np.arange(n) / SR
    if name in ("amb_suburb", "amb_road", "music_stop"):
        if name == "amb_road":
            n, t = sig(span[1] - span[0])
            w = rng.standard_normal(n)
            m.place(np.convolve(w, np.ones(200) / 200, mode="same") * 0.6, span[0], 0.5)
        return
    if name == "engine":
        m.engine(span[0], span[1], lambda tt: 5.0, lambda tt: 0.0, 0.16)
    elif name == "indicator":
        m.indicator(at, min(span[1], at + 1.6))
    elif name == "horn":
        m.horn(at, 1.0 if "long" in note else 0.5, 0.12 if "far" in note else 0.24)
    elif name == "squeak":
        m.squeak(at, 0.05 if "long" in note else 0.03)
        if "long" in note:
            m.squeak(at + 0.35, 0.04)
    elif name in ("whoosh", "pop", "tick", "buzz"):
        getattr(m, name)(at)
    elif name == "hit":
        m.hit(at, 0.75)
    elif name == "chime":
        m.chime(at, 0.12 if "soft" in note else 0.22, (1046.5,) if "one" in note else (1046.5, 1318.5, 1568.0))
    elif name == "ping":
        n, t = sig(0.5)
        m.place((np.sin(2 * np.pi * 1760 * t) + 0.25 * np.sin(2 * np.pi * 3520 * t)) * np.exp(-t * 9), at, 0.22)
    elif name == "click":
        n, t = sig(0.03)
        m.place(rng.standard_normal(n) * np.exp(-t * 300), at, 0.18)
    elif name == "flash":
        n, t = sig(0.35)
        whine = np.sin(2 * np.pi * (3000 + 4000 * t) * t) * np.exp(-t * 9) * 0.25
        snap = rng.standard_normal(n) * np.exp(-t * 60)
        m.place(whine + snap, at, 0.22)
    elif name in ("thud", "door"):
        n, t = sig(0.4)
        m.place(np.sin(2 * np.pi * (85 - 40 * t) * t) * np.exp(-t * 14) + 0.3 * rng.standard_normal(n) *
                np.exp(-t * 50), at, 0.5 if "soft" not in note else 0.3)
        if name == "door":
            cue(m, "click", at + 0.12, span, "", np)
    elif name == "bell":
        n, t = sig(1.2)
        s = sum(a * np.sin(2 * np.pi * f * t) for f, a in ((2350, 1.0), (3480, 0.5), (5100, 0.2)))
        for k in range(2):
            m.place(s * np.exp(-t * 4.5), at + 0.16 * k, 0.12)
    elif name == "bike":
        tt = 0.0
        while tt < 1.6:
            cue(m, "click", at + tt, span, "", np)
            tt += 0.07
        m.whoosh(at + 0.6, 0.15)
    elif name == "siren_short":
        n, t = sig(1.6)
        f = 700 + 500 * (0.5 + 0.5 * np.sin(2 * np.pi * 1.8 * t))
        m.place(np.sin(2 * np.pi * np.cumsum(f) / SR) * np.minimum(1, t * 8) * np.minimum(1, (1.6 - t) * 6), at, 0.1)


def check_cps(ep, langs=("en", "de", "fr")):
    """List of (lang, seg, cps, text) above the limit (the footer source line is exempt: it is the credit line)."""
    bad = []
    for lang in langs:
        ep.nofit = []
        tl = ep.timed(lang)
        bad += [(lg, sg, "no fit", ln) for lg, sg, ln in ep.nofit]
        for c in tl:
            if c["kind"] == "foot":
                continue
            n = Episode.nchars(c)
            if c["seg"] == "END":
                continue
            cps = n / max(0.01, c["t1"] - c["t0"])
            if cps > CPS + 1e-6:
                bad.append((lang, c["seg"], round(cps, 1), c["lines"]))
        end = [c for c in tl if c["seg"] == "END"]
        if end:
            n = sum(Episode.nchars(c) for c in end)
            a, b = ep.segments["END"]
            if n / (b - a - 0.2) > CPS:
                bad.append((lang, "END", round(n / (b - a - 0.2), 1), [c["lines"] for c in end]))
    return bad


# ================================================================== scene side (Blender)
SPEC = {
    # old-town street: one lane between facades, kerbless, setts (Italian centri storici; not a verified spec number)
    "it": dict(street=4.2, palette="it"),
    # UK: the German town kit mirrored (lanes, roundabout, cabin side flip together); centre line kept from the kit
    "uk": dict(lane=3.0, palette="uk"),
    # NL: the townplus Radfahrstreifen width (1.85 m incl. the 0.25 m line), only the colour changes to red
    "nl": dict(cycle_lane=1.85, palette="nl"),
    "es": dict(lane=3.25, palette="es"),
}
PALETTE = {
    "it": dict(walls=[((0.78, 0.52, 0.22), (0.84, 0.6, 0.3)), ((0.72, 0.36, 0.2), (0.78, 0.42, 0.25)),
                      ((0.86, 0.76, 0.56), (0.9, 0.82, 0.64)), ((0.8, 0.62, 0.38), (0.85, 0.68, 0.45)),
                      ((0.66, 0.3, 0.18), (0.72, 0.36, 0.22))],
               shutters=[(0.1, 0.24, 0.14), (0.16, 0.3, 0.2), (0.32, 0.18, 0.08)], roof="terracotta", brick=False,
               storeys=(3, 4), frame=(0.32, 0.2, 0.1)),
    "uk": dict(walls=[((0.42, 0.16, 0.1), (0.5, 0.2, 0.13)), ((0.5, 0.24, 0.15), (0.58, 0.3, 0.2)),
                      ((0.36, 0.14, 0.09), (0.44, 0.18, 0.12))],
               shutters=[], roof="slate", brick=True, storeys=(2, 3), frame=(0.9, 0.9, 0.88)),
    "nl": dict(walls=[((0.36, 0.14, 0.08), (0.44, 0.19, 0.11)), ((0.3, 0.12, 0.08), (0.38, 0.16, 0.1)),
                      ((0.45, 0.25, 0.14), (0.52, 0.3, 0.18))],
               shutters=[], roof="flat", brick=True, storeys=(3, 4), frame=(0.92, 0.92, 0.9)),
    "es": dict(walls=[((0.88, 0.86, 0.8), (0.93, 0.91, 0.86)), ((0.86, 0.78, 0.62), (0.9, 0.84, 0.7)),
                      ((0.9, 0.88, 0.84), (0.95, 0.93, 0.9))],
               shutters=[(0.35, 0.2, 0.08), (0.12, 0.22, 0.14)], roof="terracotta", brick=False, storeys=(3, 5),
               frame=(0.3, 0.18, 0.08)),
}


def mirror_xy(pts):
    """Left-hand traffic: the German kit mirrored in x (scale x = -1)."""
    return [(-x, y) for x, y in pts]


def mirror_yaw(yaw):
    return (math.pi - yaw) % (2 * math.pi)


def _mods():
    import bpy
    import town as TN
    import world as W
    return bpy, TN, W


class Mats:
    """Country materials (built once per scene)."""

    def __init__(self, cc):
        bpy, TN, W = _mods()
        P = PALETTE[cc]
        self.cc, self.P = cc, P
        if P["brick"]:
            self.walls = [TN.brick(f"{cc}_brick{k}", c1, c2, (0.55, 0.53, 0.5), 1.0, mortar_size=0.012, row_h=0.075,
                                   brick_w=0.23, bump=0.25, var=0.35) for k, (c1, c2) in enumerate(P["walls"])]
        else:
            self.walls = [W.noisy(f"{cc}_plaster{k}", c1, c2, 1.2, rough=0.9, bump=0.12) for k, (c1, c2) in
                          enumerate(P["walls"])]
        self.stone = W.noisy(f"{cc}_stone", (0.62, 0.58, 0.5), (0.72, 0.68, 0.6), 3.0, rough=0.85, bump=0.3)
        self.dark_stone = W.noisy(f"{cc}_stone_dark", (0.42, 0.39, 0.34), (0.5, 0.47, 0.41), 3.0, rough=0.9, bump=0.3)
        self.shutters = [TN.brick(f"{cc}_shutter{k}", col, tuple(v * 1.15 for v in col),
                                  tuple(v * 0.5 for v in col), 1.0, mortar_size=0.05, row_h=0.06, brick_w=10.0,
                                  bump=0.3, offset=0.0, var=0.05) for k, col in enumerate(P["shutters"])]
        self.frame = W.principled(f"{cc}_frame", P["frame"], 0.5)
        self.glass = W.principled(f"{cc}_glass", (0.02, 0.025, 0.03), 0.05, spec=0.9, coat=1.0)
        self.curtain = W.principled(f"{cc}_curtain", (0.75, 0.72, 0.66), 0.9)
        self.door = W.principled(f"{cc}_door", (0.18, 0.09, 0.04), 0.6)
        self.iron = W.principled(f"{cc}_iron", (0.03, 0.03, 0.03), 0.5, metal=0.6)
        self.terracotta = TN.brick(f"{cc}_roof_tiles", (0.55, 0.22, 0.1), (0.48, 0.18, 0.08), (0.2, 0.08, 0.04), 1.0,
                                   mortar_size=0.02, row_h=0.3, brick_w=0.22, bump=0.6, var=0.35, rough=0.7)
        self.slate = TN.brick(f"{cc}_slate", (0.12, 0.13, 0.15), (0.16, 0.17, 0.19), (0.05, 0.05, 0.06), 1.0,
                              mortar_size=0.012, row_h=0.22, brick_w=0.4, bump=0.4, var=0.2, rough=0.5)
        self.setts = TN.brick(f"{cc}_setts", (0.36, 0.33, 0.29), (0.48, 0.44, 0.38), (0.14, 0.13, 0.11), 1.0,
                              mortar_size=0.018, row_h=0.13, brick_w=0.16, bump=0.55, var=0.45, rough=0.8)
        self.pot = W.principled(f"{cc}_pot", (0.5, 0.22, 0.12), 0.8)
        self.white = W.principled(f"{cc}_white", (0.85, 0.85, 0.82), 0.6)


def _flip(o):
    if o.data.polygons and o.data.polygons[0].normal.z < 0:
        o.data.flip_normals()


def ground(c, name, pts, mat, z=0.0, uv=1.0):
    bpy, TN, W = _mods()
    o = W.mesh_obj(name, [(x, y, z) for x, y in pts], [tuple(range(len(pts)))], mat, c)
    _flip(o)
    TN.uv_world(o, uv)
    return o


def terrace(c, CM, p0, p1, seed=1, depth=9.0, min_w=4.5, max_w=7.5, ground_floor="mixed"):
    """A row of joined town houses with its facade on the segment p0 -> p1 and the street on the RIGHT of
    p0 -> p1. Windows with frames, sills, curtains and (south) shutters, doors, shop fronts (no signs, no text),
    plinth, cornice, roof (tiles, slate with chimney pots, or flat with a parapet and the odd stepped gable),
    drainpipes, a balcony now and then. Returns the unit roots."""
    import random
    from mathutils import Vector
    bpy, TN, W = _mods()
    rnd = random.Random(seed)
    P = CM.P
    a, b = Vector(p0), Vector(p1)
    L = (b - a).length
    u = (b - a) / L
    rz = math.atan2(u.y, u.x)
    roots, s = [], 0.0
    while s < L - 1.0:
        w = min(L - s, rnd.uniform(min_w, max_w))
        if L - s - w < 2.5:
            w = L - s
        c0 = a + u * (s + w / 2)
        g = bpy.data.objects.new(f"unit_{seed}_{len(roots)}", None)
        c.objects.link(g)
        g.location = (c0.x, c0.y, 0.0)
        g.rotation_euler = (0, 0, rz)
        roots.append(g)
        nst = rnd.randint(*P["storeys"])
        fh = 3.1
        H = 0.7 + nst * fh
        wall = rnd.choice(CM.walls)

        def B(nm, loc, size, m, bev=0.0):
            # local frame: x along the row, +y (local) away from the street; loc given with +y towards the street
            return TN.box(nm, c, (loc[0], -loc[1], loc[2]), size, m, bevel=bev, parent=g)
        B("body", (0, -depth / 2, H / 2), (w, depth, H), wall)
        B("plinth", (0, 0.04, 0.45), (w, 0.08, 0.9), CM.dark_stone)
        if P["roof"] != "flat" or rnd.random() < 0.6:
            B("cornice", (0, 0.12, H - 0.15), (w + 0.02, 0.3, 0.3), CM.stone if not P["brick"] else CM.white)
        nwin = max(1, int(w / 2.3))
        xs = [-w / 2 + (k + 0.5) * w / nwin for k in range(nwin)]
        sh = rnd.choice(CM.shutters) if CM.shutters else None
        balcony_floor = rnd.choice([None, None, 1, 2]) if not P["brick"] else None
        for fl in range(nst):
            z0 = 0.7 + fl * fh
            for kx, x in enumerate(xs):
                if fl == 0:
                    if kx == nwin // 2 and ground_floor != "shop":
                        B("door_recess", (x, -0.12, 1.25), (1.2, 0.26, 2.5), CM.door)
                        B("door_head", (x, 0.02, 2.62), (1.5, 0.08, 0.2), CM.stone)
                        continue
                    if ground_floor == "shop" or (ground_floor == "mixed" and rnd.random() < 0.35):
                        B("shop_glass", (x, -0.1, 1.55), (w / nwin - 0.5, 0.06, 2.3), CM.glass)
                        B("shop_frame", (x, -0.02, 2.75), (w / nwin - 0.3, 0.1, 0.12), CM.frame)
                        continue
                ww, wh = (0.95, 1.55) if not P["brick"] else (1.05, 1.6)
                zc = z0 + 1.45 if fl else z0 + 1.2
                B("win_glass", (x, -0.14, zc), (ww, 0.04, wh), CM.glass)
                B("win_curtain", (x, -0.18, zc + wh * 0.2), (ww * 0.9, 0.02, wh * 0.5), CM.curtain)
                B("win_frame_t", (x, -0.02, zc + wh / 2), (ww + 0.12, 0.2, 0.08), CM.frame)
                B("win_frame_b", (x, -0.02, zc - wh / 2), (ww + 0.12, 0.2, 0.08), CM.frame)
                B("win_mull", (x, -0.1, zc), (0.05, 0.06, wh), CM.frame)
                if P["brick"]:
                    B("win_bar", (x, -0.1, zc + wh * 0.05), (ww, 0.06, 0.05), CM.frame)
                B("sill", (x, 0.05, zc - wh / 2 - 0.05), (ww + 0.25, 0.14, 0.07),
                  CM.stone if not P["brick"] else CM.white)
                if sh is not None and fl > 0:
                    if rnd.random() < 0.7:
                        for sx in (-1, 1):
                            B("shutter", (x + sx * (ww / 2 + 0.27), 0.03, zc), (0.5, 0.04, wh + 0.05), sh)
                    else:
                        B("shutter_c", (x, -0.02, zc), (ww + 0.05, 0.05, wh + 0.05), sh)
                if balcony_floor == fl and kx == nwin // 2:
                    B("balcony", (x, 0.45, z0 + 0.6), (ww + 0.9, 0.9, 0.12), CM.stone)
                    for kk in range(9):
                        B("bal_bar", (x - (ww + 0.8) / 2 + kk * (ww + 0.8) / 8, 0.85, z0 + 1.15),
                          (0.025, 0.025, 0.95), CM.iron)
                    B("bal_rail", (x, 0.85, z0 + 1.62), (ww + 0.9, 0.05, 0.05), CM.iron)
        if P["roof"] == "flat":
            B("parapet", (0, 0.0, H + 0.3), (w, 0.3, 0.6), wall)
            if rnd.random() < 0.4:
                for k in range(3):
                    B("gable", (0, 0.0, H + 0.6 + k * 0.9 + 0.45), (w * (0.8 - 0.22 * k), 0.3, 0.9), wall)
        else:
            m = CM.terracotta if P["roof"] == "terracotta" else CM.slate
            tp = math.tan(math.radians(18 if P["roof"] == "terracotta" else 38))
            ov = 0.5
            vs = [(-w / 2, ov, H - ov * tp), (w / 2, ov, H - ov * tp), (w / 2, -depth / 2, H + depth / 2 * tp),
                  (-w / 2, -depth / 2, H + depth / 2 * tp)]
            run = (depth / 2 + ov) * 1.1
            o = W.mesh_obj("roof", [(x, -y, z) for x, y, z in vs], [(0, 1, 2, 3)], m, c,
                           uvs=[(0, 0), (w, 0), (w, run), (0, run)])
            o.modifiers.new("t", "SOLIDIFY").thickness = 0.12
            o.parent = g
            if P["roof"] == "slate" and rnd.random() < 0.8:
                cx = rnd.choice((-w / 2 + 0.6, w / 2 - 0.6))
                zt = H + (depth / 2 - 0.6) * tp
                B("chimney", (cx, -0.6, zt + 0.3), (0.9, 0.6, 1.6), wall)
                for k in range(2):
                    TN.cyl("pot", c, (cx - 0.2 + 0.4 * k, 0.6, zt + 1.25), 0.1, 0.4, CM.pot, verts=10).parent = g
        if rnd.random() < 0.7:
            TN.cyl("pipe", c, (w / 2 - 0.12, -0.12, H / 2), 0.05, H, CM.iron, verts=8).parent = g
        s += w
    return roots


def arch_wall(c, mat, half_open=2.4, spring=3.4, half_w=14.0, h=8.0, thick=1.2, y=0.0, name="arch_wall"):
    """A town wall across the street (along x at y) with a round-arched gate 2 * half_open wide, merlons on top."""
    import bmesh
    bpy, TN, W = _mods()
    pts = [(-half_w, 0.0), (-half_open, 0.0), (-half_open, spring)]
    for k in range(1, 24):
        a = math.pi - math.pi * k / 24
        pts.append((half_open * math.cos(a), spring + half_open * math.sin(a)))
    pts += [(half_open, spring), (half_open, 0.0), (half_w, 0.0), (half_w, h), (-half_w, h)]
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    vs = [bm.verts.new((x, y - thick / 2, z)) for x, z in pts]
    f = bm.faces.new(vs)
    r = bmesh.ops.extrude_face_region(bm, geom=[f])
    for v in [e for e in r["geom"] if isinstance(e, bmesh.types.BMVert)]:
        v.co.y += thick
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new(name, me)
    c.objects.link(o)
    me.materials.append(mat)
    uvl = me.uv_layers.new(name="UVMap")
    for poly in me.polygons:
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            uvl.data[li].uv = (co.x + co.y, co.z)
    for k in range(int(half_w * 2 / 1.6)):
        TN.box("merlon", c, (-half_w + 0.4 + k * 1.6, y, h + 0.45), (0.8, thick, 0.9), mat)
    return o


def flat(c, name, pts2d, color, loc=(0, 0, 0), rot=(math.pi / 2, 0, 0), emit=1.0, parent=None, z=0.0):
    """A flat graphic: polygon in its local xy plane (standing and facing -y by default), emissive colour."""
    bpy, TN, W = _mods()
    import jx
    if isinstance(loc, (int, float)):      # screen_pay / screen_nav pass emit as the 5th positional argument
        emit, loc = float(loc), (0, 0, 0)
    m = jx.flat_mat(name + "_m", color, emit)
    o = W.mesh_obj(name, [(x, y, z) for x, y in pts2d], [tuple(range(len(pts2d)))], m, c)
    o.location, o.rotation_euler = loc, rot
    if parent:
        o.parent = parent
    return o


def bar_pts(x0, y0, x1, y1, w):
    L = math.hypot(x1 - x0, y1 - y0)
    nx, ny = -(y1 - y0) / L * w / 2, (x1 - x0) / L * w / 2
    return [(x0 + nx, y0 + ny), (x0 - nx, y0 - ny), (x1 - nx, y1 - ny), (x1 + nx, y1 + ny)]


def disc_pts(r, n=40, cx=0.0, cy=0.0):
    return [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def arrow_pts(L=2.0, w=0.5, head=0.7, hw=0.55):
    """Straight arrow along +x from x = 0."""
    return [(0, -w / 2), (L - head, -w / 2), (L - head, -hw), (L, 0), (L - head, hw), (L - head, w / 2), (0, w / 2)]


def car_icon_pts(s=1.0):
    p = [(-1.0, 0.15), (-1.0, 0.45), (-0.55, 0.5), (-0.3, 0.85), (0.35, 0.85), (0.62, 0.5), (1.0, 0.42), (1.0, 0.15)]
    return [(x * s, y * s) for x, y in p]


def icon(c, name, kind, loc, size=1.0, rot=(math.pi / 2, 0, 0)):
    """Flat car icon on a white disc with a red cross ('no') or a green tick ('yes'); stands facing -y."""
    bpy, TN, W = _mods()
    g = bpy.data.objects.new(name, None)
    c.objects.link(g)
    g.location, g.rotation_euler = loc, rot
    g.scale = (size, size, size)
    flat(c, name + "_plate", disc_pts(1.35, 48, 0, 0.2), (0.97, 0.97, 0.95), emit=0.6, parent=g, z=-0.01)
    flat(c, name + "_car", car_icon_pts(), (0.08, 0.09, 0.1), emit=0.0, parent=g)
    for x in (-0.55, 0.55):
        flat(c, name + "_wh", disc_pts(0.2, 20, x, 0.15), (0.02, 0.02, 0.02), emit=0.0, parent=g, z=0.005)
    if kind == "no":
        for p, q in (((-0.9, -0.65), (0.9, 1.05)), ((-0.9, 1.05), (0.9, -0.65))):
            flat(c, name + "_x", bar_pts(p[0], p[1], q[0], q[1], 0.24), (0.9, 0.05, 0.05), 1.2, parent=g, z=0.01)
    else:
        for p, q in (((-0.6, 0.05), (-0.15, -0.45)), ((-0.15, -0.45), (0.8, 0.95))):
            flat(c, name + "_v", bar_pts(p[0], p[1], q[0], q[1], 0.26), (0.1, 0.75, 0.2), 1.2, parent=g, z=0.01)
    return g


def show(objs, spans_, fps=30):
    """Rendered only inside the (t0, t1) spans in seconds (hide_render keyed, constant)."""
    allo = []
    for o in (objs if isinstance(objs, (list, tuple)) else [objs]):
        allo += [o] + list(o.children_recursive)
    for o in allo:
        import stage
        if o.animation_data and any(fc.data_path == "hide_render" for fc in stage.fcurves(o)):
            continue      # keeps its own timing (a tick that appears later inside a screen)
        o.hide_render = True
        o.keyframe_insert("hide_render", frame=1)
        for t0, t1 in spans_:
            o.hide_render = False
            o.keyframe_insert("hide_render", frame=max(1, int(round(t0 * fps)) + 1))
            o.hide_render = True
            o.keyframe_insert("hide_render", frame=int(round(t1 * fps)) + 1)


def blank_plates(colls):
    """Local cars: blank plates (the German text, EU band and D removed). Heroes keep their fictional German plate."""
    bpy, TN, W = _mods()
    n = 0
    for col in colls:
        for o in list(col.all_objects):
            base = o.name.split(".")[0]
            if base.startswith("plate") and base.endswith(("_txt", "_eu", "_d")):
                bpy.data.objects.remove(o, do_unlink=True)
                n += 1
    return n


def mirror_world(colls, keep=()):
    """Left-hand traffic: mirror every top-level object of the given collections in x (world matrix scale x = -1).
    Signs, plates and any text are built AFTER this call (or kept out) so nothing reads in mirror writing; cars are
    not mirrored, they drive along mirrored paths."""
    from mathutils import Matrix
    bpy, TN, W = _mods()
    M = Matrix.Scale(-1.0, 4, (1, 0, 0))
    n = 0
    for col in colls:
        for o in list(col.all_objects):
            if o.parent is None and o.name not in keep:
                o.matrix_world = M @ o.matrix_world
                n += 1
    return n


def end_card(c, cc, ids, x0=9000.0):
    """Series end card: a road-grey card (asphalt shader, no photo) with the episode's signs as flat call-outs in a
    row (unaltered Commons files through kit/signs.py). Returns (camera position, target, ortho scale) for an
    orthographic camera; the title, follow line and source footer are captions."""
    bpy, TN, W = _mods()
    import signs as SG
    TN.box("end_card", c, (x0, 0.4, 0.0), (12.0, 0.2, 20.0), TN.town_asphalt())
    n = len(ids)
    width = min(1.9, 8.0 / max(1, n) - 0.25)
    for k, sid in enumerate(ids):
        f = SG.face(sid, c, width, cc, name=f"end_{sid}", back=False)
        f.location = (x0 + (k - (n - 1) / 2) * (width + 0.3), 0.25, -2.4 - f["height"] / 2)
    return (x0, -30.0, 0.0), (x0, 0.0, 0.0), 16.0


def drive_pieces(car, pieces, night=False, mirror=False, z=0.0):
    """Like jx.drive, but each frame may use its own path: pieces = [(path, [(s, v), ...]), ...] concatenated from
    frame 1 (one entry per frame). Between segments the car may jump (the cut hides it). mirror=True flips the
    track in x for left-hand traffic (the car itself is not mirrored, so its plate reads normally)."""
    import jx
    import motion
    locs, yaws, vs = [], [], []
    wb = 0.55 * car["L"]
    for path, sv in pieces:
        for (s, v) in sv:
            pf, _ = path.at(s + wb / 2)
            pr, _ = path.at(s - wb / 2)
            p, _ = path.at(s)
            yaw = math.atan2(pf.y - pr.y, pf.x - pr.x)
            if mirror:
                locs.append((-p.x, p.y, z))
                yaws.append(mirror_yaw(yaw))
            else:
                locs.append((p.x, p.y, z))
                yaws.append(yaw)
            vs.append(v)
    track = motion.track_from(locs, yaws, vs)
    for side, t0, t1 in car.get("blinks", []):
        jx._mark(track, side, t0, t1, 1)
    car["rig"] = motion.bake(car.get("rig") or motion.rig(car["obj"]), track, night=night, frame0=1)
    car["track"] = locs
    return car


def hold(s, n):
    return [(s, 0.0)] * n


def phone(c, name, loc, rot, screens):
    """A phone (no brand, no logo, no text) with flat screens: screens = {name: (t_spans, builder)} where builder(c,
    parent) adds flat graphics in screen coordinates (metres, x right, y up, screen 0.068 x 0.146, z = 0.0006).
    Returns the root empty (local +z is the screen normal)."""
    bpy, TN, W = _mods()
    g = bpy.data.objects.new(name, None)
    c.objects.link(g)
    g.location, g.rotation_euler = loc, rot
    body = W.principled(name + "_body", (0.03, 0.03, 0.035), 0.35, metal=0.3, coat=0.6)
    TN.box(name + "_case", c, (0, 0, -0.004), (0.074, 0.154, 0.008), body, bevel=0.003, parent=g)
    for k, (key, (spans_, build)) in enumerate(screens.items()):
        sg = bpy.data.objects.new(f"{name}_{key}", None)
        c.objects.link(sg)
        sg.parent = g
        flat(c, f"{name}_{key}_bg", [(-0.034, -0.073), (0.034, -0.073), (0.034, 0.073), (-0.034, 0.073)],
             (0.85, 0.86, 0.84), emit=0.9, rot=(0, 0, 0), parent=sg, z=0.0002 + 0.00005 * k)
        build(c, sg)
        show(sg, spans_)
    return g


def screen_nav(turn="left"):
    """Map screen: blocks, streets, a blue route that turns into a narrow street under an arch, a green
    instruction bar with a white turn arrow (no text)."""
    def b(c, p):
        z = 0.0004
        for k, (x0, y0, x1, y1) in enumerate([(-0.034, -0.073, -0.006, -0.02), (0.006, -0.073, 0.034, -0.02),
                                             (-0.034, -0.008, -0.006, 0.045), (0.006, -0.008, 0.034, 0.045)]):
            flat(c, "blk", [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], (0.93, 0.9, 0.84), 0.9, rot=(0, 0, 0), parent=p,
                 z=z)
        sgn = -1 if turn == "left" else 1
        route = [(0.0, -0.07), (0.0, -0.014), (sgn * 0.03, -0.014)] if turn else [(0.0, -0.07), (0.0, 0.045)]
        for (x0, y0), (x1, y1) in zip(route, route[1:]):
            flat(c, "route", bar_pts(x0, y0, x1, y1, 0.0055), (0.1, 0.4, 1.0), 1.2, rot=(0, 0, 0), parent=p,
                 z=z + 0.0002)
        flat(c, "me", disc_pts(0.004, 20, 0.0, -0.05), (0.1, 0.4, 1.0), 1.5, rot=(0, 0, 0), parent=p, z=z + 0.0003)
        flat(c, "bar", [(-0.034, 0.047), (0.034, 0.047), (0.034, 0.073), (-0.034, 0.073)], (0.05, 0.45, 0.25), 1.0,
             rot=(0, 0, 0), parent=p, z=z)
        # turn arrow: up then sideways
        flat(c, "arr1", bar_pts(0.0, 0.051, 0.0, 0.063, 0.004), (1, 1, 1), 1.5, rot=(0, 0, 0), parent=p, z=z + 0.0002)
        flat(c, "arr2", [(0.002, 0.061), (sgn * 0.008, 0.061), (sgn * 0.008, 0.058), (sgn * 0.014, 0.0635),
                         (sgn * 0.008, 0.069), (sgn * 0.008, 0.066), (0.002, 0.066)] if sgn > 0 else
             [(-0.002, 0.066), (-0.008, 0.066), (-0.008, 0.069), (-0.014, 0.0635), (-0.008, 0.058), (-0.008, 0.061),
              (-0.002, 0.061)], (1, 1, 1), 1.5, rot=(0, 0, 0), parent=p, z=z + 0.0002)
    return b


def screen_pay(t_tap, t_tick):
    """Payment screen: a letter icon, a green pay button, a tap ripple, then a big green tick and a yellow tag
    (no text, no numerals)."""
    def b(c, p):
        z = 0.0004
        flat(c, "env", [(-0.022, 0.02), (0.022, 0.02), (0.022, 0.05), (-0.022, 0.05)], (1, 1, 1), 1.0, rot=(0, 0, 0),
             parent=p, z=z)
        for a_, b_ in (((-0.022, 0.05), (0.0, 0.034)), ((0.0, 0.034), (0.022, 0.05))):
            flat(c, "flap", bar_pts(a_[0], a_[1], b_[0], b_[1], 0.0015), (0.4, 0.42, 0.45), 1.0, rot=(0, 0, 0),
                 parent=p, z=z + 0.0002)
        for k in range(3):
            flat(c, "line", [(-0.024, -0.002 - 0.007 * k), (0.02 - 0.01 * k, -0.002 - 0.007 * k),
                             (0.02 - 0.01 * k, -0.0045 - 0.007 * k), (-0.024, -0.0045 - 0.007 * k)], (0.6, 0.62, 0.64),
                 0.9, rot=(0, 0, 0), parent=p, z=z)
        btn = flat(c, "btn", [(-0.024, -0.05), (0.024, -0.05), (0.024, -0.034), (-0.024, -0.034)], (0.1, 0.65, 0.3),
                   1.0, rot=(0, 0, 0), parent=p, z=z)
        rip = flat(c, "ripple", disc_pts(0.008, 32, 0.0, -0.042), (1, 1, 1), 1.5, rot=(0, 0, 0), parent=p,
                   z=z + 0.0003)
        show(rip, [(t_tap, t_tap + 0.35)])
        tick = bpy_empty(c, "tick", p)
        flat(c, "tick_bg", disc_pts(0.024, 48, 0.0, 0.0), (0.1, 0.7, 0.3), 1.2, rot=(0, 0, 0), parent=tick, z=z + 0.0005)
        for a_, b_ in (((-0.012, 0.0), (-0.003, -0.009)), ((-0.003, -0.009), (0.013, 0.01))):
            flat(c, "tick_v", bar_pts(a_[0], a_[1], b_[0], b_[1], 0.0045), (1, 1, 1), 1.5, rot=(0, 0, 0), parent=tick,
                 z=z + 0.0007)
        tag = bpy_empty(c, "tag", p)
        flat(c, "tag_s", [(0.008, -0.03), (0.03, -0.03), (0.03, -0.012), (0.008, -0.012), (0.0, -0.021)],
             (1.0, 0.75, 0.0), 1.2, rot=(0, 0, 0), parent=tag, z=z + 0.0008)
        flat(c, "tag_h", disc_pts(0.0022, 16, 0.006, -0.021), (0.2, 0.2, 0.2), 0.5, rot=(0, 0, 0), parent=tag,
             z=z + 0.0009)
        show(tick, [(t_tick, 999)])
        show(tag, [(t_tick + 0.5, 999)])
        btn.name = btn.name
    return b


def sun_light(assets, az_deg=235.0, elev_deg=45.0, energy=4.0, warm=False, overcast=0.0):
    """stage.sky with the sun from azimuth az (degrees from +x, anticlockwise); warm tints the sun, overcast (0..1)
    softens it (lower energy, larger angle)."""
    from mathutils import Vector
    import stage
    a = math.radians(az_deg)
    stage.sky(None, -Vector((math.cos(a), math.sin(a), 0)), assets, sun_elev_deg=elev_deg,
              sun_energy=energy * (1 - 0.6 * overcast))
    bpy, TN, W = _mods()
    for o in bpy.data.objects:
        if o.type == "LIGHT" and o.data.type == "SUN":
            if warm:
                o.data.color = (1.0, 0.92, 0.8)
            if overcast:
                o.data.angle = math.radians(2 + 25 * overcast)


def bpy_empty(c, name, parent=None, loc=(0, 0, 0)):
    bpy, TN, W = _mods()
    e = bpy.data.objects.new(name, None)
    c.objects.link(e)
    e.location = loc
    if parent:
        e.parent = parent
    return e
