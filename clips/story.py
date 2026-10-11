"""Original narrated shorts ("story" jobs): a script of scenes becomes a 1080x1920 video with an AI voice, word-by-word
captions, a hook line and one picture per scene (product sites, thumbnails, our own cards) with a slow zoom.

No one else's video is reused, so nothing has to be downloaded from YouTube. Scene pictures come from:
  {"url": "https://..."}            an image file
  {"screenshot": "https://..."}     a phone-sized screenshot of a web page (Playwright)
  {"path": "assets/x.png"}          a file in the repo

Voice: Kokoro (open model, runs on the GitHub runner). CLIPS_FAKE_TTS=1 replaces it with silence and even word
timings, for tests without the model.
"""
import os
import subprocess
import urllib.request
from pathlib import Path

import numpy as np

from .common import OUT_H, OUT_W, probe, run, write_json
from .render import VARIANTS, build_ass

SR = 24000
GAP = 0.25          # pause between scenes, seconds
CARD_BOX = (960, 720)
CARD_TOP = 470


# ---------------- voice ----------------

def _fake_tts(text):
    words = text.split()
    per = 0.36
    audio = np.zeros(int(SR * per * max(1, len(words))), dtype=np.float32)
    return audio, [{"w": w, "s": round(i * per, 2), "e": round(i * per + per * 0.8, 2)} for i, w in enumerate(words)]


_PIPE = {}


def tts(text, voice="am_michael", speed=1.05):
    """Audio (float32, 24 kHz) for one scene."""
    if os.environ.get("CLIPS_FAKE_TTS"):
        return _fake_tts(text)[0]
    from kokoro import KPipeline  # heavy import, only on the runner
    lang = voice[0]  # a = American English, b = British English
    pipe = _PIPE.get(lang) or _PIPE.setdefault(lang, KPipeline(lang_code=lang))
    parts = [np.asarray(audio, dtype=np.float32) for _, _, audio in pipe(text, voice=voice, speed=speed)]
    return np.concatenate(parts) if parts else np.zeros(SR // 2, dtype=np.float32)


def write_wav(path, audio):
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
    import wave
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)


def narration(scenes, voice, speed):
    """One audio track for all scenes, the start and end of each scene, and the word timings."""
    chunks, bounds, words, t = [], [], [], 0.0
    for sc in scenes:
        if os.environ.get("CLIPS_FAKE_TTS"):
            audio, ws = _fake_tts(sc["say"])
            words += [{"w": w["w"], "s": w["s"] + t, "e": w["e"] + t} for w in ws]
        else:
            audio = tts(sc["say"], voice, speed)
            words += estimate_words(sc["say"], t, len(audio) / SR)
        dur = len(audio) / SR
        bounds.append((t, t + dur + GAP))
        chunks += [audio, np.zeros(int(SR * GAP), dtype=np.float32)]
        t += dur + GAP
    chunks.append(np.zeros(int(SR * 0.6), dtype=np.float32))
    bounds[-1] = (bounds[-1][0], bounds[-1][1] + 0.6)
    return np.concatenate(chunks), bounds, words


def estimate_words(text, start, dur):
    """Word timings spread over the scene by word length: the fallback when the speech model is not available."""
    ws = text.split()
    total = sum(len(w) + 2 for w in ws) or 1
    out, t = [], start + 0.05
    for w in ws:
        d = (dur - 0.1) * (len(w) + 2) / total
        out.append({"w": w, "s": round(t, 2), "e": round(t + d * 0.9, 2)})
        t += d
    return out


def word_times(wav_path, language="en"):
    from .transcribe import transcribe
    return transcribe(wav_path, language=language)["words"]


# ---------------- pictures ----------------

