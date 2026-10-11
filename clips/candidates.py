"""Find the moments most likely to work as a short clip.

Windows are built from whole transcript segments (so a clip starts and ends on a sentence), 18 to 45 seconds by
default, and scored on: a strong first line (question, number, money, a charged word, talking to "you"), loud or
lively audio, a clean ending, and speaking pace. The best non-overlapping windows go to candidates.json with their
text, so a person or Claude can pick the final ones and write the hook line.
"""
import argparse
import re
import subprocess

import numpy as np

from .common import probe, read_json, write_json

CHARGED = {
    "never", "always", "secret", "crazy", "insane", "nobody", "everyone", "biggest", "worst", "best", "why", "how",
    "stop", "mistake", "truth", "actually", "money", "rich", "broke", "million", "billion", "fired", "quit", "wrong",
    "lie", "lied", "honestly", "literally", "shocked", "banned", "illegal", "hate", "love", "first", "last", "only",
    "free", "dollars", "rule", "problem", "wild", "craziest", "realized", "learned", "warning", "nobody's",
}
FILLER_START = {"and", "but", "so", "because", "or", "um", "uh", "like", "which", "that"}


def energy_track(media, step=0.5):
    """RMS loudness per `step` seconds (z-scored). Empty when the file has no audio."""
    if not probe(media)["audio"]:
        return np.zeros(0), step
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(media), "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
        capture_output=True, check=True,
    ).stdout
    pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
    n = int(16000 * step)
    if len(pcm) < n:
        return np.zeros(0), step
    frames = pcm[: len(pcm) // n * n].reshape(-1, n)
    rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-9)
    db = 20 * np.log10(rms + 1e-9)
    z = (db - db.mean()) / (db.std() + 1e-6)
    return z, step


def hook_score(text):
    t = text.strip()
    words = re.findall(r"[a-zA-Z']+", t.lower())
    s = 0.0
    if "?" in t:
        s += 1.5
    if "!" in t:
        s += 0.8
    if re.search(r"\d|\$|%|€", t):
        s += 1.2
    s += 0.6 * min(3, sum(w in CHARGED for w in words))
    if words[:1] and words[0] in {"you", "your", "you're"} or " you " in f" {t.lower()} ":
        s += 0.8
    if words[:1] and words[0] in FILLER_START:
        s -= 1.5
    if len(words) > 28:
        s -= 0.7  # a long first sentence is a slow hook
    return s


def score_window(segs, energy, step):
    first, last = segs[0], segs[-1]
    dur = last["e"] - first["s"]
    text = " ".join(x["text"] for x in segs)
    n_words = len(text.split())
    pace = n_words / max(dur, 1e-6)
    s = hook_score(first["text"]) * 1.4
    s += 1.0 if re.search(r"[.!?]$", last["text"].strip()) else -1.5
    s += 0.6 if 2.2 <= pace <= 3.8 else -0.6
    if len(energy):
        a, b = int(first["s"] / step), max(int(first["s"] / step) + 1, int(last["e"] / step))
        seg_e = energy[a:b]
        if len(seg_e):
            s += 0.8 * float(seg_e.mean()) + 0.4 * float((seg_e > 1.5).sum()) / max(1.0, dur / 10)
    s += 0.15 * sum(hook_score(x["text"]) > 1.5 for x in segs[1:])  # more strong lines inside
    return round(s, 3), round(dur, 2), text


def find(transcript, media=None, min_len=18.0, max_len=45.0, top=12):
    segs = [x for x in transcript["segments"] if x["text"].strip()]
    energy, step = energy_track(media) if media else (np.zeros(0), 0.5)
    windows = []
    for i in range(len(segs)):
        for j in range(i, len(segs)):
            dur = segs[j]["e"] - segs[i]["s"]
            if dur > max_len:
                break
            if dur >= min_len:
                sc, d, text = score_window(segs[i:j + 1], energy, step)
                windows.append({"s": segs[i]["s"], "e": segs[j]["e"], "dur": d, "score": sc, "first": segs[i]["text"], "text": text})
    windows.sort(key=lambda w: -w["score"])
    picked = []
    for w in windows:
        if all(w["e"] <= p["s"] or w["s"] >= p["e"] for p in picked):
            picked.append(w)
        if len(picked) >= top:
            break
    for k, w in enumerate(picked, 1):
        w["id"] = f"c{k:02d}"
    return picked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("out")
    ap.add_argument("--media")
    ap.add_argument("--min", type=float, default=18.0)
    ap.add_argument("--max", type=float, default=45.0)
    ap.add_argument("--top", type=int, default=12)
    a = ap.parse_args()
    write_json(a.out, find(read_json(a.transcript), a.media, a.min, a.max, a.top))


if __name__ == "__main__":
    main()
