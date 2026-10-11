"""Speech to text with word timings (faster-whisper). Runs on the GitHub runner, where the model can be downloaded.

Output: {"language", "words": [{"w", "s", "e"}], "segments": [{"s", "e", "text"}]}
"""
import argparse
import os

from .common import write_json


def transcribe(media, model_size=None, language=None):
    from faster_whisper import WhisperModel  # imported here so the rest of the pipeline works without it

    model = WhisperModel(model_size or os.environ.get("CLIPS_WHISPER", "small"), device="cpu", compute_type="int8")
    segs, info = model.transcribe(str(media), word_timestamps=True, vad_filter=True, language=language)
    words, segments = [], []
    for seg in segs:
        segments.append({"s": round(seg.start, 2), "e": round(seg.end, 2), "text": seg.text.strip()})
        for w in seg.words or []:
            text = w.word.strip()
            if text:
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
