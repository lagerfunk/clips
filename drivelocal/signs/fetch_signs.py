"""Download traffic-sign SVGs from Wikimedia Commons, unaltered, for the Drive Like a Local kit.
Runs on a GitHub runner (the Claude workspace cannot reach Commons): python3 drivelocal/signs/fetch_signs.py OUTDIR

Each list file drivelocal/signs/<set>.json is one set (de-core, at, it, ...), owned by one agent; the set name is
the file name:
  {"set": "de-core", "signs": [
     {"id": "205", "search": "Zeichen 205"},                       # best StVO match by title
     {"id": "1040-32", "title": "File:Zusatzzeichen 1040-32 - Parkscheibe, StVO 1992.svg"}]}   # exact file
Writes OUTDIR/<set>/<id>.svg (original bytes), <id>.png (a 1024 px librsvg rendering of that SVG, the renderer
Commons uses) and OUTDIR/<set>/sources.json + SOURCES.md (file page, author, licence, retrieval time) so every video
description can name the source. Nothing is edited: German official signs are public domain under section 5(1)
UrhG, and section 5(2) requires them unaltered with the source named.

Gentle on Wikimedia (runner IPs are shared and get HTTP 429 quickly): OUTDIR may already hold an earlier run (the
workflow checks out the branch first) and signs already there are kept, one request at a time with a pause, file
info in batches of 40 titles, Retry-After honoured on 429. Unresolved signs are listed in MISSING.txt; the workflow
publishes what it has and fails, and the next run continues where this one stopped."""
import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "lagerfunk-drivelocal/1.1 (https://github.com/lagerfunk/clips; road-rule explainer videos; "
                    "one request at a time)"}
PREFER = ["StVO 2017", "StVO 2013", "StVO 2009", "StVO 2007", "StVO 2001", "StVO 2000", "StVO 1994",
          "StVO 1992", "StVO 1988", "StVO 1970"]
AVOID = re.compile(r"\b(DDR|1938|1956|1964|1971|Vorlage|blank|leer|old|alt|Variante|sample|Skizze)\b|\.\.\.", re.I)
PAUSE_API, PAUSE_FILE = 1.5, 2.5
DEADLINE = time.time() + 35 * 60
_last = [0.0]


def _open(url, pause, timeout):
    for attempt in range(6):
        wait = _last[0] + pause - time.time()
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and time.time() < DEADLINE:
                ra = e.headers.get("Retry-After") if e.headers else None
                delay = min(120, int(ra)) if ra and ra.isdigit() else 20 * (attempt + 1)
                print(f"  {e.code}, waiting {delay} s", flush=True)
                time.sleep(delay)
                continue
            raise
        except Exception as e:  # noqa: BLE001
            print("  retry", attempt, e, flush=True)
            time.sleep(5)
    raise RuntimeError("gave up after retries: " + url[:120])


def call(**params):
    params.update(format="json", formatversion="2", maxlag="5")
    data = json.loads(_open(API + "?" + urllib.parse.urlencode(params), PAUSE_API, 30))
    if "error" in data:
        raise RuntimeError(f"API error: {data['error']}")
    return data


def rasterise(svg, png, width=1024):
    subprocess.run(["rsvg-convert", "-w", str(width), "-o", str(png), str(svg)], check=True, timeout=60)


def acceptable(entry, title):
    """A resolved title must still fit the entry: exact title, or the search prefix, no AVOID word, and every word in
    "require" (for example 215 must say Kreisverkehr: the 1970 file numbered 215 is a different sign)."""
    if entry.get("title"):
        return title == entry["title"]
    if not re.match(r"^File:" + re.escape(entry["search"]) + r"(\s|\.svg$|,)", title, re.I) or AVOID.search(title):
        return False
    return all(w.lower() in title.lower() for w in entry.get("require", []))


def resolve(entry):
    if entry.get("title"):
        return entry["title"]
    q = entry["search"]
    res = call(action="query", list="search", srnamespace=6, srlimit=100, srsearch=f'intitle:"{q}"')
    pat = re.compile(r"^File:" + re.escape(q) + r"(\s|\.svg$|,)", re.I)
    titles = [h["title"] for h in res.get("query", {}).get("search", [])
              if pat.match(h["title"]) and h["title"].lower().endswith(".svg") and acceptable(entry, h["title"])]
    if not titles:
        return None
    for p in entry.get("prefer", PREFER):
        hits = [t for t in titles if p in t]
        if hits:
            return min(hits, key=len)
    return min(titles, key=len)


