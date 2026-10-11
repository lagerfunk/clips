"""Run one clipping job end to end.

  python -m clips.job jobs/<id>.json --work work --out out

1. fetch every source, 2. transcribe it (cached), 3. without picked clips: write candidates and stop,
4. with picked clips: render every clip once per platform and write manifest.json with the post text.

Job file:
{
  "id": "2026-10-12-topps",
  "campaign": {"name": "...", "board": "whop", "url": "...", "rate": "$1 per 1K", "platforms": ["tiktok", "instagram", "youtube"],
               "mustInclude": ["#ad"], "rules": ["..."]},
  "sources": [{"id": "s1", "url": "https://drive.google.com/...", "file": "optional name inside a folder"}],
  "clips": [{"id": "01", "source": "s1", "segments": [[12.0, 31.5], [40.2, 47.0]], "hook": "...", "caption": "...",
             "hashtags": ["#ad"], "title": "optional YouTube title"}]
}
"""
import argparse
import re
from pathlib import Path

from . import candidates as cand
from .common import PLATFORMS, probe, read_json, write_json
from .fetch import fetch
from .render import render

MIN_CLIP, MAX_CLIP = 8.0, 90.0
DISCLOSURE = "#ad"  # paid per view by the brand: the post is advertising and must say so (UWG § 5a, platform rules)


def _norm(t):
    return re.sub(r"[^a-z0-9$€%]+", "", t.lower())


def resolve_segment(words, seg):
    """[start, end] in seconds, or {"from": "first words", "to": "last words"} resolved against the transcript,
    so a clip can be written by quoting what is said and still cut on the exact word."""
    if isinstance(seg, (list, tuple)):
        return float(seg[0]), float(seg[1])
    toks = [_norm(w["w"]) for w in words]
    def find(phrase, start=0, last=False):
        p = [x for x in (_norm(t) for t in phrase.split()) if x]
        for i in range(start, len(toks) - len(p) + 1):
            if toks[i:i + len(p)] == p:
                return i + len(p) - 1 if last else i
        return None
    i = find(seg["from"])
    if i is None:
        raise ValueError(f"start text not found in the transcript: {seg['from']!r}")
    j = find(seg["to"], i, last=True)
    if j is None:
        raise ValueError(f"end text not found after the start: {seg['to']!r}")
    return max(0.0, words[i]["s"] - 0.12), words[j]["e"] + 0.3


def fix_words(words, fixes):
    """Correct names the speech model got wrong ("Zeng" -> "Zain") in the captions only, keeping punctuation."""
    if not fixes:
        return words
    low = {k.lower(): v for k, v in fixes.items() if k != k.upper() or len(k) < 2}
    exact = {k: v for k, v in fixes.items() if k == k.upper() and len(k) >= 2}  # all-caps keys ("ID") match exactly
    out = []
    for w in words:
        m = re.match(r"^(.*?)([.,!?;:]*)$", w["w"])
        core, tail = m.group(1), m.group(2)
        new = exact.get(core) or low.get(core.lower())
        out.append({**w, "w": (new + tail) if new else w["w"]})
    return out


def check_job(job):
    problems = []
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,60}", job.get("id", "")):
        problems.append("id: lowercase letters, digits and dashes only")
    plats = job.get("campaign", {}).get("platforms") or list(PLATFORMS)
    if any(p not in PLATFORMS for p in plats):
        problems.append(f"platforms must be among {PLATFORMS}")
    if job.get("type") == "story":
        return problems + check_stories(job)
    src_ids = {s["id"] for s in job.get("sources", [])}
    if not src_ids:
        problems.append("no sources")
    seen = set()
    for c in job.get("clips", []):
        cid = c.get("id", "?")
        if cid in seen:
            problems.append(f"clip {cid}: duplicate id")
        seen.add(cid)
        if c.get("source") not in src_ids:
            problems.append(f"clip {cid}: unknown source {c.get('source')}")
        segs = c.get("segments") or []
        if any(isinstance(x, dict) for x in segs):
            if not all(isinstance(x, dict) and x.get("from") and x.get("to") or isinstance(x, list) for x in segs):
                problems.append(f"clip {cid}: text segments need 'from' and 'to'")
            segs = []  # checked against the transcript at render time
            total = None
        else:
            total = sum(b - a for a, b in segs)
        if not (c.get("segments")) or (segs and any(b <= a for a, b in segs)):
            problems.append(f"clip {cid}: segments must be [start, end] pairs with end > start, or from/to text")
        elif total is not None and not MIN_CLIP <= total <= MAX_CLIP:
            problems.append(f"clip {cid}: {total:.1f}s long, keep it between {MIN_CLIP:.0f} and {MAX_CLIP:.0f}s")
        if not c.get("hook") or len(c["hook"]) > 90:
            problems.append(f"clip {cid}: hook missing or over 90 characters")
        if len(c.get("title") or c.get("hook", "")) > 100:
            problems.append(f"clip {cid}: YouTube title over 100 characters")
        if "—" in (c.get("hook", "") + c.get("caption", "")):
            problems.append(f"clip {cid}: no em dashes")
    return problems


