"""Render one vertical clip (1080x1920) from one or more moments of a source video.

- Moments are cut and joined in the given order (a re-cut structure, not one raw copy).
- Layout: a portrait source fills the frame; a landscape source is cropped around the speaker's face when faces are
  found, otherwise shown full width on a blurred copy of itself.
- Word-by-word captions (the spoken word lights up), kept above the bottom third where the app buttons sit.
- A hook line at the top, written per clip.
- Loudness normalised to -14 LUFS. Every platform gets its own render (slightly different framing, hook position
  and encode), so no two uploads are the same file.
"""
import argparse
import math
import re
import subprocess
import tempfile
from pathlib import Path

from .common import FONT_DIR, FONT_NAME, OUT_H, OUT_W, probe, read_json, run, write_json

VARIANTS = {
    "tiktok": {"zoom": 1.00, "hook_y": 230, "cap_y": 1180, "crf": 20, "hook_colour": "&H00FFFFFF&"},
    "youtube": {"zoom": 1.03, "hook_y": 260, "cap_y": 1150, "crf": 21, "hook_colour": "&H0000FFFF&"},
    "instagram": {"zoom": 1.05, "hook_y": 300, "cap_y": 1210, "crf": 19, "hook_colour": "&H00FFFFFF&"},
}
ACTIVE = "&H0000E1FF&"  # warm yellow (ASS colours are BGR)
MAX_WORDS, MAX_CHARS = 3, 16


def _clean(text):
    return re.sub(r"[{}\\]", "", text).strip()


def ass_time(t):
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def wrap(text, width=18, max_lines=3):
    lines, cur = [], ""
    for w in _clean(text).split():
        if cur and len(cur) + 1 + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".,;:") + "..."
    return r"\N".join(lines)


def map_words(words, segments):
    """Words inside the chosen moments, moved onto the clip's own timeline."""
    out, offset = [], 0.0
    for a, b in segments:
        for w in words:
            if w["s"] >= a - 0.05 and w["e"] <= b + 0.05:
                out.append({"w": w["w"], "s": max(0.0, w["s"] - a) + offset, "e": min(b, w["e"]) - a + offset})
        offset += b - a
    return out, offset


def groups(words):
    """Split words into short caption groups (up to 3 words or 16 characters, break after punctuation)."""
    gs, cur = [], []
    for w in words:
        text = _clean(w["w"])
        if not text:
            continue
        if cur and (len(cur) >= MAX_WORDS or len(" ".join(x["t"] for x in cur)) + 1 + len(text) > MAX_CHARS):
            gs.append(cur)
            cur = []
        cur.append({"t": text, "s": w["s"], "e": w["e"]})
        if re.search(r"[.!?,;:]$", text):
            gs.append(cur)
            cur = []
    if cur:
        gs.append(cur)
    return gs


