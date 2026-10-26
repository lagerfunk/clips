"""A/B table for a lookdev perf rev (plain python, ffmpeg): for every job, each variant's kept frame against the
baseline variant ("off"), as PSNR (dB) and SSIM, next to the SWEEP timings from the job's log.
Run: python3 lookdev/perf_ab.py /home/claude/assets/lookdev-out/perf/r1 [--base off]
The "off+seed" row (same settings, other noise) is the noise floor: a lever whose PSNR and SSIM are at or above it
changes nothing a viewer can tell from render noise."""
import glob
import os
import re
import subprocess
import sys


def compare(a, b):
    r = subprocess.run(["ffmpeg", "-v", "info", "-nostats", "-i", a, "-i", b, "-lavfi",
                        "[0:v][1:v]ssim;[0:v][1:v]psnr", "-f", "null", "-"], capture_output=True, text=True)
    ssim = re.search(r"SSIM .*All:([0-9.]+)", r.stderr)
    psnr = re.search(r"PSNR .*average:([0-9.inf]+)", r.stderr)
    return (float(psnr.group(1)) if psnr else None, float(ssim.group(1)) if ssim else None)


def main():
    d = sys.argv[1]
    base = sys.argv[sys.argv.index("--base") + 1] if "--base" in sys.argv else "off"
    jobs = sorted({os.path.basename(p).split("_f_")[0] for p in glob.glob(os.path.join(d, "*_f_*.png"))})
    for job in jobs:
        sweep = {}
        for lg in glob.glob(os.path.join(d, "logs", job + "_c*.txt")):
            for ln in open(lg, errors="replace"):
                if ln.startswith("SWEEP ") and "|" in ln and not ln.startswith("SWEEP variant"):
                    parts = [p.strip() for p in ln[6:].split("|")]
                    sweep[parts[0]] = parts[1:]
        pngs = sorted(glob.glob(os.path.join(d, job + "_f_*.png")))
        ref = next((p for p in pngs if p.endswith("_" + base + ".png")), None)
        print(f"\n{job}  (variant | psnr dB | ssim | first s | steady s | trace | update | denoise | save | pre)")
        for p in pngs:
            v = re.sub(r"^.*_f_\d+_", "", os.path.basename(p))[:-4]
            ps, ss = compare(ref, p) if ref and p != ref else (None, None)
            t = sweep.get(v.replace("-", "+"), [])
            print(f"  {v:22s} | {ps if ps is not None else '-':>6} | {ss if ss is not None else '-':>8} | " +
                  " | ".join(t))


if __name__ == "__main__":
    main()
