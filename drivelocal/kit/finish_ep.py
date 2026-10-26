"""Finish one episode: captions, sound, compose per language, per-language segment order, checks.

    python3 kit/finish_ep.py epNN RENDER.mp4 OUTDIR [--langs en,de,fr]

Expects projects/drivelocal/epNN/post_epNN.py with the same CLI as episodes 2 to 5 (`post_epNN.py OUTDIR` writes
epNN_<lang>.ass and audio_epNN.wav) and, optionally, writing OUTDIR/epNN_edit.json:
  {"title": {"en": "...", "de": "...", "fr": "..."},
   "segments": {"HOOK": [0, 2.2], "SITUATION": [2.2, 12], ...},
   "order": {"en": ["HOOK", ...], "de": [...], "fr": [...]}}
Writes OUTDIR/dlalNN-<slug>-<lang>.mp4 (1080x1920, 30 fps, -14 LUFS) and OUTDIR/work/checks_epNN.json with the
caption safe-zone result, loudness and duration of every file. Exit code 1 if a check fails."""
import glob
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def run(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def measure(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null",
                        "-"], capture_output=True, text=True)
    s = r.stderr[r.stderr.rfind("Summary:"):]
    import re
    i = float(re.search(r"I:\s+(-?[\d.]+) LUFS", s).group(1))
    tp = float(re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", s).group(1))
    d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                             capture_output=True, text=True).stdout)
    v = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate",
                        "-of", "csv=p=0", path], capture_output=True, text=True).stdout.strip()
    return {"lufs": i, "peak": tp, "seconds": round(d, 2), "video": v}


def main():
    ep, render, out = sys.argv[1], sys.argv[2], sys.argv[3]
    langs = ["en", "de", "fr"]
    if "--langs" in sys.argv:
        langs = sys.argv[sys.argv.index("--langs") + 1].split(",")
    n = ep[2:]
    work = os.path.join(out, "work")
    os.makedirs(work, exist_ok=True)
    post = os.path.join(ROOT, ep, f"post_{ep}.py")
    run([sys.executable, post, work], stdout=subprocess.DEVNULL)
    scene = sorted(glob.glob(os.path.join(ROOT, ep, f"{ep}_*.py")))
    slug = os.path.basename(scene[0])[len(ep) + 1:-3].replace("_", "-") if scene else ep
    edit = {}
    ej = os.path.join(work, f"{ep}_edit.json")
    if os.path.exists(ej):
        edit = json.load(open(ej, encoding="utf-8"))
    checks = {"ep": ep, "files": {}}
    cap = subprocess.run([sys.executable, os.path.join(ROOT, "tests", "check_captions.py")] +
                         [os.path.join(work, f"{ep}_{lang}.ass") for lang in langs], capture_output=True, text=True)
    checks["captions"] = cap.stdout.strip().splitlines()[-1]
    ok = cap.returncode == 0
    for lang in langs:
        dst = os.path.join(out, f"dlal{n}-{slug}-{lang}.mp4")
        title = edit.get("title", {}).get(lang, f"Drive Like a Local #{int(n)} ({lang})")
        tmp = dst if not edit.get("order") else dst.replace(".mp4", ".canon.mp4")
        run(["bash", os.path.join(HERE, "compose.sh"), render, os.path.join(work, f"{ep}_{lang}.ass"),
             os.path.join(work, f"audio_{ep}.wav"), tmp, title, os.path.join(ROOT, "fonts")], stdout=subprocess.DEVNULL)
        if edit.get("order"):
            order = edit["order"].get(lang) or edit["order"].get("en")
            segs = ",".join(f"{k}:{a}-{b}" for k, (a, b) in edit["segments"].items())
            run([sys.executable, os.path.join(HERE, "edit.py"), tmp, dst, segs, ",".join(order)],
                stdout=subprocess.DEVNULL)
            os.remove(tmp)
        m = measure(dst)
        m["ok"] = abs(m["lufs"] + 14) <= 0.6 and m["peak"] <= -1.0 and m["video"].startswith("1080,1920")
        ok = ok and m["ok"]
        checks["files"][os.path.basename(dst)] = m
        run(["ffmpeg", "-v", "error", "-y", "-i", dst, "-vf", "fps=1,scale=216:-1,tile=6x6", "-frames:v", "1",
             os.path.join(work, f"sheet_{ep}_{lang}.jpg")])
    checks["ok"] = ok
    json.dump(checks, open(os.path.join(work, f"checks_{ep}.json"), "w"), indent=1)
    print(json.dumps(checks, indent=1))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
