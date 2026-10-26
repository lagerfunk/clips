"""Numbers for captions, only from facts/de.json (or facts/<cc>.json) and only when VERIFIED (two independent dated
sources). Anything else returns None, so the post script must show its no-number fallback line.

    import facts as F
    D = F.load("de")
    D.fine("rvl_hinder", "en")      -> "€25"          (None unless VERIFIED)
    D.points("rvl_danger", "de")    -> "+ 1 Punkt"
    D.ban("rettungsgasse_no_corridor", "fr") -> "+ 1 mois d'interdiction de conduire"
    D.ok("shared_blame_200")        -> False unless VERIFIED
    D.used                          -> keys asked for (the episode's facts file lists them)"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _money(v, lang):
    def one(x):
        x = int(x) if float(x).is_integer() else x
        return {"en": f"€{x}", "de": f"{x} Euro", "fr": f"{x} euros"}[lang]
    if isinstance(v, (list, tuple)):
        a, b = v
        a = int(a) if float(a).is_integer() else a
        b = int(b) if float(b).is_integer() else b
        return {"en": f"€{a} to €{b}", "de": f"{a} bis {b} Euro", "fr": f"{a} à {b} euros"}[lang]
    return one(v)


class Facts:
    def __init__(self, data):
        self.data = data
        self.keys = data.get("keys", {})
        self.used = set()

    def entry(self, key):
        self.used.add(key)
        e = self.keys.get(key)
        if not e or e.get("status") != "VERIFIED":
            return None
        return e

    def ok(self, key):
        return self.entry(key) is not None

    def fine(self, key, lang="en"):
        e = self.entry(key)
        if not e or e.get("eur") in (None, [], ""):
            return None
        return _money(e["eur"], lang)

    def points(self, key, lang="en"):
        e = self.entry(key)
        if not e or not e.get("points"):
            return None
        p = int(e["points"])
        return {"en": f"+ {p} point" + ("s" if p > 1 else ""), "de": f"+ {p} Punkt" + ("e" if p > 1 else ""),
                "fr": f"+ {p} point" + ("s" if p > 1 else "")}[lang]

    def ban(self, key, lang="en"):
        e = self.entry(key)
        if not e or not e.get("ban_months"):
            return None
        m = int(e["ban_months"])
        return {"en": f"+ {m}-month ban" if m == 1 else f"+ {m}-month ban",
                "de": f"+ {m} Monat Fahrverbot" if m == 1 else f"+ {m} Monate Fahrverbot",
                "fr": f"+ {m} mois d'interdiction de conduire"}[lang]

    def value(self, key, field):
        e = self.entry(key)
        return None if not e else e.get(field)

    def sources(self, keys=None):
        """Publisher and date of every source behind the given (or used) keys, for descriptions and QA."""
        out = {}
        for k in sorted(keys or self.used):
            e = self.keys.get(k)
            if e:
                out[k] = [(s.get("publisher"), s.get("page_date"), s.get("url")) for s in e.get("sources", [])]
        return out


def load(country="de", path=None):
    p = path or os.path.join(ROOT, "facts", f"{country}.json")
    if not os.path.exists(p):
        return Facts({"keys": {}})
    return Facts(json.load(open(p, encoding="utf-8")))
