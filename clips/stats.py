"""Daily, read-only performance report for our own posts. No scraping: only the official APIs we hold keys for.

Sources, each optional and skipped when its secret is missing:
  YouTube Data API v3 with a plain API key (YT_API_KEY) for the channels in YT_CHANNEL_IDS (comma list of channel
    ids, or @handles). Path: channels.list part=contentDetails -> uploads playlist -> playlistItems.list ->
    videos.list part=statistics,contentDetails in batches of 50. Every list call costs 1 quota unit (10,000 a day by
    default); paging stops at the first page older than STATS_SINCE and at STATS_YT_MAX_UNITS.
  Buffer GraphQL (BUFFER_API_KEY): sent posts per channel with their published link and Buffer's post metrics.
    Fields verified 2026-10-11 on developers.buffer.com:
      https://developers.buffer.com/types/Post.md            Post.externalLink, sentAt, metrics, metricsUpdatedAt
      https://developers.buffer.com/types/PostMetric.md      PostMetric { type name value unit description }
      https://developers.buffer.com/types/PostMetricType.md  views, likes, reactions, comments, impressions, ...
      https://developers.buffer.com/guides/post-metrics.md   personal API key only, refreshed about once a day,
                                                              a missing metric is not a zero, marked experimental
      https://developers.buffer.com/examples/get-posts-with-metrics.md and guides/pagination.md (first/after)
    If the metrics fields are refused, links and ids are still collected.

Writes <out>/<YYYY-MM-DD>.json (one row per post) and <out>/latest.md (short owner report with the day-14 and day-28
checks), then sends latest.md to Telegram when TELEGRAM_BOT_TOKEN and CLIPS_CHAT_ID are set. Keys, the chat id and
channel ids are never printed or written.

  python -m clips.stats [--out results/stats] [--no-send]
"""
import argparse
import json
import os
import re
import statistics
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import buffer
from .common import read_json, write_json

YT_API = "https://www.googleapis.com/youtube/v3"
DEFAULT_SINCE = "2026-10-01"  # older uploads (the renamed channel has videos from years ago) are not ours to judge
SHORTS_MAX_S = 180            # YouTube Shorts can run up to 3 minutes; longer uploads are left out
YT_MAX_UNITS = int(os.environ.get("STATS_YT_MAX_UNITS") or 300)
BUFFER_PAGE, BUFFER_MAX_PAGES = 50, 20

MEDIAN_MIN = 300          # day-14 bar: median views of posts older than 48 h
OVER_K = 1000             # a post "makes it" with 1,000 views within 7 days
OVER_K_SHARE_MIN = 0.05   # day-14 bar: at least 5% of posts make it
CHECK_DAY, KILL_DAY = 14, 28
LABEL = {"youtube": "YouTube", "tiktok": "TikTok", "instagram": "Instagram"}

_SECRETS = []  # values scrubbed from every message that might be printed


def _clean(msg):
    msg = str(msg)
    for s in sorted(_SECRETS, key=len, reverse=True):
        if len(s) >= 6:  # real keys, ids and chat ids are long; a stray short value must not garble text
            msg = msg.replace(s, "***")
    return msg[:300]


def log(msg):
    print(_clean(msg), flush=True)


# ---------- YouTube ----------

def http_get_json(url):
    """GET a JSON document. Errors carry only the API's reason code, never the URL (it holds the key)."""
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        reason = ""
        try:
            err = json.loads(e.read()).get("error", {})
            reason = (err.get("errors") or [{}])[0].get("reason") or err.get("status") or ""
        except Exception:
            pass
        raise RuntimeError(f"YouTube answered {e.code} {reason}".strip()) from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"YouTube not reachable: {e.reason}") from None


class YouTube:
    def __init__(self, key, get=None, max_units=YT_MAX_UNITS):
        self.key, self.get, self.max_units, self.units = key, get or http_get_json, max_units, 0

    def call(self, method, **params):
        if self.units >= self.max_units:
            raise RuntimeError(f"YouTube quota budget of {self.max_units} units reached")
        self.units += 1  # every *.list call costs 1 unit
        q = urllib.parse.urlencode({**params, "key": self.key})
        return self.get(f"{YT_API}/{method}?{q}")


