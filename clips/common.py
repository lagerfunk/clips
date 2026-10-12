"""Shared helpers for the clip pipeline: running ffmpeg, probing media, reading and writing JSON."""
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = Path(os.environ.get("CLIPS_FONT_DIR", "/usr/share/fonts/truetype/dejavu"))
FONT_NAME = os.environ.get("CLIPS_FONT_NAME", "DejaVu Sans")
OUT_W, OUT_H = 1080, 1920
PLATFORMS = ("tiktok", "youtube", "instagram")


def run(cmd, quiet=True):
    """Run a command, raise with its stderr tail when it fails."""
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "")[-1500:]
        raise RuntimeError(f"command failed ({cmd[0]}): {tail}")
    return r.stdout if quiet else r


def probe(path):
    """Duration, size and whether the file has audio."""
    out = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", "-show_chapters", str(path)])
    info = json.loads(out)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in info["streams"] if s["codec_type"] == "audio"), None)
    if v is None:
        raise ValueError(f"no video stream in {path}")
    return {
        "duration": float(info["format"]["duration"]),
        "width": int(v["width"]),
        "height": int(v["height"]),
        "audio": a is not None,
        "extra_streams": sum(1 for s in info["streams"] if s["codec_type"] not in ("video", "audio")),
        "chapters": len(info.get("chapters", [])),
    }


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