def build_ass(words, duration, hook, variant):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {OUT_W}
PlayResY: {OUT_H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,{FONT_NAME},92,&H00FFFFFF&,&H00FFFFFF&,&H00000000&,&H80000000&,-1,0,0,0,100,100,0,0,1,7,3,5,60,60,0,1
Style: Hook,{FONT_NAME},74,{variant['hook_colour']},&H00FFFFFF&,&H00000000&,&HC8000000&,-1,0,0,0,100,100,0,0,3,18,0,8,80,80,{variant['hook_y']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    if hook:
        lines.append(f"Dialogue: 1,{ass_time(0)},{ass_time(duration)},Hook,,0,0,0,,{wrap(hook)}")
    gs = groups(words)
    x, y = OUT_W // 2, variant["cap_y"]
    for gi, g in enumerate(gs):
        g_end = g[-1]["e"] + 0.25
        if gi + 1 < len(gs):
            g_end = min(g_end, gs[gi + 1][0]["s"])
        g_end = max(g_end, g[-1]["s"] + 0.12)
        for wi, w in enumerate(g):
            start = w["s"] if wi else min(w["s"], g[0]["s"])
            end = g[wi + 1]["s"] if wi + 1 < len(g) else g_end
            if end <= start:
                end = start + 0.08
            parts = [(f"{{\\c{ACTIVE}}}{x2['t'].upper()}{{\\c&H00FFFFFF&}}" if k == wi else x2["t"].upper()) for k, x2 in enumerate(g)]
            pop = r"\fscx112\fscy112\t(0,90,\fscx100\fscy100)" if wi == 0 else ""
            lines.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Cap,,0,0,0,,{{\\pos({x},{y}){pop}}}{' '.join(parts)}")
    return head + "\n".join(lines) + "\n"


_TRACKS = {}


def face_track(source, segments, info, every=0.5):
    """Piecewise crop centre (source pixels) on the clip timeline, or None when faces are not reliable.
    Cached per source and moments: every platform render of a clip reuses the same track."""
    key = (str(source), tuple(tuple(x) for x in segments))
    if key not in _TRACKS:
        _TRACKS[key] = _face_track(source, segments, info, every)
    return _TRACKS[key]


def _face_track(source, segments, info, every=0.5):
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    cascade_path = Path(getattr(cv2, "data", None).haarcascades if hasattr(cv2, "data") else "") / "haarcascade_frontalface_default.xml"
    if not cascade_path.exists():
        return None
    det = cv2.CascadeClassifier(str(cascade_path))
    sw = 640
    sh = int(round(sw * info["height"] / info["width"] / 2)) * 2
    samples, offset, hits, total = [], 0.0, 0, 0
    for a, b in segments:
        # decode only the moment, at 2 frames a second and 640 px wide: far faster than seeking frame by frame
        raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(source),
                              "-vf", f"fps={1 / every:.3f},scale={sw}:{sh}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
                             capture_output=True).stdout
        n = len(raw) // (sw * sh)
        frames = np.frombuffer(raw[: n * sw * sh], dtype=np.uint8).reshape(n, sh, sw) if n else []
        for k, frame in enumerate(frames):
            total += 1
            faces = det.detectMultiScale(frame, 1.1, 5, minSize=(40, 40))
            if len(faces):
                fx, fy, fw, fh = max(faces, key=lambda f: f[2] * f[3])
                samples.append((k * every + offset, (fx + fw / 2) * info["width"] / sw))
                hits += 1
        offset += b - a
    if total == 0 or hits / total < 0.4:
        return None
    crop_w = info["height"] * 9 / 16
    lo, hi = crop_w / 2, info["width"] - crop_w / 2
    # one-second medians, then hold a position until the face moves more than 8% of the width (looks like a camera cut)
    bins = {}
    for t, x in samples:
        bins.setdefault(int(t), []).append(x)
    steps = []
    for sec in sorted(bins):
        x = sorted(bins[sec])[len(bins[sec]) // 2]
        x = min(hi, max(lo, x))
        if not steps or (abs(x - steps[-1][1]) > 0.08 * info["width"] and sec - steps[-1][0] >= 2):
            steps.append((sec, x))
    return [(t, x - crop_w / 2) for t, x in steps]


def crop_expr(steps):
    expr = f"{steps[-1][1]:.0f}"
    for i in range(len(steps) - 1, 0, -1):
        expr = f"if(lt(t,{steps[i][0]}),{steps[i - 1][1]:.0f},{expr})"
    return expr


def render(source, segments, words, hook, platform, out, layout="auto", workdir=None):
    variant = VARIANTS[platform]
    info = probe(source)
    segments = [(float(a), float(b)) for a, b in segments]
    for a, b in segments:
        if not (0 <= a < b <= info["duration"] + 0.01):
            raise ValueError(f"moment {a}-{b} is outside the source (0-{info['duration']:.1f})")
    clip_words, duration = map_words(words, segments)
    work = Path(workdir or tempfile.mkdtemp(prefix="clip-"))
    work.mkdir(parents=True, exist_ok=True)
    ass_path = work / f"{Path(out).stem}.ass"
    ass_path.write_text(build_ass(clip_words, duration, hook, variant), encoding="utf-8")

    parts, labels = [], []
    for k, (a, b) in enumerate(segments):
        parts.append(f"[0:v]trim={a:.3f}:{b:.3f},setpts=PTS-STARTPTS,fps=30[v{k}]")
        if info["audio"]:
            parts.append(f"[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS[a{k}]")
            labels.append(f"[v{k}][a{k}]")
        else:
            labels.append(f"[v{k}]")
    n = len(segments)
    parts.append(f"{''.join(labels)}concat=n={n}:v=1:a={1 if info['audio'] else 0}[vc]" + ("[ac]" if info["audio"] else ""))

    portrait = info["width"] / info["height"] < 0.75
    z = variant["zoom"]
    mode = layout
    if layout == "auto":
        mode = "fill" if portrait else ("crop" if face_track(source, segments, info) else "fit")
    if mode == "crop":
        steps = face_track(source, segments, info) or [(0, (info["width"] - info["height"] * 9 / 16) / 2)]
        print(f"  {Path(out).name}: face crop, {len(steps)} position(s)")
        cw = int(info["height"] * 9 / 16) // 2 * 2
        parts.append(f"[vc]crop={cw}:ih:x='{crop_expr(steps)}':y=0,scale={math.ceil(OUT_W * z / 2) * 2}:{math.ceil(OUT_H * z / 2) * 2},crop={OUT_W}:{OUT_H},setsar=1[base]")
    elif mode == "fill":
        parts.append(f"[vc]scale={OUT_W * z:.0f}:{OUT_H * z:.0f}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},setsar=1[base]")
    else:  # fit: full-width video on a blurred, darkened copy of itself
        fg_w = int(OUT_W * z) // 2 * 2
        parts.append("[vc]split[bgs][fgs]")
        parts.append(f"[bgs]scale={OUT_W}:{OUT_H}:force_original_aspect_ratio=increase,crop={OUT_W}:{OUT_H},gblur=sigma=28,eq=brightness=-0.12[bg]")
        parts.append(f"[fgs]scale={fg_w}:-2[fg]")
        parts.append(f"[bg][fg]overlay=x=(W-w)/2:y=(H-h)/2-140,setsar=1[base]")
    parts.append(f"[base]ass={ass_path}:fontsdir={FONT_DIR}[vout]")
    if info["audio"]:
        parts.append("[ac]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")
    script = work / f"{Path(out).stem}.filter"
    script.write_text(";\n".join(parts), encoding="utf-8")

    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(source), "-filter_complex_script", str(script), "-map", "[vout]"]
    if info["audio"]:
        cmd += ["-map", "[aout]", "-c:a", "aac", "-b:a", "160k"]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", str(variant["crf"]), "-pix_fmt", "yuv420p", "-r", "30",
            "-movflags", "+faststart", "-metadata", f"comment=clip-{platform}", str(out)]
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    run(cmd)
    got = probe(out)
    if (got["width"], got["height"]) != (OUT_W, OUT_H) or abs(got["duration"] - duration) > 0.6:
        raise RuntimeError(f"render check failed for {out}: {got}, expected {duration:.1f}s at {OUT_W}x{OUT_H}")
    return {"out": str(out), "platform": platform, "duration": round(got["duration"], 2), "layout": mode, "words": len(clip_words)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("transcript")
    ap.add_argument("out")
    ap.add_argument("--seg", action="append", required=True, help="start:end in seconds, repeatable, in clip order")
    ap.add_argument("--hook", default="")
    ap.add_argument("--platform", default="tiktok", choices=list(VARIANTS))
    ap.add_argument("--layout", default="auto", choices=["auto", "fit", "crop", "fill"])
    a = ap.parse_args()
    segs = [tuple(float(x) for x in s.split(":")) for s in a.seg]
    res = render(a.source, segs, read_json(a.transcript)["words"], a.hook, a.platform, a.out, a.layout)
    write_json(Path(a.out).with_suffix(".json"), res)
    print(res)


if __name__ == "__main__":
    main()
