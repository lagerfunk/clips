"""Queue rendered clips in Buffer (TikTok, YouTube Shorts, Instagram Reels) through Buffer's GraphQL API.

Buffer publishes through each platform's official partner access, which is the only way an individual can post
publicly to TikTok without an audited app. Needs BUFFER_API_KEY (the owner creates it in Buffer, Settings, API, and
stores it as a GitHub secret). Each clip's file must sit at a public, direct https URL (the media branch on GitHub
Pages) that stays up until Buffer has published it.

  python -m clips.buffer channels                     list the connected channels (service and name only)
  python -m clips.buffer queue out/<job>/manifest.json --base-url https://<pages>/media/<job>
"""
import argparse
import json
import os
import time
import urllib.request

from .common import read_json, write_json

API = "https://api.buffer.com"
SERVICE = {"tiktok": "tiktok", "youtube": "youtube", "instagram": "instagram"}
YT_CATEGORY = os.environ.get("CLIPS_YT_CATEGORY", "28")  # Science & Technology; 24 Entertainment, 22 People & Blogs


def gql(query, variables=None, key=None):
    key = key or os.environ["BUFFER_API_KEY"]
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    for attempt in range(4):
        req = urllib.request.Request(API, data=body, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                time.sleep(min(60, int(e.headers.get("Retry-After", "10"))))
                continue
            raise RuntimeError(f"Buffer answered {e.code}") from None
        if data.get("errors"):
            raise RuntimeError("Buffer error: " + "; ".join(x.get("message", "?") for x in data["errors"])[:400])
        return data["data"]
    raise RuntimeError("Buffer rate limit did not clear")


def channels(key=None):
    orgs = gql("query { account { organizations { id name } } }", key=key)["account"]["organizations"]
    out = []
    for o in orgs:
        q = "query { channels(input: {organizationId: %s}) { id name service isQueuePaused } }" % json.dumps(o["id"])
        out += gql(q, key=key)["channels"]
    return out


def post_input(platform, channel_id, video_url, caption, title):
    inp = {
        "text": caption,
        "channelId": channel_id,
        "schedulingType": "automatic",
        "mode": "addToQueue",
        "assets": [{"video": {"url": video_url, "metadata": {"thumbnailOffset": 1500}}}],
    }
    if platform == "youtube":
        inp["metadata"] = {"youtube": {"title": title[:100], "categoryId": YT_CATEGORY, "madeForKids": False, "privacy": "public"}}
    elif platform == "instagram":
        inp["metadata"] = {"instagram": {"type": "reel", "shouldShareToFeed": True}}
    return inp


CREATE = """mutation($input: CreatePostInput!) {
  createPost(input: $input) {
    ... on PostActionSuccess { post { id status dueAt } }
    ... on MutationError { message }
  }
}"""


def queue(manifest_path, base_url, key=None, dry_run=False):
    m = read_json(manifest_path)
    if m.get("stage") != "rendered":
        raise SystemExit("nothing rendered yet")
    chans = {} if dry_run else {c["service"]: c for c in channels(key)}
    results = []
    for f in m["files"]:
        plat = f["platform"]
        url = f"{base_url.rstrip('/')}/{os.path.basename(f['out'])}"
        inp = post_input(plat, chans.get(SERVICE[plat], {}).get("id", "dry-run"), url, f["caption"], f["title"])
        if dry_run:
            results.append({"clip": f["clip"], "platform": plat, "input": inp})
            continue
        if SERVICE[plat] not in chans:
            results.append({"clip": f["clip"], "platform": plat, "error": "no Buffer channel connected for this platform"})
            continue
        res = gql(CREATE, {"input": inp}, key=key)["createPost"]
        if "post" in res:
            results.append({"clip": f["clip"], "platform": plat, "post": res["post"]["id"], "due": res["post"].get("dueAt")})
        else:
            results.append({"clip": f["clip"], "platform": plat, "error": res.get("message", "unknown")})
    m["queued"] = results
    write_json(manifest_path, m)
    return results


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("channels")
    q = sub.add_parser("queue")
    q.add_argument("manifest")
    q.add_argument("--base-url", required=True)
    q.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if a.cmd == "channels":
        for c in channels():
            print(f"{c['service']}: {c['name']}{' (queue paused)' if c.get('isQueuePaused') else ''}")
        return
    res = queue(a.manifest, a.base_url, dry_run=a.dry_run)
    bad = [r for r in res if "error" in r]
    for r in res:
        print(r["clip"], r["platform"], "queued" if "post" in r else ("dry run" if a.dry_run else "FAILED: " + r["error"]))
    if bad and not a.dry_run:
        raise SystemExit(f"{len(bad)} post(s) could not be queued")


if __name__ == "__main__":
    main()
