# clips

Vertical clip pipeline for paid clipping campaigns: fetch the campaign's source video, transcribe it with word
timings, find the strongest moments, and render 1080x1920 clips with word-by-word captions, a hook line and
-14 LUFS audio, one render per platform. Clips go to a private review channel; posting is done on the owner's
accounts, each post marked as an ad.

Run locally: `pip install -r requirements.txt` (plus ffmpeg), then `python -m clips.job jobs/<id>.json`.
Tests: `python -m unittest discover -s tests`.