def parse_ids(raw):
    return [x.strip() for x in (raw or "").split(",") if x.strip()]


def iso_seconds(d):
    m = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?", d or "")
    if not m:
        return None
    days, h, mi, s = m.groups()
    return int(days or 0) * 86400 + int(h or 0) * 3600 + int(mi or 0) * 60 + float(s or 0)


def parse_time(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def yt_collect(key, ids, since, get=None, max_units=YT_MAX_UNITS):
    """Our Shorts published since `since`, with statistics. Returns (posts, info)."""
    yt = YouTube(key, get, max_units)
    info = {"units": 0, "channels": 0, "unresolved": 0, "errors": []}
    channels = []
    plain = [i for i in ids if not i.startswith("@")]
    try:
        if plain:
            res = yt.call("channels", part="snippet,contentDetails", id=",".join(plain[:50]), maxResults=50)
            channels += res.get("items", [])
        for h in (i for i in ids if i.startswith("@")):
            channels += yt.call("channels", part="snippet,contentDetails", forHandle=h).get("items", [])
    except Exception as e:
        info["errors"].append(_clean(e))
    info["channels"] = len(channels)
    info["unresolved"] = max(0, len(ids) - len(channels))

    videos = []  # (account, video id, published)
    for ch in channels:
        account = ch.get("snippet", {}).get("title", "YouTube channel")
        uploads = ch.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
        if not uploads:
            continue
        token = None
        for _ in range(20):
            params = {"part": "contentDetails", "playlistId": uploads, "maxResults": 50}
            if token:
                params["pageToken"] = token
            try:
                page = yt.call("playlistItems", **params)
            except Exception as e:
                info["errors"].append(_clean(e))
                break
            items = page.get("items", [])
            fresh = 0
            for it in items:
                cd = it.get("contentDetails", {})
                pub = parse_time(cd.get("videoPublishedAt"))
                if cd.get("videoId") and pub and pub >= since:
                    videos.append((account, cd["videoId"], pub))
                    fresh += 1
            token = page.get("nextPageToken")
            if not token or (items and fresh == 0):  # uploads come newest first: a page with nothing new ends it
                break

    posts = []
    for i in range(0, len(videos), 50):
        batch = videos[i:i + 50]
        try:
            res = yt.call("videos", part="statistics,contentDetails", id=",".join(v[1] for v in batch), maxResults=50)
        except Exception as e:
            info["errors"].append(_clean(e))
            break
        found = {it["id"]: it for it in res.get("items", [])}
        for account, vid, pub in batch:
            it = found.get(vid)
            if not it:
                continue  # private, deleted or still processing
            dur = iso_seconds(it.get("contentDetails", {}).get("duration"))
            if dur is not None and dur > SHORTS_MAX_S:
                continue
            st = it.get("statistics", {})
            posts.append({"platform": "youtube", "account": account, "id": vid,
                          "url": f"https://www.youtube.com/shorts/{vid}", "published": pub,
                          "views": _int(st.get("viewCount")), "likes": _int(st.get("likeCount")),
                          "comments": _int(st.get("commentCount")), "source": "youtube"})
    info["units"] = yt.units
    return posts, info


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


# ---------- Buffer ----------

METRIC_FIELDS = " metrics { type value } metricsUpdatedAt"


def posts_query(org_id, channel_ids, after, metrics):
    """Arguments are written inline (as clips.buffer does), so no input type name has to be guessed."""
    args = f"first: {BUFFER_PAGE}" + (f", after: {json.dumps(after)}" if after else "")
    filt = "{status: [sent], channelIds: [%s]}" % ", ".join(json.dumps(c) for c in channel_ids)
    return ("query { posts(%s, input: {organizationId: %s, filter: %s}) {\n"
            "  edges { node { id channelId channelService externalLink sentAt dueAt%s } }\n"
            "  pageInfo { hasNextPage endCursor }\n} }") % (args, json.dumps(org_id), filt, METRIC_FIELDS if metrics else "")


def platform_id(platform, url, fallback):
    pats = {"youtube": r"(?:shorts/|watch\?v=|youtu\.be/)([\w-]{11})", "tiktok": r"/video/(\d+)",
            "instagram": r"/(?:reel|reels|p|tv)/([\w-]+)"}
    m = re.search(pats.get(platform, r"$^"), url or "")
    return m.group(1) if m else f"buffer-{fallback}"


def buffer_collect(key, since, gql=None):
    """Sent posts from every Buffer channel since `since`. Returns (posts, info)."""
    gql = gql or buffer.gql
    info = {"channels": 0, "metrics": True, "errors": []}
    posts = []
    try:
        orgs = gql("query { account { organizations { id } } }", key=key)["account"]["organizations"]
    except Exception as e:
        info["errors"].append(_clean(e))
        return posts, info
    for org in orgs:
        try:
            q = "query { channels(input: {organizationId: %s}) { id name service } }" % json.dumps(org["id"])
            chans = {c["id"]: c for c in gql(q, key=key)["channels"]}
        except Exception as e:
            info["errors"].append(_clean(e))
            continue
        info["channels"] += len(chans)
        if not chans:
            continue
        after, fell_back = None, False
        for _ in range(BUFFER_MAX_PAGES + 1):
            try:
                data = gql(posts_query(org["id"], list(chans), after, info["metrics"]), key=key)["posts"]
            except Exception as e:
                if info["metrics"] and after is None and not fell_back:  # metrics refused (personal key only)
                    info["metrics"], fell_back = False, True
                    continue
                if fell_back and after is None:
                    info["metrics"] = True  # the plain query failed too, so metrics were not the problem
                info["errors"].append(_clean(e))
                break
            for edge in data.get("edges", []):
                n = edge["node"]
                pub = parse_time(n.get("sentAt") or n.get("dueAt"))
                if not pub or pub < since:
                    continue
                ch = chans.get(n.get("channelId"), {})
                plat = (n.get("channelService") or ch.get("service") or "other").lower()
                m = {x["type"]: x.get("value") for x in (n.get("metrics") or [])}
                views = m.get("views", m.get("impressions"))
                posts.append({"platform": plat, "account": ch.get("name", plat), "url": n.get("externalLink"),
                              "id": platform_id(plat, n.get("externalLink"), n["id"]), "published": pub,
                              "views": _int(views), "likes": _int(m.get("likes", m.get("reactions"))),
                              "comments": _int(m.get("comments")), "source": "buffer"})
            page = data.get("pageInfo", {})
            if not page.get("hasNextPage"):
                break
            after = page.get("endCursor")
    return posts, info


# ---------- maths ----------

def merge(*groups):
    """One row per (platform, id); the YouTube API's numbers win over Buffer's for the same video."""
    out = {}
    for g in groups:
        for p in g:
            k = (p["platform"], p["id"])
            if k not in out or (p["source"] == "youtube" and out[k]["source"] != "youtube"):
                out[k] = p
    return list(out.values())


def finish(posts, now):
    rows = []
    for p in posts:
        r = dict(p)
        pub = p["published"]
        r["published"] = pub.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        r["age_days"] = round((now - pub).total_seconds() / 86400, 2)
        rows.append(r)
    rows.sort(key=lambda r: (r["platform"], r["account"], r["published"]))
    return rows


def load_history(out_dir, today):
    """{(platform, id): [(age_days, views), ...]} from earlier daily files."""
    hist = {}
    for f in sorted(Path(out_dir).glob("????-??-??.json")):
        if f.stem >= today:
            continue
        try:
            rows = read_json(f).get("posts", [])
        except (OSError, ValueError):
            continue
        for r in rows:
            if r.get("views") is not None and r.get("age_days") is not None:
                hist.setdefault((r["platform"], r["id"]), []).append((r["age_days"], r["views"]))
    return hist


def views_7d(row, hist):
    """Views reached within 7 days: the best daily reading taken at age 7 days or less. When no reading that early
    exists (stats started later), today's number stands in, which can only overstate."""
    obs = hist.get((row["platform"], row["id"]), []) + [(row["age_days"], row["views"])]
    early = [v for a, v in obs if v is not None and a <= 7]
    return max(early) if early else row["views"]


def measure(rows, hist):
    old = [r["views"] for r in rows if r["views"] is not None and r["age_days"] > 2]
    week = [r for r in rows if r["views"] is not None and r["age_days"] >= 7]
    hits = sum(1 for r in week if (views_7d(r, hist) or 0) >= OVER_K)
    return {"median_48h": statistics.median(old) if old else None, "n_48h": len(old),
            "share_7d": hits / len(week) if week else None, "hit_7d": hits, "n_7d": len(week)}


def passes(m):
    if m["median_48h"] is None or m["share_7d"] is None:
        return None
    return m["median_48h"] >= MEDIAN_MIN and m["share_7d"] >= OVER_K_SHARE_MIN


def check(rows, hist, now):
    """Day counted from the account's first post. Day 14: pass or reformat. Day 28: pass or kill, judged on the
    posts made from day 14 on (the reformatted ones) when any of them is a week old, else on all posts."""
    first = min(parse_time(r["published"]) for r in rows)
    day = int((now - first).total_seconds() // 86400)
    if day < CHECK_DAY:
        when = (first + timedelta(days=CHECK_DAY)).strftime("%Y-%m-%d")
        return day, {"status": "early", "text": f"day {CHECK_DAY} check due {when}"}
    scope, judged = "all posts", rows
    if day >= KILL_DAY:
        later = [r for r in rows if parse_time(r["published"]) >= first + timedelta(days=CHECK_DAY)]
        if any(r["age_days"] >= 7 and r["views"] is not None for r in later):
            scope, judged = f"posts since day {CHECK_DAY}", later
    m = measure(judged, hist)
    ok = passes(m)
    bar = f"median {MEDIAN_MIN}+ and {OVER_K_SHARE_MIN:.0%}+ over {OVER_K:,} views in 7 days"
    if ok is None:
        return day, {"status": "no-data", "text": f"not enough data yet ({bar})"}
    if ok:
        return day, {"status": "pass", "text": f"PASS, keep going ({bar}, {scope})"}
    if day >= KILL_DAY:
        return day, {"status": "kill", "text": f"KILL flag, stop this account's format ({bar} missed, {scope})"}
    return day, {"status": "reformat", "text": f"REFORMAT ({bar} missed)"}


def summarise(rows, hist, now):
    accounts = {}
    for r in rows:
        accounts.setdefault((r["platform"], r["account"]), []).append(r)
    out = []
    for (plat, acc), rs in sorted(accounts.items()):
        m = measure(rs, hist)
        day, chk = check(rs, hist, now)
        known = [r for r in rs if r["views"] is not None]
        best = sorted(known, key=lambda r: -r["views"])[:3]
        out.append({"platform": plat, "account": acc, "posts": len(rs), "with_views": len(known),
                    "total_views": sum(r["views"] for r in known), "day": day, "check": chk,
                    "best": [{"views": r["views"], "url": r["url"]} for r in best], **m})
    return out


# ---------- report ----------

def _n(v):
    return f"{int(round(v)):,}"


def render_md(summary, date, notes):
    lines = [f"# Clip stats {date}", ""]
    if not summary:
        lines += ["No posts found yet.", ""]
    for s in summary:
        lines.append(f"## {s['account']} on {LABEL.get(s['platform'], s['platform'].title())} (day {s['day']})")
        if not s["with_views"]:
            lines.append(f"- Posts: {s['posts']}, views not available from this source yet")
        else:
            lines.append(f"- Posts: {s['posts']}, total views: {_n(s['total_views'])}"
                         + ("" if s["with_views"] == s["posts"] else f" (views known for {s['with_views']})"))
            lines.append("- Median views, posts older than 48 h: " + (
                f"{_n(s['median_48h'])} ({s['n_48h']} posts)" if s["median_48h"] is not None else "no post that old yet"))
            lines.append(f"- Over {OVER_K:,} views within 7 days: " + (
                f"{s['hit_7d']} of {s['n_7d']} ({s['share_7d']:.0%})" if s["share_7d"] is not None else "no post 7 days old yet"))
        lines.append(f"- Check: {s['check']['text']}")
        for b in s["best"]:
            lines.append(f"- Best: {_n(b['views'])} views {b['url'] or '(no link)'}")
        lines.append("")
    lines += [f"Sources: {'; '.join(notes)}.", ""]
    text = "\n".join(lines)
    return text.replace("\u2014", ",").replace("\u2013", "-")  # never an em or en dash in owner text


# ---------- Telegram ----------

def send_telegram(text, token, chat, post=None):
    data = urllib.parse.urlencode({"chat_id": chat, "text": text[:4000], "disable_web_page_preview": "true"}).encode()
    if post:
        return post(data)
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            ok = json.loads(r.read()).get("ok")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Telegram answered {e.code}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"Telegram not reachable: {e.reason}") from None
    if not ok:
        raise RuntimeError("Telegram refused the message")


# ---------- main ----------

def run(out_dir, env, now=None, send=True, yt_get=None, gql=None, tg_post=None):
    """Returns the exit code: 0 fine, 2 when a configured source or the Telegram send failed (files still written)."""
    now = now or datetime.now(timezone.utc)
    since = datetime.fromisoformat((env.get("STATS_SINCE") or DEFAULT_SINCE)[:10]).replace(tzinfo=timezone.utc)
    yt_key, ids, buf_key = env.get("YT_API_KEY"), parse_ids(env.get("YT_CHANNEL_IDS")), env.get("BUFFER_API_KEY")
    _SECRETS[:] = [s for s in (yt_key, buf_key, env.get("TELEGRAM_BOT_TOKEN"), env.get("CLIPS_CHAT_ID"), *ids) if s]
    groups, notes, failed = [], [], False
    sources = {}

    if yt_key and ids:
        posts, info = yt_collect(yt_key, ids, since, get=yt_get)
        groups.append(posts)
        sources["youtube"] = {"posts": len(posts), "channels": info["channels"], "units": info["units"],
                              "errors": info["errors"]}
        note = f"YouTube {len(posts)} posts from {info['channels']} channel(s), {info['units']} quota units"
        if info["unresolved"]:
            note += f", {info['unresolved']} channel id(s) not found"
        if info["errors"]:
            failed, note = True, note + ", error: " + info["errors"][0]
        notes.append(note)
    else:
        why = "no YT_API_KEY" if not yt_key else "no YT_CHANNEL_IDS"
        sources["youtube"] = {"skipped": why}
        notes.append(f"YouTube skipped ({why})")

    if buf_key:
        posts, info = buffer_collect(buf_key, since, gql=gql)
        groups.append(posts)
        sources["buffer"] = {"posts": len(posts), "channels": info["channels"], "metrics": info["metrics"],
                             "errors": info["errors"]}
        note = f"Buffer {len(posts)} posts from {info['channels']} channel(s)"
        if not info["metrics"]:
            note += ", links only (metrics not available for this key)"
        if info["errors"]:
            failed, note = True, note + ", error: " + info["errors"][0]
        notes.append(note)
    else:
        sources["buffer"] = {"skipped": "no BUFFER_API_KEY"}
        notes.append("Buffer skipped (no BUFFER_API_KEY)")

    if not groups:
        log("No stats source configured (YT_API_KEY with YT_CHANNEL_IDS, or BUFFER_API_KEY): nothing to do.")
        return 0

    date = now.strftime("%Y-%m-%d")
    rows = finish(merge(*groups), now)
    hist = load_history(out_dir, date)
    summary = summarise(rows, hist, now)
    md = render_md(summary, date, notes)
    write_json(Path(out_dir) / f"{date}.json", {"date": date, "generated": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                                 "since": since.strftime("%Y-%m-%d"), "sources": sources,
                                                 "posts": rows})
    (Path(out_dir) / "latest.md").write_text(md, encoding="utf-8")
    for n in notes:
        log(n)
    log(f"Wrote {len(rows)} posts, {len(summary)} account(s) to {out_dir}")

    token, chat = env.get("TELEGRAM_BOT_TOKEN"), env.get("CLIPS_CHAT_ID")
    if send and token and chat:
        try:
            send_telegram(md, token, chat, post=tg_post)
            log("Report sent to Telegram")
        except RuntimeError as e:
            failed = True
            log(f"Telegram send failed: {e}")
    elif send:
        log("No TELEGRAM_BOT_TOKEN and CLIPS_CHAT_ID: report not sent")
    return 2 if failed else 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="results/stats")
    ap.add_argument("--no-send", action="store_true")
    a = ap.parse_args()
    sys.exit(run(a.out, os.environ, send=not a.no_send))


if __name__ == "__main__":
    main()
