"""loud.py IN.wav OUT.wav [target_lufs] [ceiling_dbtp]
Brings a sound track to the target loudness (default -14 LUFS integrated) without letting peaks pass the ceiling
(default -1.5 dBTP). Two-pass linear loudnorm misses the target when the true-peak limit blocks the gain (episode 3
came out at -15.6 LUFS), so this applies gain plus a look-ahead limiter and re-measures until it is within 0.3 LU.
Prints the final integrated loudness and true peak."""
import json
import re
import subprocess
import sys


def measure(path):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", path, "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    s = r.stderr[r.stderr.rfind("Summary:"):]
    i = float(re.search(r"I:\s+(-?[\d.]+) LUFS", s).group(1))
    tp = float(re.search(r"Peak:\s+(-?[\d.]+|-inf) dBFS", s).group(1))
    return i, tp


def render(src, dst, gain_db, ceiling_db):
    lim = 10 ** ((ceiling_db - 0.3) / 20)
    af = (f"aresample=192000,volume={gain_db:.3f}dB,"
          f"alimiter=limit={lim:.4f}:attack=2:release=60:level=false:asc=1,aresample=48000")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-af", af, "-c:a", "pcm_s24le", dst], check=True)


def main():
    src, dst = sys.argv[1], sys.argv[2]
    target = float(sys.argv[3]) if len(sys.argv) > 3 else -14.0
    ceiling = float(sys.argv[4]) if len(sys.argv) > 4 else -1.5
    i0, _ = measure(src)
    gain = target - i0
    for _ in range(5):
        render(src, dst, gain, ceiling)
        i, tp = measure(dst)
        if abs(i - target) <= 0.3:
            break
        gain += target - i
    print(json.dumps({"lufs": i, "true_peak": tp, "gain_db": round(gain, 2)}))


if __name__ == "__main__":
    main()