def fetch_image(spec, dest):
    dest = Path(dest)
    if "path" in spec:
        return Path(spec["path"])
    if "url" in spec:
        req = urllib.request.Request(spec["url"], headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            dest.write_bytes(r.read())
        return dest
    if "screenshot" in spec:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = p.chromium.launch()
            page = b.new_page(viewport={"width": 430, "height": 760}, device_scale_factor=2.5, is_mobile=True,
                              user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148")
            page.goto(spec["screenshot"], wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(int(spec.get("wait", 3000)))
            if spec.get("scroll"):
                page.mouse.wheel(0, int(spec["scroll"]))
                page.wait_for_timeout(800)
            page.screenshot(path=str(dest))
            b.close()
        return dest
    raise ValueError(f"scene picture needs url, screenshot or path: {spec}")


def plain_picture(text, dest):
    """A clean gradient card with a short text, used when a scene picture cannot be fetched."""
    from PIL import Image, ImageDraw, ImageFont
    w, h = 1200, 900
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(0, w, 4):
            c = (int(20 + 40 * x / w), int(24 + 30 * y / h), int(60 + 120 * (x + y) / (w + h)))
            for k in range(4):
                if x + k < w:
                    px[x + k, y] = c
    d = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 96)
    except OSError:
        font = ImageFont.load_default()
    box = d.textbbox((0, 0), text, font=font)
    d.text(((w - box[2]) / 2, (h - box[3]) / 2), text, font=font, fill=(255, 255, 255))
    im.save(dest)
    return Path(dest)


def card(img_path, out_png):
    """Blurred, darkened full-frame background plus the picture as a rounded card with a shadow."""
    from PIL import Image, ImageDraw, ImageFilter
    im = Image.open(img_path).convert("RGB")
    if im.height > im.width * 1.05:  # a phone screenshot: show its top part (the hero) wide, not a thin strip
        im = im.crop((0, 0, im.width, int(im.width * 0.78)))
    pad = 240  # blur a larger frame and crop, so the edges do not wash out
    bg_scale = max((OUT_W + pad) / im.width, (OUT_H + pad) / im.height)
    bg = im.resize((int(im.width * bg_scale) + 1, int(im.height * bg_scale) + 1)).filter(ImageFilter.GaussianBlur(36))
    left, top = (bg.width - OUT_W) // 2, (bg.height - OUT_H) // 2
    bg = bg.crop((left, top, left + OUT_W, top + OUT_H))
    bg = Image.blend(bg, Image.new("RGB", bg.size, (8, 10, 14)), 0.45)
    bw, bh = CARD_BOX
    s = min(bw / im.width, bh / im.height)
    fg = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
    x, y = (OUT_W - fg.width) // 2, CARD_TOP + (bh - fg.height) // 2
    shadow = Image.new("L", (fg.width + 80, fg.height + 80), 0)
    ImageDraw.Draw(shadow).rounded_rectangle((40, 40, 40 + fg.width, 40 + fg.height), 34, fill=170)
    bg.paste((0, 0, 0), (x - 40, y - 28), shadow.filter(ImageFilter.GaussianBlur(22)))
    mask = Image.new("L", fg.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, fg.width, fg.height), 28, fill=255)
    bg.paste(fg, (x, y), mask)
    bg.save(out_png)
    return out_png


def scene_clip(png, seconds, out, zoom_in=True):
    frames = max(1, round(seconds * 30))
    z = "min(zoom+0.0006,1.07)" if zoom_in else "if(eq(on,0),1.07,max(zoom-0.0006,1.0))"
    run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-i", str(png), "-t", f"{seconds:.3f}",
         "-vf", f"scale={OUT_W * 2}:{OUT_H * 2},zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={OUT_W}x{OUT_H}:fps=30,format=yuv420p",
         "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-r", "30", str(out)])
    return out


STAT_STYLE = "Style: Stat,{font},128,&H0000E1FF&,&H00FFFFFF&,&H00000000&,&H80000000&,-1,0,0,0,100,100,0,0,1,8,4,5,40,40,0,1"