def check_stories(job):
    problems, seen = [], set()
    # Owner 2026-10-11: "this is just blatant AI videos". No AI-voice slideshows: a story job needs his own recording.
    if not job.get("ownerVoice"):
        problems.append("story jobs need the owner's own voice recording (ownerVoice); AI-voice videos are off (owner 2026-10-11)")
    if not job.get("stories"):
        problems.append("story job without stories")
    for st in job.get("stories", []):
        sid = st.get("id", "?")
        if sid in seen:
            problems.append(f"story {sid}: duplicate id")
        seen.add(sid)
        if not st.get("hook") or len(st["hook"]) > 90:
            problems.append(f"story {sid}: hook missing or over 90 characters")
        scenes = st.get("scenes") or []
        if not 2 <= len(scenes) <= 12:
            problems.append(f"story {sid}: 2 to 12 scenes")
        words = sum(len(sc.get("say", "").split()) for sc in scenes)
        if not 25 <= words <= 170:
            problems.append(f"story {sid}: {words} spoken words, keep 25 to 170 (about 10 to 60 seconds)")
        for sc in scenes:
            if not sc.get("say") or not isinstance(sc.get("image"), dict):
                problems.append(f"story {sid}: every scene needs 'say' and an 'image'")
                break
        if "\u2014" in (st.get("hook", "") + st.get("caption", "") + " ".join(sc.get("say", "") for sc in scenes)):
            problems.append(f"story {sid}: no em dashes")
    return problems


def run_stories(job, work, out, only=None):
    from .story import render_story
    jid = job["id"]
    plats = job.get("campaign", {}).get("platforms") or list(PLATFORMS)
    rendered = []
    for st in job["stories"]:
        if only and st["id"] not in only:
            continue
        for res in render_story(st, Path(work) / jid, Path(out) / jid, job.get("voice", "am_michael"), job.get("speed", 1.05), plats):
            rendered.append({"clip": st["id"], **res, **post_text(job, st)})
    manifest = {"id": jid, "stage": "rendered", "campaign": job.get("campaign", {}), "files": rendered}
    write_json(Path(out) / jid / "manifest.json", manifest)
    return manifest


def post_text(job, clip):
    camp = job.get("campaign", {})
    tags = list(dict.fromkeys(clip.get("hashtags", []) + camp.get("mustInclude", [])))
    if camp.get("disclosure", True) and DISCLOSURE not in tags:
        tags.insert(0, DISCLOSURE)
    caption = (clip.get("caption") or clip["hook"]).strip()
    text = f"{caption}\n\n{' '.join(tags)}".strip()
    return {"caption": text[:2200], "title": (clip.get("title") or clip["hook"])[:100], "tags": tags}


def run_job(job_path, work="work", out="out", only=None):
    job = read_json(job_path)
    problems = check_job(job)
    if problems:
        raise SystemExit("job not valid:\n- " + "\n- ".join(problems))
    if job.get("type") == "story":
        return run_stories(job, work, out, only)
    jid = job["id"]
    wdir, odir = Path(work) / jid, Path(out) / jid
    sources, failed = {}, {}
    for s in job["sources"]:
        try:
            files = fetch(s["url"], wdir / s["id"])
        except Exception as e:  # one blocked source must not stop the others
            failed[s["id"]] = str(e)[-300:]
            print(f"source {s['id']} could not be fetched: {failed[s['id']]}")
            continue
        media = next((f for f in files if s.get("file") and f.name == s["file"]), files[0])
        tr_path = wdir / f"{s['id']}.words.json"
        saved = Path("results") / jid / f"{s['id']}.words.json"
        if not tr_path.exists() and saved.exists():
            tr_path.parent.mkdir(parents=True, exist_ok=True)
            tr_path.write_text(saved.read_text())
        if not tr_path.exists():
            from .transcribe import transcribe
            write_json(tr_path, transcribe(media, language=s.get("language")))
        sources[s["id"]] = {"media": media, "transcript": read_json(tr_path), "info": probe(media)}
    if not sources:
        write_json(odir / "manifest.json", {"id": jid, "stage": "failed", "failed": failed})
        raise SystemExit(f"no source could be fetched: {failed}")

    if not job.get("clips"):
        summary = {}
        for sid, s in sources.items():
            found = cand.find(s["transcript"], s["media"])
            write_json(odir / f"candidates-{sid}.json", found)
            summary[sid] = len(found)
        write_json(odir / "manifest.json", {"id": jid, "stage": "candidates", "candidates": summary, "failed": failed})
        return {"stage": "candidates", "candidates": summary, "failed": failed}

    plats = job.get("campaign", {}).get("platforms") or list(PLATFORMS)
    rendered = []
    for c in job["clips"]:
        if only and c["id"] not in only:
            continue
        if c["source"] not in sources:
            print(f"clip {c['id']}: source {c['source']} unavailable, skipped")
            continue
        s = sources[c["source"]]
        segs = [resolve_segment(s["transcript"]["words"], x) for x in c["segments"]]
        total = sum(b - a for a, b in segs)
        if not MIN_CLIP <= total <= MAX_CLIP:
            raise ValueError(f"clip {c['id']}: {total:.1f}s after resolving the text, keep {MIN_CLIP:.0f} to {MAX_CLIP:.0f}s")
        cap_words = fix_words(s["transcript"]["words"], job.get("fixWords"))
        for p in plats:
            res = render(s["media"], segs, cap_words, c["hook"], p,
                         odir / f"{c['id']}-{p}.mp4", c.get("layout", "auto"), wdir / "render")
            rendered.append({"clip": c["id"], **res, **post_text(job, c)})
    manifest = {"id": jid, "stage": "rendered", "campaign": job.get("campaign", {}), "files": rendered}
    write_json(odir / "manifest.json", manifest)
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("--work", default="work")
    ap.add_argument("--out", default="out")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    res = run_job(a.job, a.work, a.out, a.only)
    print({k: v for k, v in res.items() if k != "files"}, len(res.get("files", [])), "files")


if __name__ == "__main__":
    main()
