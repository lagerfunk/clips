"""Send rendered clips to the owner's private Telegram channel, one album per clip (one file per platform), with the
text to paste. Needs TELEGRAM_BOT_TOKEN and CLIPS_CHAT_ID in the environment; neither is ever printed.

  python -m clips.deliver out/<job>/manifest.json [--dry-run]
"""
import argparse
import json
import os
import subprocess
from collections import OrderedDict
from pathlib import Path

from .common import read_json

LABEL = {"tiktok": "TikTok", "youtube": "YouTube Shorts", "instagram": "Instagram Reels"}
MAX_BYTES = 49 * 1024 * 1024  # Telegram bot upload limit is 50 MB


def albums(manifest):
    by_clip = OrderedDict()
    for f in manifest["files"]:
        by_clip.setdefault(f["clip"], []).append(f)
    out = []
    for clip, files in by_clip.items():
        first = files[0]
        text = (f"Clip {clip} | {manifest.get('campaign', {}).get('name', manifest['id'])}\n"
                f"Post on: {', '.join(LABEL[f['platform']] for f in files)}\n"
                f"YouTube title: {first['title']}\n\n{first['caption']}")
        out.append({"clip": clip, "files": files, "text": text[:1024]})
    return out


def send(album, token, chat):
    media, args = [], []
    for i, f in enumerate(album["files"]):
        size = Path(f["out"]).stat().st_size
        if size > MAX_BYTES:
            raise RuntimeError(f"{f['out']} is {size >> 20} MB, over the Telegram bot limit")
        item = {"type": "video", "media": f"attach://v{i}", "supports_streaming": True}
        if i == 0:
            item["caption"] = album["text"]
        media.append(item)
        args += ["-F", f"v{i}=@{f['out']}"]
    cmd = ["curl", "-sS", "--fail-with-body", "-X", "POST", f"https://api.telegram.org/bot{token}/sendMediaGroup",
           "-F", f"chat_id={chat}", "-F", f"media={json.dumps(media)}", *args]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0 or '"ok":true' not in r.stdout:
        body = (r.stdout or r.stderr).replace(token, "***")[:300]
        raise RuntimeError(f"Telegram refused clip {album['clip']}: {body}")


CHAT_FILE = Path(".clips-chat.enc")  # the channel id, encrypted with the bot token, so it never shows in public


def _openssl(args, data, token):
    r = subprocess.run(["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-a", "-A", *args, "-pass", "env:CLIPS_KEY"],
                       input=data, capture_output=True, text=True, env={**os.environ, "CLIPS_KEY": token})
    if r.returncode != 0:
        raise RuntimeError("could not read or store the channel id")
    return r.stdout.strip()


def find_chat(token, title="Clips"):
    """The private channel the bot was added to as admin, found from the bot's recent updates (kept 24 hours)."""
    r = subprocess.run(["curl", "-sS", f"https://api.telegram.org/bot{token}/getUpdates?allowed_updates="
                        + json.dumps(["my_chat_member", "channel_post"])], capture_output=True, text=True)
    try:
        updates = json.loads(r.stdout).get("result", [])
    except json.JSONDecodeError:
        updates = []
    for u in reversed(updates):
        chat = (u.get("my_chat_member") or u.get("channel_post") or {}).get("chat", {})
        if chat.get("type") == "channel" and chat.get("title", "").strip().lower() == title.lower():
            return str(chat["id"])
    return None


def chat_id(token):
    if os.environ.get("CLIPS_CHAT_ID"):
        return os.environ["CLIPS_CHAT_ID"]
    if CHAT_FILE.exists():
        return _openssl(["-d"], CHAT_FILE.read_text() + "\n", token)
    found = find_chat(token)
    if not found:
        raise SystemExit("No channel called 'Clips' found: add the bot to the channel as admin, post one message there, run again within 24 hours.")
    CHAT_FILE.write_text(_openssl([], found, token) + "\n")
    print("Clips channel found and stored (encrypted).")
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("manifest")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    manifest = read_json(a.manifest)
    if manifest.get("stage") != "rendered":
        raise SystemExit("nothing rendered yet")
    items = albums(manifest)
    if a.dry_run:
        for al in items:
            print(f"--- clip {al['clip']} ({len(al['files'])} files)\n{al['text']}")
        return
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is needed")
    chat = chat_id(token)
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::add-mask::{chat}")
    for al in items:
        send(al, token, chat)
        print(f"sent clip {al['clip']}")


if __name__ == "__main__":
    main()
