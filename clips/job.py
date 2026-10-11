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


def check_job(job):
    problems = []
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,60}", job.get("id", "")):
        problems.append("id: lowercase letters, digits and dashes only")
    plats = job.get("campaign", {}).get("platforms") or list(PLATFORMS)
    if any(p not in PLATFORMS for p in plats):
        problems.append(f"platforms must be among {PLATFORMS}")
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
        total = sum(b - a for a, b in segs)
        if not segs or any(b <= a for a, b in segs):
            problems.append(f"clip {cid}: segments must be [start, end] pairs with end > start")
        elif not MIN_CLIP <= total <= MAX_CLIP:
            problems.append(f"clip {cid}: {total:.1f}s long, keep it between {MIN_CLIP:.0f} and {MAX_CLIP:.0f}s")
        if not c.get("hook") or len(c["hook"]) > 90:
            problems.append(f"clip {cid}: hook missing or over 90 characters")
        if len(c.get("title") or c.get("hook", "")) > 100:
            problems.append(f"clip {cid}: YouTube title over 100 characters")
        if "—" in (c.get("hook", "") + c.get("caption", "")):
            problems.append(f"clip {cid}: no em dashes")
    return problems


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
    jid = job["id"]
    wdir, odir = Path(work) / jid, Path(out) / jid
    sources = {}
    for s in job["sources"]:
        files = fetch(s["url"], wdir / s["id"])
        media = next((f for f in files if s.get("file") and f.name == s["file"]), files[0])
        tr_path = wdir / f"{s['id']}.words.json"
        if not tr_path.exists():
            from .transcribe import transcribe
            write_json(tr_path, transcribe(media, language=s.get("language")))
        sources[s["id"]] = {"media": media, "transcript": read_json(tr_path), "info": probe(media)}

    if not job.get("clips"):
        summary = {}
        for sid, s in sources.items():
            found = cand.find(s["transcript"], s["media"])
            write_json(odir / f"candidates-{sid}.json", found)
            summary[sid] = len(found)
        write_json(odir / "manifest.json", {"id": jid, "stage": "candidates", "candidates": summary})
        return {"stage": "candidates", "candidates": summary}

    plats = job.get("campaign", {}).get("platforms") or list(PLATFORMS)
    rendered = []
    for c in job["clips"]:
        if only and c["id"] not in only:
            continue
        s = sources[c["source"]]
        for p in plats:
            res = render(s["media"], c["segments"], s["transcript"]["words"], c["hook"], p,
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