def strip_html(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def write_index(d, sset, index):
    json.dump(index, open(d / "sources.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    lines = [f"# Sign sources, set {sset}", "",
             "Wikimedia Commons files, used unaltered (German signs: section 5(1) and 5(2) UrhG). Name the source "
             "in every video description.", ""]
    for k, v in sorted(index.items()):
        lines.append(f"- {k}: [{v['title'][5:]}]({v['page']}), {v['licence'] or 'see page'}"
                     f"{', ' + v['artist'] if v['artist'] else ''}, retrieved {v['retrieved']}")
    (d / "SOURCES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    out = pathlib.Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    missing = []
    try:
        call(action="query", meta="siteinfo")
        print("Commons API reachable", flush=True)
    except Exception as ex:  # noqa: BLE001
        (out / "MISSING.txt").write_text(f"Commons API not reachable from the runner: {ex}\n", encoding="utf-8")
        print("probe failed", ex)
        return
    for lf in sorted(pathlib.Path(__file__).parent.glob("*.json")):
        conf = json.load(open(lf, encoding="utf-8"))
        sset = lf.stem
        if conf.get("set", sset) != sset:
            raise SystemExit(f"{lf.name}: set must equal the file name ({sset})")
        d = out / sset
        d.mkdir(parents=True, exist_ok=True)
        idx_path = d / "sources.json"
        index = json.load(open(idx_path, encoding="utf-8")) if idx_path.exists() else {}
        rev_path = d / "REV"
        if str(conf.get("rev", 1)) != (rev_path.read_text().strip() if rev_path.exists() else "1"):
            index = {}          # list revision changed: resolve every title again
        rev_path.write_text(str(conf.get("rev", 1)) + "\n")
        wanted = {e["id"]: e for e in conf["signs"]}
        for k in list(index):
            if k not in wanted:
                index.pop(k)
        for k, e in wanted.items():
            if k in index:
                if e.get("plate"):
                    index[k]["plate"] = e["plate"]
                else:
                    index[k].pop("plate", None)
        todo = [e for e in conf["signs"] if not (e["id"] in index and (d / f"{e['id']}.png").exists()
                                                  and acceptable(e, index[e["id"]]["title"]))]
        print(f"{sset}: {len(index)} kept, {len(todo)} to fetch", flush=True)
        titles = {}
        for e in todo:
            if time.time() > DEADLINE:
                missing.append(f"{sset}/{e['id']}: not reached (time budget), next run continues")
                continue
            try:
                t = resolve(e)
                if t:
                    titles[e["id"]] = t
                else:
                    missing.append(f"{sset}/{e['id']} ({e.get('search') or e.get('title')}): no match")
            except Exception as ex:  # noqa: BLE001
                missing.append(f"{sset}/{e['id']}: resolve error {ex}")
        infos = {}
        tl = sorted(set(titles.values()))
        for i in range(0, len(tl), 40):
            try:
                res = call(action="query", titles="|".join(tl[i:i + 40]), prop="imageinfo",
                           iiprop="url|extmetadata|size|mime")
                for p in res.get("query", {}).get("pages", []):
                    if p.get("imageinfo"):
                        infos[p["title"]] = p["imageinfo"][0]
                for n in res.get("query", {}).get("normalized", []):
                    if n["to"] in infos:
                        infos[n["from"]] = infos[n["to"]]
            except Exception as ex:  # noqa: BLE001
                print("imageinfo batch failed", ex, flush=True)
        for sid, t in titles.items():
            ii = infos.get(t)
            if not ii:
                missing.append(f"{sset}/{sid} ({t}): no image info")
                continue
            if time.time() > DEADLINE:
                missing.append(f"{sset}/{sid}: not downloaded (time budget), next run continues")
                continue
            try:
                (d / f"{sid}.svg").write_bytes(_open(ii["url"], PAUSE_FILE, 60))
                rasterise(d / f"{sid}.svg", d / f"{sid}.png")
                meta = ii.get("extmetadata", {})
                index[sid] = {"title": t, "page": ii["descriptionurl"], "svg": ii["url"],
                              "width": ii.get("width"), "height": ii.get("height"),
                              "artist": strip_html(meta.get("Artist", {}).get("value")),
                              "licence": strip_html(meta.get("LicenseShortName", {}).get("value")),
                              "usage": strip_html(meta.get("UsageTerms", {}).get("value")),
                              "retrieved": time.strftime("%Y-%m-%d")}
                if wanted[sid].get("plate"):
                    index[sid]["plate"] = wanted[sid]["plate"]
                print(f"{sset}/{sid}: {t} [{index[sid]['licence']}]", flush=True)
            except Exception as ex:  # noqa: BLE001
                missing.append(f"{sset}/{sid}: download error {ex}")
            write_index(d, sset, index)
        write_index(d, sset, index)
        # discovery: real Commons file titles for search queries, so an agent can pick exact titles
        disc = conf.get("discover", [])
        if disc:
            lines = []
            for q in disc:
                try:
                    res = call(action="query", list="search", srnamespace=6, srlimit=100, srsearch=q)
                    hits = [h["title"] for h in res.get("query", {}).get("search", [])]
                    lines.append(f"## {q} ({len(hits)})")
                    lines += [f"  {t}" for t in hits]
                except Exception as ex:  # noqa: BLE001
                    lines.append(f"## {q}: error {ex}")
            (d / "DISCOVER.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "MISSING.txt").write_text("\n".join(missing) + ("\n" if missing else ""), encoding="utf-8")
    print(f"done, {len(missing)} missing", flush=True)


if __name__ == "__main__":
    main()
