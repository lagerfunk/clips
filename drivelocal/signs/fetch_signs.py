"""Download traffic-sign SVGs from Wikimedia Commons, unaltered, for the Drive Like a Local kit.
Runs on a GitHub runner (the Claude workspace cannot reach Commons): python3 drivelocal/signs/fetch_signs.py OUTDIR

Each list file drivelocal/signs/<set>.json is one set (de-core, at, it, ...), owned by one agent; the set name is
the file name:
  {"set": "de-core", "signs": [
     {"id": "205", "search": "Zeichen 205"},                       # best StVO match by title
     {"id": "274-60", "search": "Zeichen 274-60"},
     {"id": "1040-32", "title": "File:Zusatzzeichen 1040-32 - Parkscheibe, StVO 1992.svg"}]}   # exact file
Writes OUTDIR/<set>/<id>.svg (original bytes), <id>.png (Commons' own 1024 px rendering of that SVG) and
OUTDIR/<set>/sources.json + SOURCES.md (file page, author, licence, retrieval time) so every video description can
name the source. Nothing is edited: German official signs are public domain under section 5(1) UrhG, and
section 5(2) requires them unaltered with the source named. A sign that cannot be resolved is listed as missing and
the workflow fails after pushing the rest, so a wrong title never slips through."""
import json
import pathlib
import re
import sys
import time
import urllib.parse
import urllib.request

API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "lagerfunk-drivelocal/1.0 (github.com/lagerfunk/clips; road-rule explainer videos)"}
PREFER = ["StVO 2017", "StVO 2013", "StVO 2009", "StVO 1992", "StVO 1970"]
AVOID = re.compile(r"\b(DDR|1938|1956|1964|1971|Vorlage|blank|leer|old|alt|Variante|sample)\b", re.I)


def call(**params):
    params.update(format="json", formatversion="2")
    url = API + "?" + urllib.parse.urlencode(params)
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            print("retry", attempt, e, flush=True)
            time.sleep(2 + 3 * attempt)
    raise RuntimeError("Commons API unreachable: " + url)


def get(url, dest):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                dest.write_bytes(r.read())
            return
        except Exception as e:  # noqa: BLE001
            print("retry", attempt, e, flush=True)
            time.sleep(2 + 3 * attempt)
    raise RuntimeError("download failed: " + url)


def resolve(entry):
    if entry.get("title"):
        return entry["title"]
    q = entry["search"]
    res = call(action="query", list="search", srnamespace=6, srlimit=100, srsearch=f'intitle:"{q}"')
    if "error" in res:
        raise RuntimeError(f"search error: {res['error']}")
    pat = re.compile(r"^File:" + re.escape(q) + r"(\s|\.svg$|,)", re.I)
    titles = [h["title"] for h in res.get("query", {}).get("search", [])
              if pat.match(h["title"]) and h["title"].lower().endswith(".svg") and not AVOID.search(h["title"])]
    if not titles:
        return None
    for p in entry.get("prefer", PREFER):
        hits = [t for t in titles if p in t]
        if hits:
            return min(hits, key=len)
    return min(titles, key=len)


def strip_html(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def main():
    out = pathlib.Path(sys.argv[1])
    lists = sorted(pathlib.Path(__file__).parent.glob("*.json"))
    missing = []
    for lf in lists:
        conf = json.load(open(lf, encoding="utf-8"))
        sset = lf.stem
        if conf.get("set", sset) != sset:
            raise SystemExit(f"{lf.name}: set must equal the file name ({sset})")
        d = out / sset
        d.mkdir(parents=True, exist_ok=True)
        index = {}
        for e in conf["signs"]:
            try:
                title = resolve(e)
                if not title:
                    missing.append(f"{sset}/{e['id']} ({e.get('search') or e.get('title')}): no match")
                    continue
                info = call(action="query", titles=title, prop="imageinfo", iiprop="url|extmetadata|size|mime",
                            iiurlwidth=1024)
                page = info.get("query", {}).get("pages", [{}])[0]
                if page.get("missing") or not page.get("imageinfo"):
                    missing.append(f"{sset}/{e['id']} ({title}): no image info")
                    continue
                ii = page["imageinfo"][0]
                meta = ii.get("extmetadata", {})
                get(ii["url"], d / f"{e['id']}.svg")
                get(ii["thumburl"], d / f"{e['id']}.png")
                index[e["id"]] = {
                    "title": title, "page": ii["descriptionurl"], "svg": ii["url"],
                    "width": ii.get("width"), "height": ii.get("height"),
                    "artist": strip_html(meta.get("Artist", {}).get("value")),
                    "licence": strip_html(meta.get("LicenseShortName", {}).get("value")),
                    "usage": strip_html(meta.get("UsageTerms", {}).get("value")),
                    "retrieved": time.strftime("%Y-%m-%d"),
                }
                print(f"{sset}/{e['id']}: {title} [{index[e['id']]['licence']}]", flush=True)
            except Exception as ex:  # noqa: BLE001
                missing.append(f"{sset}/{e['id']}: error {type(ex).__name__}: {ex}")
            time.sleep(0.3)
        json.dump(index, open(d / "sources.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        lines = [f"# Sign sources, set {sset}", "",
                 "Wikimedia Commons files, used unaltered (German signs: section 5(1) and 5(2) UrhG). Name the "
                 "source in every video description.", ""]
        for k, v in index.items():
            lines.append(f"- {k}: [{v['title'][5:]}]({v['page']}), {v['licence'] or 'see page'}"
                         f"{', ' + v['artist'] if v['artist'] else ''}, retrieved {v['retrieved']}")
        (d / "SOURCES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "MISSING.txt").write_text("\n".join(missing) + ("\n" if missing else ""), encoding="utf-8")
    if missing:
        print("MISSING (the workflow pushes what resolved, then fails):\n  " + "\n  ".join(missing))
    print("done")


if __name__ == "__main__":
    main()
