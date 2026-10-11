"""Download a campaign source video: Google Drive (file or folder), a direct file URL, or a VOD page (yt-dlp).

Only sources the campaign itself provides or allows are used; the job file records where each one came from.
"""
import argparse
import shutil
import subprocess
import urllib.request
from pathlib import Path

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}


def kind_of(url):
    if Path(url).exists():
        return "file"
    if "drive.google.com" in url or "docs.google.com" in url:
        return "drive-folder" if "/folders/" in url else "drive"
    if any(h in url for h in ("youtube.com", "youtu.be", "twitch.tv", "kick.com", "tiktok.com", "instagram.com", "x.com", "twitter.com")):
        return "page"
    return "direct"


def fetch(url, dest_dir):
    """Returns the list of video files fetched (a Drive folder can hold several)."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    kind = kind_of(url)
    if kind == "file":
        target = dest / Path(url).name
        if Path(url).resolve() != target.resolve():
            shutil.copy(url, target)
        return [target]
    if kind == "drive":
        subprocess.run(["gdown", "--fuzzy", url, "-O", str(dest) + "/"], check=True)
    elif kind == "drive-folder":
        subprocess.run(["gdown", "--folder", url, "-O", str(dest)], check=True)
    elif kind == "page":
        cmd = ["yt-dlp", "-f", "bv*[height<=1080]+ba/b[height<=1080]/b", "--merge-output-format", "mp4",
               "--retries", "3", "--extractor-args", "youtube:player_client=tv_simply,web_safari,mweb,default"]
        if shutil.which("deno"):
            cmd += ["--js-runtimes", "deno"]
        subprocess.run(cmd + ["-o", str(dest / "%(id)s.%(ext)s"), url], check=True)
    else:
        name = Path(url.split("?")[0]).name or "source.mp4"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as r, open(dest / name, "wb") as f:
            shutil.copyfileobj(r, f)
    files = sorted(p for p in dest.rglob("*") if p.suffix.lower() in VIDEO_EXT)
    if not files:
        raise RuntimeError(f"no video found at {url}")
    return files


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("dest")
    a = ap.parse_args()
    for f in fetch(a.url, a.dest):
        print(f)


if __name__ == "__main__":
    main()
