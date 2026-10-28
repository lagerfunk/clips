"""Long video from finished Shorts: "Driving in Germany: the complete guide" (8 to 12 min, 1920x1080, 30 fps).

    python3 kit/longform.py plan.json OUT.mp4

plan.json:
  {"lang": "en", "title": "Driving in Germany", "subtitle": "The complete guide", "intro_s": 5, "outro_s": 6,
   "outro": ["Rules as of Oct 2026", "Sources: StVO, BKatV", "Signs: Wikimedia Commons"],
   "chapters": [{"file": "dlal02-rechts-vor-links-en.mp4", "title": "Right before left", "rule": "No sign, no light:
                 the car from the right goes first", "trim_end": 0.0}, ...]}

Each chapter: the 9:16 Short centred at full height, the same picture blurred and darkened behind it, the chapter
number and title on the left, the rule in one line on the right (all text in Montserrat, OFL). Hard cuts between
chapters. Sound: the Shorts' own synthesised sound (no voice), the whole film
normalised to -14 LUFS with kit/loud.py. Writes OUT.chapters.txt with YouTube chapter timestamps (first at 0:00)."""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(os.path.dirname(HERE), "fonts")
W, H, FPS = 1920, 1080, 30

HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Num,Montserrat Black,40,&H0000C8FF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,2,0,1,0,3,7,0,0,0,1
Style: Side,Montserrat Black,56,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,0,3,7,0,0,0,1
Style: Rule,Montserrat ExtraBold,40,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,0,3,7,0,0,0,1
Style: Big,Montserrat Black,110,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,0,4,5,0,0,0,1
Style: Mid,Montserrat ExtraBold,52,&H0000C8FF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,0,3,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def ts(t):
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def wrap(text, n):
    out, cur = [], ""
    for w in text.split():
        if cur and len(cur) + 1 + len(w) > n:
            out.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        out.append(cur)
    return "\\N".join(out)


def dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                                capture_output=True, text=True, check=True).stdout)


def true_peak(path):
    r = subprocess.run(["ffmpeg", "-nostats", "-i", path, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    vals = [float(ln.split()[1]) for ln in r.stderr.splitlines() if ln.strip().startswith("Peak:") and len(ln.split()) > 1]
    return vals[-1] if vals else 0.0


def run(cmd):
    subprocess.run(cmd, check=True)


def card(path, ass_text, seconds, tmp):
    a = os.path.join(tmp, os.path.basename(path) + ".ass")
    open(a, "w", encoding="utf-8").write(HEAD + ass_text)
    run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x111418:s={W}x{H}:d={seconds}:r={FPS}",
         "-f", "lavfi", "-i",
         # a soft synthesised two-note chime at the start of the card (sound design, no music, no voice)
         f"aevalsrc=0.20*sin(2*PI*880*t)*exp(-3*t)+0.12*sin(2*PI*1320*t)*exp(-4*t):s=48000:c=stereo:d={seconds}",
         "-t", str(seconds),
         "-vf", f"subtitles={a}:fontsdir={FONTS}", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
         "-c:a", "pcm_s24le", "-f", "matroska", path])


def chapter(path, src, n, title, rule, trim_end, tmp):
    d = dur(src) - trim_end
    ev = (f"Dialogue: 1,{ts(0.2)},{ts(d)},Num,,0,0,0,,{{\\pos(90,330)\\fad(250,0)}}CHAPTER {n}\n"
          f"Dialogue: 1,{ts(0.3)},{ts(d)},Side,,0,0,0,,{{\\pos(90,385)\\fad(250,0)}}{wrap(title, 16)}\n"
          f"Dialogue: 1,{ts(0.6)},{ts(d)},Rule,,0,0,0,,{{\\pos(1440,385)\\fad(250,0)}}{wrap(rule, 20)}\n")
    a = os.path.join(tmp, f"ch{n}.ass")
    open(a, "w", encoding="utf-8").write(HEAD + ev)
    fg_w = int(round(H * 9 / 16 / 2) * 2)
    fc = (f"[0:v]split=2[b][f];[b]scale={W}:-2,crop={W}:{H},boxblur=40:2,eq=brightness=-0.32:saturation=0.8[bg];"
          f"[f]scale={fg_w}:{H}:flags=lanczos[fg];[bg][fg]overlay=(W-w)/2:0,subtitles={a}:fontsdir={FONTS}[v]")
    run(["ffmpeg", "-v", "error", "-y", "-i", src, "-t", f"{d:.3f}", "-filter_complex", fc, "-map", "[v]",
         "-map", "0:a", "-r", str(FPS), "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
         "-c:a", "pcm_s24le", "-ar", "48000", "-ac", "2", "-f", "matroska", path])
    return d