def stat_events(scenes, bounds):
    """A big number or short phrase per scene ("label"), popping in under the captions."""
    from .render import _clean, ass_time
    lines = []
    for sc, (a, b) in zip(scenes, bounds):
        if sc.get("label"):
            label = _clean(sc["label"])
            size = min(128, int(980 / (0.62 * max(1, len(label)))))  # long labels shrink so they never run off the frame
            lines.append(f"Dialogue: 2,{ass_time(a + 0.15)},{ass_time(b)},Stat,,0,0,0,,"
                         f"{{\\pos(540,1430)\\fs{size}\\fad(120,120)\\fscx70\\fscy70\\t(0,160,\\fscx100\\fscy100)}}{label}")
    return lines


def with_stats(ass_text, scenes, bounds):
    from .common import FONT_NAME
    lines = stat_events(scenes, bounds)
    if not lines:
        return ass_text
    ass_text = ass_text.replace("\n\n[Events]", "\n" + STAT_STYLE.format(font=FONT_NAME) + "\n\n[Events]", 1)
    return ass_text.rstrip("\n") + "\n" + "\n".join(lines) + "\n"


# ---------------- one story ----------------

def render_story(story, work, out_dir, voice="am_michael", speed=1.05, platforms=("youtube", "tiktok", "instagram")):
    work, out_dir = Path(work), Path(out_dir)
    work.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)
    sid = story["id"]
    audio, bounds, fake_words = narration(story["scenes"], story.get("voice", voice), story.get("speed", speed))
    wav = work / f"{sid}.wav"
    write_wav(wav, audio)
    words = fake_words
    if not os.environ.get("CLIPS_FAKE_TTS"):
        try:
            words = word_times(wav) or fake_words
        except Exception as e:  # captions still work with estimated timings
            print(f"word timings from the speech model failed ({e}); using estimated timings")
    clips = []
    for i, (sc, (a, b)) in enumerate(zip(story["scenes"], bounds)):
        try:
            img = fetch_image(sc["image"], work / f"{sid}-img{i}.png")
        except Exception as e:  # one missing picture must not stop the video
            print(f"scene {i} picture failed ({str(e)[:160]}); using a plain card")
            img = plain_picture(sc.get("label") or story["hook"][:22], work / f"{sid}-img{i}.png")
        png = card(img, work / f"{sid}-card{i}.png")
        clips.append(scene_clip(png, b - a, work / f"{sid}-scene{i}.mp4", zoom_in=i % 2 == 0))
    lst = work / f"{sid}-scenes.txt"
    lst.write_text("".join(f"file '{c.resolve()}'\n" for c in clips))
    base = work / f"{sid}-base.mp4"
    run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(base)])
    duration = len(audio) / SR
    results = []
    for p in platforms:
        v = VARIANTS[p]
        ass = work / f"{sid}-{p}.ass"
        ass.write_text(with_stats(build_ass(words, duration, story["hook"], v), story["scenes"], bounds), encoding="utf-8")
        out = out_dir / f"{sid}-{p}.mp4"
        zw, zh = int(OUT_W * v["zoom"]) // 2 * 2, int(OUT_H * v["zoom"]) // 2 * 2
        run(["ffmpeg", "-y", "-v", "error", "-i", str(base), "-i", str(wav),
             "-filter_complex", f"[0:v]scale={zw}:{zh},crop={OUT_W}:{OUT_H},setsar=1,ass={ass}[v];[1:a]loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[a]",
             "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "medium", "-crf", str(v["crf"]), "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", "-metadata", f"comment=story-{p}", str(out)])
        got = probe(out)
        if (got["width"], got["height"]) != (OUT_W, OUT_H) or abs(got["duration"] - duration) > 0.8:
            raise RuntimeError(f"story render check failed for {out}: {got}, expected {duration:.1f}s")
        results.append({"out": str(out), "platform": p, "duration": round(got["duration"], 2), "layout": "story", "words": len(words)})
    return results
