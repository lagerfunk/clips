"""Post rendered clips on a calendar through Buffer: every post goes out at its own fixed time.

Calendar file, calendar/<name>.json (files starting with "_" and calendar/accounts.json are not calendars):
  {"timezone": "Europe/Berlin",
   "posts": [{"at": "2026-10-13T19:00", "account": "nocode.founders", "platform": "youtube", "job": "<job id>",
              "clip": "01"}]}
Caption, title and disclosure come from results/<job>/manifest.json (the entry for that clip and platform). Buffer
reads the video from https://raw.githubusercontent.com/<repo>/media/<job>/<clip>-<platform>.mp4.

  python -m clips.schedule plan --job <id> --start 2026-10-13 --times 12:00,16:00,19:00 \\
      --platforms youtube,tiktok,instagram --order 01,02,03 --account nocode.founders \\
      [--offset tiktok=0,instagram=1] --out calendar/<name>.json
  python -m clips.schedule run --calendar 'calendar/*.json' --horizon-hours 30 [--dry-run]

plan: the same clip order on every platform, as many clips a day as there are times, a platform can start a few days
later (--offset). An existing calendar file is extended, never overwritten.

run: every post due within the horizon that is not in the ledger (results/_schedule/queued.json) becomes one Buffer
post scheduled for that exact time. Safe to rerun: the ledger is written after every post, a post already waiting
in Buffer at the same time with the same text is adopted instead of created twice, a media file (job, clip,
platform) is never queued twice on any account, at most 3 posts a day per account and platform, at most 9 posts
waiting per Buffer channel (the free plan stops at 10), and a post whose video does not answer 200 is skipped.
"""
import argparse
import glob
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import buffer
from .common import PLATFORMS, read_json, write_json

LEDGER = "results/_schedule/queued.json"
TZ = "Europe/Berlin"
CAP = 9            # posts waiting per Buffer channel; the free plan allows 10
MAX_PER_DAY = 3    # posts a day per account and platform (owner rule)
LEAD_MINUTES = 5   # a post due sooner than this is too late to hand to Buffer
URGENT_HOURS = 3   # a post this close that still cannot be queued fails the run, so GitHub tells the owner
AT_FORMAT = "%Y-%m-%dT%H:%M"
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}")
AD_LABEL = re.compile(r"(?<![\w#])(#ad|werbung|anzeige)(?![\w])", re.I)
MEDIA = "https://raw.githubusercontent.com/{repo}/media/{job}/{clip}-{platform}.mp4"

# Buffer GraphQL, checked on developers.buffer.com on 2026-10-11:
# - https://developers.buffer.com/guides/posts-and-scheduling.md: "customScheduled" mode sets an exact time with
#   dueAt, "ISO 8601 format (UTC)", example "2026-03-10T15:00:00.000Z"; schedulingType automatic.
# - https://developers.buffer.com/types/CreatePostInput.md: dueAt is a DateTime, mode a ShareMode (required).
# - https://developers.buffer.com/examples/get-scheduled-posts.html: posts(input: {organizationId, filter:
#   {status: [scheduled], channelIds}}) with edges { node { id text dueAt channelId } } and pageInfo for paging.
WAITING = """query { posts(first: 20%s, input: {organizationId: %s, filter: {status: [scheduled], channelIds: %s}}) {
  edges { node { id text dueAt channelId } }
  pageInfo { hasNextPage endCursor }
} }"""


# ---------------------------------------------------------------- time

def to_utc(at, tz=TZ):
    """Local calendar time ("2026-10-25T19:00" in Europe/Berlin) to an aware UTC datetime. A time that exists twice
    (the hour the clocks go back) is taken the first time; one that does not exist moves forward with the clock."""
    return datetime.strptime(at, AT_FORMAT).replace(tzinfo=ZoneInfo(tz)).astimezone(timezone.utc)