def main():
    plan = json.load(open(sys.argv[1], encoding="utf-8"))
    out = sys.argv[2]
    base = os.path.dirname(os.path.abspath(sys.argv[1]))
    tmp = tempfile.mkdtemp(prefix="longform-")
    parts, marks, t = [], [], 0.0
    intro = os.path.join(tmp, "00_intro.mkv")
    card(intro, f"Dialogue: 1,{ts(0.2)},{ts(plan.get('intro_s', 5))},Big,,0,0,0,,{{\\pos(960,470)\\fad(300,200)}}"
         f"{plan['title']}\nDialogue: 1,{ts(0.6)},{ts(plan.get('intro_s', 5))},Mid,,0,0,0,,"
         f"{{\\pos(960,600)\\fad(300,200)}}{plan.get('subtitle', '')}\n", plan.get("intro_s", 5), tmp)
    parts.append(intro)
    t += plan.get("intro_s", 5)
    for i, ch in enumerate(plan["chapters"], 1):
        src = ch["file"] if os.path.isabs(ch["file"]) else os.path.join(base, ch["file"])
        p = os.path.join(tmp, f"{i:02d}_ch.mkv")
        # YouTube ignores a chapter list with any entry under 10 s: the intro card folds into chapter 1 (0:00) and
        # the outro card into the last chapter
        marks.append((0.0 if i == 1 else t, f"{i}. {ch['title']}"))
        t += chapter(p, src, i, ch["title"], ch["rule"], ch.get("trim_end", 0.0), tmp)
        parts.append(p)
    outro = os.path.join(tmp, "99_outro.mkv")
    lines = plan.get("outro", [])
    ev = "".join(f"Dialogue: 1,{ts(0.2 + 0.3 * k)},{ts(plan.get('outro_s', 6))},Mid,,0,0,0,,"
                 f"{{\\pos(960,{430 + 80 * k})\\fad(300,200)}}{ln}\n" for k, ln in enumerate(lines))
    card(outro, ev, plan.get("outro_s", 6), tmp)
    parts.append(outro)
    lst = os.path.join(tmp, "list.txt")
    open(lst, "w").write("".join(f"file '{p}'\n" for p in parts))
    joined = os.path.join(tmp, "joined.mkv")
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined])
    wav, norm = os.path.join(tmp, "a.wav"), os.path.join(tmp, "n.wav")
    run(["ffmpeg", "-v", "error", "-y", "-i", joined, "-vn", "-c:a", "pcm_s24le", wav])
    loud = subprocess.run([sys.executable, os.path.join(HERE, "loud.py"), wav, norm], capture_output=True, text=True,
                          check=True).stdout.strip()
    # -aac_pns 0: perceptual noise substitution let one transient overshoot to 0 dBTP after encoding (long-guide QA r2);
    # re-measure the muxed file and pull the gain down if the encode still lands above -1.5 dBTP
    gain = 0.0
    for _ in range(3):
        run(["ffmpeg", "-v", "error", "-y", "-i", joined, "-i", norm, "-map", "0:v", "-map", "1:a", "-c:v", "copy",
             "-af", f"volume={gain}dB", "-c:a", "aac", "-aac_pns", "0", "-b:a", "192k", "-movflags", "+faststart",
             "-metadata", f"title={plan['title']}", out])
        tp = true_peak(out)
        if tp <= -1.6:
            break
        gain -= tp + 1.7
    print("TRUE_PEAK", tp, "gain", round(gain, 2), flush=True)
    with open(out + ".chapters.txt", "w", encoding="utf-8") as f:
        for s, label in marks:
            f.write(f"{int(s // 60)}:{int(s % 60):02d} {label}\n")
    print(json.dumps({"out": out, "seconds": round(dur(out), 1), "loudness": json.loads(loud.splitlines()[-1])}))


if __name__ == "__main__":
    main()
