"""Tighten a rendered clip so the viewer hears speech from the first frame and never sits through dead air.

Found 2026-10-18 (owner: "the start of the clip is inaudible so people will just scroll"; Instagram showed only 21 to
40% of viewers past 3 seconds): clips opened on a breath or a filler word and kept the speaker's thinking pauses (up to
1.3 s). This runs after render() on the finished file, so captions, hook and overlays stay in sync:

- the clip starts 30 ms before the first sound (or, with start > 0, at the speech after the gap nearest to `start`);
- every quiet stretch longer than MIN_PAUSE is shortened to KEEP_PAUSE (half kept on each side, short fades at each
  cut so nothing clicks);
- audio gets a gentle speech chain (high-pass, a small presence lift, light compression) and two-pass loudness to
  -14 LUFS; video is re-encoded with no chapters or metadata copied.

A recut that would fall under the campaign minimum is refused (TooShort) and the caller keeps the original render.
"""
import argparse
import json
import subprocess

SR = 16000
HOP = 0.01
MIN_PAUSE = 0.35
KEEP_PAUSE = 0.15
QUIET_BELOW_SPEECH = 24.0  # dB under the clip's speech level (90th percentile) that counts as quiet
SPEECH_CHAIN = ("highpass=f=80,equalizer=f=250:t=q:w=1.0:g=-1.5,equalizer=f=3200:t=q:w=1.2:g=2.5,"
                "acompressor=threshold=-22dB:ratio=2.5:attack=8:release=150:makeup=1")


class TooShort(ValueError):
    pass


def levels(path):
    """dB per 10 ms of the clip's mono mix."""
    import numpy as np
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le",
                          "-"], capture_output=True, check=True).stdout
    a = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768
    n = int(HOP * SR)
    k = len(a) // n
    fr = a[: k * n].reshape(k, n)
    return 20 * np.log10(np.sqrt((fr ** 2).mean(axis=1)) + 1e-9)


def quiet_spans(db, thr, min_len):
    """(start, end) seconds where the level stays under thr for at least min_len."""
    spans, s = [], None
    for i, v in enumerate(db):
        if v < thr and s is None:
            s = i
        elif v >= thr and s is not None:
            if (i - s) * HOP >= min_len:
                spans.append((s * HOP, i * HOP))
            s = None
    if s is not None and (len(db) - s) * HOP >= min_len:
        spans.append((s * HOP, len(db) * HOP))
    return spans


def plan(db, start=0.0, min_pause=MIN_PAUSE, keep_pause=KEEP_PAUSE):
    """Ranges of the clip to keep, as [(a, b)] seconds, from its level curve."""
    import numpy as np
    db = np.asarray(db)
    total = len(db) * HOP
    loud = db[db > -60]
    ref = float(np.percentile(loud, 90)) if loud.size else -20.0
    thr = ref - QUIET_BELOW_SPEECH
    if start > 0:
        near = [g for g in quiet_spans(db, thr, 0.04) if abs(g[1] - start) <= 1.2 or g[0] <= start <= g[1]]
        t0 = max(0.0, min(near, key=lambda g: abs(g[1] - start))[1] - 0.03) if near else start
    else:
        first = int(np.argmax(db > thr)) if (db > thr).any() else 0
        t0 = max(0.0, first * HOP - 0.03)
    keep, cur, half = [], t0, keep_pause / 2
    for s, e in quiet_spans(db, thr, min_pause):
        if s < t0 or e >= total - 0.3:
            continue
        keep.append((cur, s + half))
        cur = e - half
    keep.append((cur, total))
    return [(round(a, 3), round(b, 3)) for a, b in keep if b - a > 0.05]


def recut(src, out, start=0.0, min_dur=0.0, min_pause=MIN_PAUSE, keep_pause=KEEP_PAUSE, crf=19):
    """Write the tightened clip to out. Returns {"t0", "duration", "cuts"}; raises TooShort under min_dur."""
    keep = plan(levels(src), start, min_pause, keep_pause)
    dur = sum(b - a for a, b in keep)
    if dur < min_dur:
        raise TooShort(f"{dur:.1f}s after tightening, the campaign takes {min_dur:g}s or more")
    vparts, aparts = [], []
    for k, (a, b) in enumerate(keep):
        fd = min(0.012, (b - a) / 4)
        vparts.append(f"[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS[v{k}]")
        aparts.append(f"[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS,"
                      f"afade=t=in:st=0:d={fd:.3f},afade=t=out:st={max(0, b - a - fd):.3f}:d={fd:.3f}[a{k}]")
    n = len(keep)
    alabels = "".join(f"[a{k}]" for k in range(n))
    both = "".join(f"[v{k}][a{k}]" for k in range(n))
    audio = ";".join(aparts) + f";{alabels}concat=n={n}:v=0:a=1[ac0];[ac0]{SPEECH_CHAIN}[ac1]"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(src), "-filter_complex",
                        audio + ";[ac1]loudnorm=I=-14:TP=-1.5:LRA=9:print_format=json[aout]", "-map", "[aout]",
                        "-f", "null", "-"], capture_output=True, text=True, check=True)
    m = json.loads(r.stderr[r.stderr.rfind("{"): r.stderr.rfind("}") + 1])
    ln = (f"loudnorm=I=-14:TP=-1.5:LRA=9:measured_I={m['input_i']}:measured_TP={m['input_tp']}:"
          f"measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}:linear=true")
    graph = (";".join(vparts + aparts) + f";{both}concat=n={n}:v=1:a=1[vc][ac0];[ac0]{SPEECH_CHAIN}[ac1];"
             f"[ac1]{ln},aresample=48000[aout]")
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-filter_complex", graph,
                    "-map", "[vc]", "-map", "[aout]", "-map_metadata", "-1", "-map_chapters", "-1", "-dn",
                    "-c:v", "libx264", "-preset", "fast", "-crf", str(crf), "-pix_fmt", "yuv420p", "-r", "30",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2", "-movflags", "+faststart", str(out)],
                   check=True)
    return {"t0": keep[0][0], "duration": round(dur, 2), "cuts": n - 1}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--start", type=float, default=0.0, help="open at the speech after the gap nearest this second")
    ap.add_argument("--min-dur", type=float, default=0.0)
    ap.add_argument("--keep-pause", type=float, default=KEEP_PAUSE)
    ap.add_argument("--min-pause", type=float, default=MIN_PAUSE)
    a = ap.parse_args()
    print(json.dumps(recut(a.src, a.out, a.start, a.min_dur, a.min_pause, a.keep_pause)))


if __name__ == "__main__":
    main()
