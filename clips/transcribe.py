"""Speech to text with word timings (faster-whisper). Runs on the GitHub runner, where the model can be downloaded.

Output: {"language", "words": [{"w", "s", "e"}], "segments": [{"s", "e", "text"}]}
"""
import argparse
import os
import subprocess

import numpy as np

from .common import write_json


def transcribe(media, model_size=None, language=None):
    from faster_whisper import WhisperModel  # imported here so the rest of the pipeline works without it

    model = WhisperModel(model_size or os.environ.get("CLIPS_WHISPER", "small"), device="cpu", compute_type="int8")
    # Decode with ffmpeg into 16 kHz mono samples ourselves: faster-whisper's own decoder breaks with newer PyAV.
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(media), "-ac", "1", "-ar", "16000", "-f", "f32le", "-"],
                         capture_output=True, check=True).stdout
    audio = np.frombuffer(raw, dtype=np.float32)
    segs, info = model.transcribe(audio, word_timestamps=True, vad_filter=True, language=language)
    words, segments = [], []
    for seg in segs:
        segments.append({"s": round(seg.start, 2), "e": round(seg.end, 2), "text": seg.text.strip()})
        for w in seg.words or []:
            text = w.word.strip()
            if not text:
                continue
            # Whisper splits "3.2" and "six-minute" into pieces without a leading space: join them back.
            if words and not w.word.startswith(" ") and (text[0] in ".,-%'" or words[-1]["w"][-1] in "-$"):
                words[-1]["w"] += text
                words[-1]["e"] = round(w.end, 2)
                continue
            words.append({"w": text, "s": round(w.start, 2), "e": round(w.end, 2)})
    return {"language": info.language, "words": words, "segments": segments}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("media")
    ap.add_argument("out")
    ap.add_argument("--model")
    ap.add_argument("--language")
    a = ap.parse_args()
    write_json(a.out, transcribe(a.media, a.model, a.language))


if __name__ == "__main__":
    main()
