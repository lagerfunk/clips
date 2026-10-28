"""Per-language cut: the same render, captions and sound, with the shot segments in a different order per language
(owner rule: each language gets its own hook wording and its own scene order, never a clone of the English cut).

    python3 kit/edit.py IN.mp4 OUT.mp4 "HOOK:0-2.2,SITUATION:2.2-12,RULE:12-20,COST:20-25,CORRECT:25-29,END:29-32" \
        COST,HOOK,SITUATION,RULE,CORRECT,END

IN.mp4 is the composed file of one language (captions burned in on the canonical timeline, sound already at
-14 LUFS). Segments are cut on frame boundaries and joined with hard cuts and 40 ms audio fades so no click is heard;
END must stay last (it carries the end card with the source line). The output is re-measured: if the loudness moved
by more than 0.5 LU the sound is normalised again with kit/loud.py."""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def parse_segments(spec):
    segs = {}
    for part in spec.split(","):
        name, rng = part.split(":")
        a, b = (float(x) for x in rng.split("-"))
        segs[name.strip()] = (a, b)
    return segs


def cut(src, dst, segs, order, fps=30):
    if order[-1] != "END" and "END" in segs:
        raise SystemExit("END must be the last segment")
    missing = [o for o in order if o not in segs]
    if missing:
        raise SystemExit(f"unknown segments: {missing}")
    # one encode per segment, then the concat demuxer: a single filter graph with reordered trims buffers every frame
    # before the first segment it needs and runs out of memory on 7 GB (ep06 DE starts at 26.6 s)
    tmpd = tempfile.mkdtemp(prefix="dlal-edit-")
    listing = os.path.join(tmpd, "list.txt")
    with open(listing, "w") as lf:
        for i, name in enumerate(order):
            a, b = segs[name]
            fa, fb = round(a * fps), round(b * fps)
            d = (fb - fa) / fps
            seg = os.path.join(tmpd, f"s{i:02d}.mkv")
            n = fb - fa
            # the first and last frame of a segment can carry a one-frame artefact of the canonical render (a washed
            # haze frame or an overlay jump at the shot change, QA r28 Florida finals): they are replaced by clones of
            # their inner neighbours, so every segment edge is clean in every language order
            vf = (["-vf", "trim=start_frame=1:end_frame=%d,setpts=PTS-STARTPTS,"
                   "tpad=start=1:start_mode=clone:stop=1:stop_mode=clone" % (n - 1)] if n >= 6 else [])
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{fa / fps:.6f}", "-i", src, "-t", f"{d:.6f}",
                            "-frames:v", str(n)] + vf + [
                            "-af", f"afade=t=in:st=0:d=0.04,afade=t=out:st={max(0, d - 0.04):.4f}:d=0.04",
                            "-c:v", "libx264", "-crf", "18", "-preset", os.environ.get("DLAL_PRESET", "veryfast"), "-pix_fmt", "yuv420p", "-r", str(fps),
                            "-c:a", "pcm_s24le", "-ar", "48000", seg], check=True)
            lf.write(f"file '{seg}'\n")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", listing, "-c", "copy",
                    "-f", "matroska", dst + ".mkv"], check=True)
    for f in os.listdir(tmpd):
        os.remove(os.path.join(tmpd, f))
    os.rmdir(tmpd)
    # loudness after the cut, then the final mp4
    wav = tempfile.mktemp(suffix=".wav")
    norm = tempfile.mktemp(suffix=".wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", dst + ".mkv", "-vn", "-c:a", "pcm_s24le", wav], check=True)
    info = json.loads(subprocess.run([sys.executable, os.path.join(HERE, "loud.py"), wav, norm],
                                     capture_output=True, text=True, check=True).stdout.strip().splitlines()[-1])
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", dst + ".mkv", "-i", norm, "-map", "0:v", "-map", "1:a",
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", dst], check=True)
    for p in (dst + ".mkv", wav, norm):
        if os.path.exists(p):
            os.remove(p)
    return info


if __name__ == "__main__":
    src, dst, spec, order = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4].split(",")
    print(json.dumps(cut(src, dst, parse_segments(spec), order)))
