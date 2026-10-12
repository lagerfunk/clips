"""Make a job file safe for the PUBLIC clips repo: links to gated campaign material (WeTransfer, Google Drive) become
"private:<job>:<id>" (resolved at run time from the CLIP_PRIVATE_SOURCES secret, see fetch.resolve), and the
campaign's member-only brief text ("rules") is dropped. The private agency repo keeps the original job."""
import json
import sys
from pathlib import Path

from .fetch import is_private_host


def sanitize_job(job, stem):
    job = json.loads(json.dumps(job))  # deep copy
    for src in job.get("sources", []):
        if is_private_host(src.get("url", "")):
            src["url"] = f"private:{stem}:{src.get('id', 'src')}"
    for name, asset in (job.get("assets") or {}).items():
        if isinstance(asset, dict) and is_private_host(asset.get("url", "")):
            asset["url"] = f"private:{stem}:asset-{name}"
    job.pop("rules", None)
    camp = job.get("campaign")
    if isinstance(camp, dict):
        camp.pop("rules", None)
    return job


def private_table(jobs_dir):
    """key -> real url, for the CLIP_PRIVATE_SOURCES secret (printed only on the owner's request, never committed)."""
    table = {}
    for f in sorted(Path(jobs_dir).glob("*.json")):
        job = json.loads(f.read_text(encoding="utf-8"))
        clean = sanitize_job(job, f.stem)
        for a, b in zip(job.get("sources", []), clean.get("sources", [])):
            if a.get("url") != b.get("url"):
                table[b["url"][len("private:"):]] = a["url"]
        for name, asset in (job.get("assets") or {}).items():
            new = (clean.get("assets") or {}).get(name, {})
            if isinstance(asset, dict) and asset.get("url") != new.get("url"):
                table[new["url"][len("private:"):]] = asset["url"]
    return table


def main(argv):
    for f in argv:
        p = Path(f)
        job = json.loads(p.read_text(encoding="utf-8"))
        clean = sanitize_job(job, p.stem)
        if clean != job:
            p.write_text(json.dumps(clean, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(f"sanitized {p.name}")


if __name__ == "__main__":
    main(sys.argv[1:])