def iso_z(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def parse_utc(s):
    dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _hhmm(t):
    if not re.fullmatch(r"\d{2}:\d{2}", t) or int(t[:2]) > 23 or int(t[3:]) > 59:
        raise ValueError(f"time {t!r}: use HH:MM, for example 19:00")
    return t


# ---------------------------------------------------------------- plan

def plan(job, start, times, platforms, order, account, tz=TZ, offsets=None, existing=None, max_per_day=MAX_PER_DAY):
    """Calendar posts for one job: clip i goes out on day start + offset + i // len(times) at times[i % len(times)].
    Returns (calendar, number of posts added). Posts already in `existing` are kept as they are."""
    offsets = offsets or {}
    for v, what in ((job, "job"), (account, "account"), *((c, "clip") for c in order)):
        if not SAFE_ID.fullmatch(v):
            raise ValueError(f"{what} {v!r}: letters, digits, dot, dash and underscore only")
    if len(set(order)) != len(order):
        raise ValueError("--order names a clip twice")
    bad = [p for p in platforms if p not in PLATFORMS] + [p for p in offsets if p not in platforms]
    if bad:
        raise ValueError(f"unknown or unused platform {bad[0]!r}: choose from {', '.join(platforms or PLATFORMS)}")
    times = sorted(set(_hhmm(t) for t in times))
    if not times or len(times) > max_per_day:
        raise ValueError(f"give 1 to {max_per_day} times a day, not {len(times)}")
    ZoneInfo(tz)
    first = date.fromisoformat(start)
    new = []
    for p in platforms:
        for i, clip in enumerate(order):
            day = first + timedelta(days=offsets.get(p, 0) + i // len(times))
            new.append({"at": f"{day.isoformat()}T{times[i % len(times)]}", "account": account, "platform": p,
                        "job": job, "clip": clip})
    cal = existing or {"timezone": tz, "posts": []}
    if cal.get("timezone", TZ) != tz:
        raise ValueError(f"the calendar file uses {cal.get('timezone')}, not {tz}")
    have = {(x["account"], x["platform"], x["job"], x["clip"]) for x in cal.get("posts", [])}
    added = [x for x in new if (x["account"], x["platform"], x["job"], x["clip"]) not in have]
    posts = cal.get("posts", []) + added
    slots = Counter((x["account"], x["platform"], x["at"]) for x in posts)
    clash = [k for k, n in slots.items() if n > 1]
    if clash:
        raise ValueError(f"two posts at the same time: {clash[0][0]} {clash[0][1]} {clash[0][2]}")
    days = Counter((x["account"], x["platform"], x["at"][:10]) for x in posts)
    full = sorted(k for k, n in days.items() if n > max_per_day)
    if full:
        raise ValueError(f"more than {max_per_day} posts on {full[0][2]} for {full[0][0]} on {full[0][1]}: "
                         "start later or use fewer times")
    rank = {p: i for i, p in enumerate(PLATFORMS)}
    cal = {**cal, "timezone": tz, "posts": sorted(posts, key=lambda x: (x["at"], rank.get(x["platform"], 9), x["account"]))}
    return cal, len(added)


# ---------------------------------------------------------------- calendar and ledger

def calendar_files(patterns):
    """Calendar files named or matched. A pattern skips files starting with "_" (examples, paused calendars);
    accounts.json is never a calendar."""
    files = []
    for p in patterns:
        if any(c in p for c in "*?["):
            files += [f for f in sorted(glob.glob(p)) if not Path(f).name.startswith("_")]
        else:
            files.append(p)
    return [f for f in dict.fromkeys(files) if Path(f).name != "accounts.json"]


def check_post(p):
    for k in ("at", "account", "platform", "job", "clip"):
        if not isinstance(p.get(k), str) or not p[k]:
            return f"missing {k}"
    if p["platform"] not in PLATFORMS:
        return f"platform {p['platform']!r} is not one of {', '.join(PLATFORMS)}"
    for k in ("account", "job", "clip"):
        if not SAFE_ID.fullmatch(p[k]):
            return f"{k} {p[k]!r} has characters that are not allowed"
    try:
        datetime.strptime(p["at"], AT_FORMAT)
    except ValueError:
        return f"at {p['at']!r}: use YYYY-MM-DDTHH:MM"
    return None


def load_posts(files):
    """All calendar posts with their UTC time, and the entries that could not be read."""
    posts, invalid = [], []
    for f in files:
        name = Path(f).name
        try:
            cal = read_json(f)
            tz = cal.get("timezone", TZ)
            ZoneInfo(tz)
            entries = cal.get("posts", [])
        except (OSError, ValueError, AttributeError, ZoneInfoNotFoundError) as e:
            invalid.append({"calendar": name, "why": f"cannot read the calendar: {e}"})
            continue
        for i, p in enumerate(entries):
            why = check_post(p) if isinstance(p, dict) else "not an object"
            if why:
                invalid.append({"calendar": name, "post": i + 1, "why": why})
                continue
            notify = set(cal.get("notify", []))  # platforms Buffer hands to the phone, e.g. TikTok for its ad switch
            posts.append({**{k: p[k] for k in ("at", "account", "platform", "job", "clip")}, "timezone": tz,
                          "notify": p["platform"] in notify,
                          "calendar": name, "due": to_utc(p["at"], tz),
                          "file": f"{p['job']}/{p['clip']}-{p['platform']}.mp4"})
    return posts, invalid


def select_due(posts, now, horizon_hours, lead_minutes=LEAD_MINUTES):
    """Posts due after now + lead and no later than now + horizon, earliest first."""
    lo, hi = now + timedelta(minutes=lead_minutes), now + timedelta(hours=horizon_hours)
    rank = {p: i for i, p in enumerate(PLATFORMS)}
    return sorted((p for p in posts if lo < p["due"] <= hi), key=lambda p: (p["due"], rank[p["platform"]], p["account"]))


def load_ledger(path):
    p = Path(path)
    if not p.exists():
        return {"posts": {}}
    led = read_json(p)
    led.setdefault("posts", {})
    return led


def save_ledger(path, led):
    tmp = Path(f"{path}.tmp")
    write_json(tmp, led)
    os.replace(tmp, path)


def load_accounts(files, path=None):
    """Optional calendar/accounts.json: {"nocode.founders": {"youtube": "<channel name or id>"}} or
    {"nocode.founders": "<channel name or id>"} for every platform."""
    cands = [Path(path)] if path else [Path(f).parent / "accounts.json" for f in files]
    for c in dict.fromkeys(cands):
        if c.exists():
            return read_json(c)
    return {}


# ---------------------------------------------------------------- Buffer and media

def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def find_channel(chans, account, platform, accounts):
    """The one Buffer channel for this account on this platform: named in accounts.json, or its name contains the
    handle without dots ("nocode.founders" matches "nocodefounders" and "NoCode Founders")."""
    svc = buffer.SERVICE[platform]
    cands = [c for c in chans if c.get("service") == svc]
    want = accounts.get(account)
    if isinstance(want, dict):
        want = want.get(platform)
    if want:
        hits = [c for c in cands if c.get("id") == want or _norm(c.get("name")) == _norm(want)]
    else:
        hits = [c for c in cands if _norm(account) in _norm(c.get("name"))]
    if len(hits) == 1:
        return hits[0], None
    if not hits:
        return None, f"no Buffer {platform} channel for {account} (connect it in Buffer or map it in calendar/accounts.json)"
    return None, f"{len(hits)} Buffer {platform} channels match {account}: name one in calendar/accounts.json"


def waiting_posts(channel_ids, key=None):
    """Posts already scheduled in Buffer, per channel: {channel id: [{id, text, dueAt, channelId}]}."""
    out = {c: [] for c in channel_ids}
    if not channel_ids:
        return out
    orgs = buffer.gql("query { account { organizations { id } } }", key=key)["account"]["organizations"]
    for o in orgs:
        after = None
        for _ in range(100):
            page = f", after: {json.dumps(after)}" if after else ""
            res = buffer.gql(WAITING % (page, json.dumps(o["id"]), json.dumps(sorted(channel_ids))), key=key)["posts"]
            for e in res.get("edges", []):
                n = e["node"]
                if n.get("channelId") in out:
                    out[n["channelId"]].append(n)
            if not res.get("pageInfo", {}).get("hasNextPage"):
                break
            after = res["pageInfo"]["endCursor"]
    return out


def media_status(url):
    """HTTP status of a HEAD request (0 when the host cannot be reached)."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "clips-schedule"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0


def manifest_entry(results, job, clip, platform, cache):
    if job not in cache:
        path = Path(results) / job / "manifest.json"
        cache[job] = read_json(path) if path.exists() else None
    m = cache[job]
    if m is None:
        return None, None, f"no manifest for job {job} yet (results/{job}/manifest.json)"
    if m.get("stage") != "rendered":
        return None, m, f"job {job} is not rendered yet (stage {m.get('stage')})"
    for f in m.get("files", []):
        if f.get("clip") == clip and f.get("platform") == platform:
            return f, m, None
    return None, m, f"clip {clip} has no {platform} render in job {job}"


def post_text(entry, manifest):
    """Caption with the disclosure first, and the reason it cannot be posted (None when it can)."""
    caption = (entry.get("caption") or "").strip()
    disc = entry.get("disclosure")
    if isinstance(disc, str) and disc.strip() and disc.strip().lower() not in caption.lower():
        caption = f"{disc.strip()} {caption}".strip()
    if not caption:
        return caption, "the manifest has no caption"
    own = disc.strip().lower() if isinstance(disc, str) else ""
    labelled = AD_LABEL.search(caption) or (own and own in caption.lower())
    if manifest.get("campaign", {}).get("disclosure", True) and not labelled:
        return caption, "the caption has no ad label"
    return caption, None


# ---------------------------------------------------------------- run

def run(calendars, horizon_hours=30, dry_run=False, now=None, results="results", ledger_path=LEDGER, repo=None,
        key=None, cap=CAP, max_per_day=MAX_PER_DAY, lead_minutes=LEAD_MINUTES, accounts_path=None):
    now = now or datetime.now(timezone.utc)
    repo = repo or os.environ.get("GITHUB_REPOSITORY")
    if not repo:
        raise SystemExit("no repository: set GITHUB_REPOSITORY (owner/name) or pass --repo")
    key = key or os.environ.get("BUFFER_API_KEY")
    if not key and not dry_run:
        raise SystemExit("BUFFER_API_KEY is not set: nothing can be queued (use --dry-run to check a calendar)")
    files = calendar_files(calendars)
    posts, invalid = load_posts(files)
    led = load_ledger(ledger_path)
    done = led["posts"]
    rep = {"queued": [], "adopted": [], "already": [], "skipped": [], "failed": [], "missed": [], "invalid": invalid}

    def item(p, **kw):
        return {"at": p["at"], "account": p["account"], "platform": p["platform"], "job": p["job"], "clip": p["clip"],
                "dueAt": iso_z(p["due"]), "calendar": p["calendar"], **kw}

    past = now - timedelta(hours=horizon_hours)
    for p in posts:
        if past < p["due"] <= now + timedelta(minutes=lead_minutes) and p["file"] not in done:
            rep["missed"].append(item(p, why="its time passed before it was queued"))
    due = select_due(posts, now, horizon_hours, lead_minutes)
    if not due:
        return rep

    online = bool(key) or not dry_run
    chans, waiting = None, None
    accounts = load_accounts(files, accounts_path)
    if online:
        chans = buffer.channels(key)
        ids = {c["id"] for c in chans if c.get("service") in buffer.SERVICE.values()}
        try:
            waiting = waiting_posts(ids, key)
        except Exception as e:  # counting falls back to the ledger; never a reason to stop
            print(f"Could not read the posts waiting in Buffer ({str(e)[:200]}); counting from the ledger instead")
    per_day = Counter((e["account"], e["platform"], e.get("at", "")[:10]) for e in done.values())
    made = Counter()
    taken = {}
    manifests = {}

    def waiting_count(cid):
        if waiting is not None:
            return len(waiting.get(cid, [])) + made[cid]
        return sum(1 for e in done.values() if e.get("channel") == cid and parse_utc(e["dueAt"]) > now) + made[cid]

    def record(p, cid, post_id, due_at, **extra):
        rec = {"account": p["account"], "platform": p["platform"], "job": p["job"], "clip": p["clip"], "at": p["at"],
               "timezone": p["timezone"], "dueAt": due_at, "channel": cid, "post": post_id, "calendar": p["calendar"],
               "queuedAt": iso_z(now), **extra}
        if dry_run:
            taken[p["file"]] = rec
        else:
            done[p["file"]] = rec
            save_ledger(ledger_path, led)
        per_day[(p["account"], p["platform"], p["at"][:10])] += 1

    for p in due:
        prev = done.get(p["file"]) or taken.get(p["file"])
        if prev:
            if prev["account"] == p["account"]:
                rep["already"].append(item(p, post=prev.get("post")))
            else:
                why = f"this file is already queued for {prev['account']} (never the same file on two accounts)"
                rep["skipped"].append(item(p, why=why))
            continue
        if per_day[(p["account"], p["platform"], p["at"][:10])] >= max_per_day:
            rep["skipped"].append(item(p, why=f"{p['account']} already has {max_per_day} {p['platform']} posts that day"))
            continue
        entry, manifest, why = manifest_entry(results, p["job"], p["clip"], p["platform"], manifests)
        if why:
            rep["skipped"].append(item(p, why=why))
            continue
        caption, why = post_text(entry, manifest)
        if why:
            rep["skipped"].append(item(p, why=why))
            continue
        if chans is None:
            channel = {"id": f"dry-run-{p['account']}-{p['platform']}", "name": "(dry run without BUFFER_API_KEY)"}
        else:
            channel, why = find_channel(chans, p["account"], p["platform"], accounts)
            if why:
                rep["skipped"].append(item(p, why=why))
                continue
        cid, due_at = channel["id"], iso_z(p["due"])
        text = " ".join(caption.split())
        same = [n for n in (waiting or {}).get(cid, []) if n.get("dueAt") and parse_utc(n["dueAt"]) == p["due"]
                and " ".join((n.get("text") or "").split()) == text]
        if same:
            record(p, cid, same[0]["id"], due_at, adopted=True)
            rep["adopted"].append(item(p, post=same[0]["id"]))
            continue
        n = waiting_count(cid)
        if n >= cap:
            why = f"{n} posts already waiting on this Buffer channel (cap {cap}); tried again next run"
            rep["skipped"].append(item(p, why=why))
            continue
        url = MEDIA.format(repo=repo, job=p["job"], clip=p["clip"], platform=p["platform"])
        code = media_status(url)
        if code != 200:
            rep["skipped"].append(item(p, why=f"video not reachable ({code or 'no answer'}): {url}"))
            continue
        inp = buffer.post_input(p["platform"], cid, url, caption, entry.get("title") or "")
        inp["mode"] = "customScheduled"  # exact time instead of the next queue slot (see the doc links at the top)
        if p.get("notify"):
            # schedulingType notification: Buffer sends it to the owner's phone at that time and he posts it in the
            # app, where the paid-promotion switch Buffer's API cannot set is turned on (CreatePostInput.md)
            inp["schedulingType"] = "notification"
        inp["dueAt"] = due_at
        if dry_run:
            record(p, cid, None, due_at)
            made[cid] += 1
            rep["queued"].append(item(p, post=None, dry_run=True, input=inp))
            continue
        try:
            res = buffer.gql(buffer.CREATE, {"input": inp}, key=key)["createPost"]
        except Exception as e:  # an unclear answer is safe: next run adopts the post if Buffer did create it
            rep["failed"].append(item(p, why=str(e)[:300]))
            continue
        if not isinstance(res, dict) or "post" not in res:
            rep["failed"].append(item(p, why=(res if isinstance(res, dict) else {}).get("message", "Buffer gave no post back")))
            continue
        got = res["post"].get("dueAt") or due_at
        made[cid] += 1
        record(p, cid, res["post"]["id"], got)
        rep["queued"].append(item(p, post=res["post"]["id"], channel=channel.get("name")))
    return rep


def urgent(rep, now, hours=URGENT_HOURS):
    """What needs a person: Buffer errors, broken calendar entries, and posts due soon that still cannot go out."""
    soon = now + timedelta(hours=hours)
    late = [x for x in rep["skipped"] if parse_utc(x["dueAt"]) <= soon]
    return rep["failed"] + rep["invalid"] + late


def print_report(rep, dry_run=False):
    lines = []
    for k, label in (("queued", "dry run, would queue" if dry_run else "queued"), ("adopted", "already in Buffer, recorded"),
                     ("skipped", "skipped"), ("failed", "FAILED"), ("missed", "missed"), ("invalid", "calendar error")):
        for x in rep[k]:
            if k == "invalid":
                lines.append(f"{label}: {x['calendar']} post {x.get('post', '-')}: {x['why']}")
                continue
            tail = f" -> {x['why']}" if x.get("why") else (f" (Buffer post {x['post']})" if x.get("post") else "")
            lines.append(f"{label}: {x['at']} {x['account']} {x['platform']} {x['job']}/{x['clip']}{tail}")
    head = (f"{len(rep['queued'])} queued, {len(rep['adopted'])} adopted, {len(rep['already'])} already queued, "
            f"{len(rep['skipped'])} skipped, {len(rep['failed'])} failed, {len(rep['missed'])} missed")
    print(head)
    for line in lines:
        print("  " + line)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(f"### Schedule\n\n{head}\n\n" + "".join(f"- {line}\n" for line in lines))


def _list(s):
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m clips.schedule")
    sub = ap.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("plan", help="write or extend a calendar file for one job")
    pl.add_argument("--job", required=True)
    pl.add_argument("--start", required=True, help="first day, YYYY-MM-DD")
    pl.add_argument("--times", required=True, help="posting times a day, HH:MM,HH:MM,HH:MM")
    pl.add_argument("--platforms", default=",".join(PLATFORMS))
    pl.add_argument("--order", help="clip ids in posting order (default: the order in the job's manifest)")
    pl.add_argument("--account", required=True)
    pl.add_argument("--offset", default="", help="days a platform starts later, for example tiktok=0,instagram=1")
    pl.add_argument("--timezone", default=TZ)
    pl.add_argument("--results", default="results")
    pl.add_argument("--out", required=True)
    rn = sub.add_parser("run", help="queue the posts due soon in Buffer")
    rn.add_argument("--calendar", nargs="+", default=["calendar/*.json"])
    rn.add_argument("--horizon-hours", type=float, default=30)
    rn.add_argument("--dry-run", action="store_true")
    rn.add_argument("--results", default="results")
    rn.add_argument("--ledger", default=LEDGER)
    rn.add_argument("--repo", help="owner/name of the repo with the media branch (default: GITHUB_REPOSITORY)")
    rn.add_argument("--accounts", help="account to channel map (default: accounts.json next to the calendars)")
    rn.add_argument("--now", help="pretend it is this UTC time, for checking a calendar (ISO 8601)")
    a = ap.parse_args(argv)

    if a.cmd == "plan":
        order = _list(a.order)
        if not order:
            mpath = Path(a.results) / a.job / "manifest.json"
            if not mpath.exists():
                raise SystemExit(f"give --order: {mpath} does not exist here")
            order = list(dict.fromkeys(f["clip"] for f in read_json(mpath).get("files", [])))
        offsets = {}
        for x in _list(a.offset):
            k, _, v = x.partition("=")
            try:
                offsets[k.strip()] = int(v)
            except ValueError:
                raise SystemExit(f"--offset {x!r}: use platform=days, for example instagram=1") from None
        existing = read_json(a.out) if Path(a.out).exists() else None
        try:
            cal, added = plan(a.job, a.start, _list(a.times), _list(a.platforms), order, a.account, a.timezone,
                              offsets, existing)
        except ValueError as e:
            raise SystemExit(str(e)) from None
        write_json(a.out, cal)
        mine = [x for x in cal["posts"] if x["job"] == a.job and x["account"] == a.account]
        print(f"{a.out}: {added} post(s) added, {len(cal['posts'])} in the file; {a.job} runs "
              f"{min(x['at'] for x in mine)} to {max(x['at'] for x in mine)} ({a.timezone})")
        return 0

    now = parse_utc(a.now) if a.now else datetime.now(timezone.utc)
    rep = run(a.calendar, a.horizon_hours, a.dry_run, now, a.results, a.ledger, a.repo, accounts_path=a.accounts)
    print_report(rep, a.dry_run)
    bad = urgent(rep, now)
    if bad:
        print(f"{len(bad)} problem(s) need a look before the posts are due")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
