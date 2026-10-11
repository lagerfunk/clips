"""Run one clipping job end to end.

  python -m clips.job jobs/<id>.json --work work --out out

1. fetch every source, 2. transcribe it (cached), 3. without picked clips: write candidates and stop,
4. with picked clips: render every clip once per platform and write manifest.json with the post text.

Job file:
{
  "id": "2026-10-12-topps",
  "campaign": {"name": "...", "board": "whop", "url": "...", "rate": "$1 per 1K", "platforms": ["tiktok", "instagram", "youtube"],
               "brand": "Topps", "adLabel": "Werbung", "disclosure": true, "mustInclude": ["@topps"], "rules": ["..."],
               "overlays": {"ad": true}},
  "overlays": {"ad": true},                       optional, job level wins over campaign level
  "assets": {"watermark": {"url": "<Drive folder or file, image URL or local path>", "pick": "png",
                           "width": 0.55, "position": "center-lower"}},   optional, see below
  "sources": [{"id": "s1", "url": "https://drive.google.com/... or https://we.tl/...", "file": "optional name inside a folder or zip"}],
  "clips": [{"id": "01", "source": "s1", "segments": [[12.0, 31.5], [40.2, 47.0]], "hook": "...", "caption": "...",
             "hashtags": ["#cards"], "title": "optional YouTube title",
             "lower": {"title": "Name, 32 chars max", "sub": "Role, 40 chars max", "start": 0.5, "end": 4.0},
             "end": "End card, 40 chars max"}]          or "end": {"text": "...", "secs": 2.5}
}

Paid campaigns (disclosure on, the default) are advertising under German law (UWG § 5a, Medienstaatsvertrag, Medienanstalten
2025): the caption opens with "Werbung | Paid promotion for <brand>", the video carries the "Werbung" label on screen,
and each app's own paid toggle is set (flags in the manifest). "#ad" alone does not count as a label.

Campaign extras (Higgsfield x 20VC style briefs):
- "tagsByPlatform": {"youtube": ["@HiggsfieldAI", "@20VC"], "instagram": ["@higgsfield.ai", "@20vchq"]}: each platform's
  caption ends with its own tags (after the clip's hashtags, #ad and mustInclude).
- "minSecs" / "maxSecs": clip length the campaign accepts. Number segments are checked before anything runs; text
  segments after they are found in the transcript, and a clip that misses fails alone (manifest "failedClips").
- assets.watermark: fetched once per job into the work dir (pick "png": the first PNG with transparency, else the first
  image; any other value names the file) and laid over every frame of every clip, never under captions or text.
"""
import argparse
import os
import re
from pathlib import Path

from . import candidates as cand
from .common import PLATFORMS, probe, read_json, write_json
from .fetch import fetch, fetch_asset, has_alpha
from .render import WM_MAX, WM_MIN, WM_POSITIONS, render

MIN_CLIP, MAX_CLIP = 8.0, 90.0
TAG_RE = re.compile(r"[@#][\w.\-]{1,100}")
AD_LABEL = "Werbung"  # first word of the caption; "Anzeige" also works, "#ad" alone does not
AD_TAG = "#ad"        # kept among the hashtags for the campaign boards, never the only label
LOWER_TITLE, LOWER_SUB, END_TEXT = 32, 40, 40
CAPTION_MAX = 2200


def _norm(t):
    return re.sub(r"[^a-z0-9$€%]+", "", t.lower())


def resolve_segment(words, seg):
    """[start, end] in seconds, or {"from": "first words", "to": "last words"} resolved against the transcript,
    so a clip can be written by quoting what is said and still cut on the exact word."""
    if isinstance(seg, (list, tuple)):
        return float(seg[0]), float(seg[1])
    toks = [_norm(w["w"]) for w in words]
    def find(phrase, start=0, last=False):
        p = [x for x in (_norm(t) for t in phrase.split()) if x]
        for i in range(start, len(toks) - len(p) + 1):
            if toks[i:i + len(p)] == p:
                return i + len(p) - 1 if last else i
        return None
    i = find(seg["from"])
    if i is None:
        raise ValueError(f"start text not found in the transcript: {seg['from']!r}")
    j = find(seg["to"], i, last=True)
    if j is None:
        raise ValueError(f"end text not found after the start: {seg['to']!r}")
    return max(0.0, words[i]["s"] - 0.12), words[j]["e"] + 0.3


def fix_words(words, fixes):
    """Correct names the speech model got wrong ("Zeng" -> "Zain") in the captions only, keeping punctuation."""
    if not fixes:
        return words
    low = {k.lower(): v for k, v in fixes.items() if k != k.upper() or len(k) < 2}
    exact = {k: v for k, v in fixes.items() if k == k.upper() and len(k) >= 2}  # all-caps keys ("ID") match exactly
    out = []
    for w in words:
        m = re.match(r"^(.*?)([.,!?;:]*)$", w["w"])
        core, tail = m.group(1), m.group(2)
        new = exact.get(core) or low.get(core.lower())
        out.append({**w, "w": (new + tail) if new else w["w"]})
    return out


def fix_phrases(words, fixes):
    """Correct multi-word mishearings in the captions ("we'd love a wall" -> "Lovable"): the matched words become one
    word spanning their time, keeping the last word's punctuation. Matching ignores case and punctuation."""
    if not fixes:
        return words
    pats = sorted(((tuple(_norm(t) for t in k.split()), v) for k, v in fixes.items()), key=lambda x: -len(x[0]))
    toks = [_norm(w["w"]) for w in words]
    out, i = [], 0
    while i < len(words):
        for pat, rep in pats:
            n = len(pat)
            if n and tuple(toks[i:i + n]) == pat:
                tail = re.match(r"^.*?([.,!?;:]*)$", words[i + n - 1]["w"]).group(1)
                out.append({**words[i], "w": rep + tail, "e": words[i + n - 1]["e"]})
                i += n
                break
        else:
            out.append(words[i])
            i += 1
    return out


def disclosure(job):
    """The ad label for a paid campaign, or None when the campaign sets "disclosure": false."""
    camp = job.get("campaign") or {}
    if not camp.get("disclosure", True):
        return None
    brand = str(camp.get("brand") or "").strip()
    return {"label": str(camp.get("adLabel") or AD_LABEL).strip(), "brand": brand or None}


def ad_line(d):
    """First caption line: "Werbung | Paid promotion for Lovable" (German label first, then the English reading)."""
    return f"{d['label']} | Paid promotion" + (f" for {d['brand']}" if d["brand"] else "")


def manifest_disclosure(d):
    """What each app must be told; Buffer cannot set these (see buffer.post_input), so the owner toggles them."""
    return {"label": d["label"], "brand": d["brand"], "youtubePaidPromotion": True,
            "tiktokBrandedContent": True, "instagramPaidPartnership": True}


def end_card(end):
    return {"text": end} if isinstance(end, str) else {k: end[k] for k in ("text", "secs") if k in end}


def overlays_for(job, clip, watermark=None):
    """On-screen extras for one clip: the permanent ad label, a lower third, an end card, the campaign watermark
    (watermark = {"path", "width", "position"}, given when the job has one). Empty when none apply."""
    camp = job.get("campaign") or {}
    conf = {**(camp.get("overlays") or {}), **(job.get("overlays") or {})}
    d = disclosure(job)
    ov = {}
    if conf.get("ad", d is not None):
        ov["ad"] = d["label"] if d else str(camp.get("adLabel") or AD_LABEL)
    if clip.get("lower"):
        ov["lower"] = {k: clip["lower"][k] for k in ("title", "sub", "start", "end") if k in clip["lower"]}
    if clip.get("end"):
        ov["end"] = end_card(clip["end"])
    if watermark:
        ov["watermark"] = dict(watermark)
    return ov


def clip_limits(job):
    """(shortest, longest) clip in seconds: the campaign's minSecs / maxSecs, else 8 to 90."""
    camp = job.get("campaign") or {}
    lo, hi = camp.get("minSecs", MIN_CLIP), camp.get("maxSecs", MAX_CLIP)
    return (float(lo) if _num(lo) else MIN_CLIP), (float(hi) if _num(hi) else MAX_CLIP)


def watermark_conf(job):
    wm = (job.get("assets") or {}).get("watermark")
    return wm if isinstance(wm, dict) else None


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x >= 0


def _text_ok(x, limit):
    return isinstance(x, str) and x.strip() and len(x) <= limit


def check_overlays(c):
    cid, problems = c.get("id", "?"), []
    if "lower" in c:
        lw = c["lower"]
        if not isinstance(lw, dict):
            problems.append(f"clip {cid}: lower must be {{\"title\", \"sub\"}}")
        else:
            if not _text_ok(lw.get("title"), LOWER_TITLE):
                problems.append(f"clip {cid}: lower title missing or over {LOWER_TITLE} characters")
            if not _text_ok(lw.get("sub"), LOWER_SUB):
                problems.append(f"clip {cid}: lower sub missing or over {LOWER_SUB} characters")
            for k in ("start", "end"):
                if k in lw and not _num(lw[k]):
                    problems.append(f"clip {cid}: lower {k} must be seconds (a number, 0 or more)")
            if _num(lw.get("start")) and _num(lw.get("end")) and lw["end"] <= lw["start"]:
                problems.append(f"clip {cid}: lower end must be after its start")
    if "end" in c:
        end = c["end"]
        text = end if isinstance(end, str) else end.get("text") if isinstance(end, dict) else None
        if not _text_ok(text, END_TEXT):
            problems.append(f"clip {cid}: end card text missing or over {END_TEXT} characters")
        if isinstance(end, dict) and "secs" in end and not (_num(end["secs"]) and end["secs"] > 0):
            problems.append(f"clip {cid}: end card secs must be a number above 0")
    return problems


def check_campaign(job):
    problems = []
    camp = job.get("campaign")
    if camp and not isinstance(camp.get("disclosure", True), bool):
        problems.append("campaign.disclosure must be true or false")
    for where, conf in (("campaign.overlays", (camp or {}).get("overlays")), ("overlays", job.get("overlays"))):
        if conf is not None and not (isinstance(conf, dict) and isinstance(conf.get("ad", True), bool)):
            problems.append(f'{where} must look like {{"ad": true}}')
    if camp and camp.get("disclosure", True) is not False:
        if not str(camp.get("brand") or "").strip():
            problems.append('campaign.brand missing: paid campaigns open the caption with "Werbung | Paid promotion '
                            'for <brand>" (set "brand", or "disclosure": false if the post is not paid)')
        if "adLabel" in camp and not _text_ok(camp["adLabel"], 20):
            problems.append('campaign.adLabel must be a short word such as "Werbung" or "Anzeige"')
    camp = camp or {}
    tbp = camp.get("tagsByPlatform")
    if tbp is not None:
        if not isinstance(tbp, dict):
            problems.append('campaign.tagsByPlatform must look like {"youtube": ["@brand"], "instagram": ["@brand.ig"]}')
        else:
            for p, tags in tbp.items():
                if p not in PLATFORMS:
                    problems.append(f"campaign.tagsByPlatform: unknown platform {p!r}, use {PLATFORMS}")
                elif not isinstance(tags, list) or not all(isinstance(t, str) and TAG_RE.fullmatch(t) for t in tags):
                    problems.append(f"campaign.tagsByPlatform.{p}: a list of @handles or #tags without spaces")
            missing = [p for p in (camp.get("platforms") or PLATFORMS) if p in PLATFORMS and p not in tbp]
            if missing:
                problems.append(f"campaign.tagsByPlatform has no entry for {', '.join(missing)} "
                                "(write [] when that platform needs no tags)")
    for k in ("minSecs", "maxSecs"):
        if k in camp and not (_num(camp[k]) and camp[k] >= 1):
            problems.append(f"campaign.{k} must be seconds (a number, 1 or more)")
    lo, hi = clip_limits(job)
    if lo >= hi:
        problems.append(f"campaign.minSecs ({lo:g}) must be below maxSecs ({hi:g})")
    return problems


def check_assets(job):
    assets = job.get("assets")
    if assets is None:
        return []
    if not isinstance(assets, dict) or set(assets) - {"watermark"}:
        return ['assets must look like {"watermark": {"url": "...", "pick": "png"}}']
    wm, problems = assets.get("watermark"), []
    if not isinstance(wm, dict) or not isinstance(wm.get("url"), str) or not wm["url"].strip():
        return ['assets.watermark needs a "url" (a Google Drive folder or file, an image URL or a local path)']
    if "pick" in wm and not _text_ok(wm["pick"], 120):
        problems.append('assets.watermark.pick: "png" or a file name')
    if "width" in wm and not (_num(wm["width"]) and WM_MIN <= wm["width"] <= WM_MAX):
        problems.append(f"assets.watermark.width: a share of the frame width from {WM_MIN} to {WM_MAX} (0.55 is 594 px)")
    if "position" in wm and wm["position"] not in WM_POSITIONS:
        problems.append(f"assets.watermark.position: one of {', '.join(WM_POSITIONS)}")
    return problems


def check_job(job):
    problems = []
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,60}", job.get("id", "")):
        problems.append("id: lowercase letters, digits and dashes only")
    plats = job.get("campaign", {}).get("platforms") or list(PLATFORMS)
    if any(p not in PLATFORMS for p in plats):
        problems.append(f"platforms must be among {PLATFORMS}")
    if job.get("type") == "story":
        return problems + check_stories(job)
    problems += check_campaign(job) + check_assets(job)
    lo, hi = clip_limits(job)
    src_ids = {s["id"] for s in job.get("sources", [])}
    if not src_ids:
        problems.append("no sources")
    seen = set()
    for c in job.get("clips", []):
        cid = c.get("id", "?")
        if cid in seen:
            problems.append(f"clip {cid}: duplicate id")
        seen.add(cid)
        if c.get("source") not in src_ids:
            problems.append(f"clip {cid}: unknown source {c.get('source')}")
        segs = c.get("segments") or []
        if any(isinstance(x, dict) for x in segs):
            if not all(isinstance(x, dict) and x.get("from") and x.get("to") or isinstance(x, list) for x in segs):
                problems.append(f"clip {cid}: text segments need 'from' and 'to'")
            segs = []  # checked against the transcript at render time
            total = None
        else:
            total = sum(b - a for a, b in segs)
        if not (c.get("segments")) or (segs and any(b <= a for a, b in segs)):
            problems.append(f"clip {cid}: segments must be [start, end] pairs with end > start, or from/to text")
        elif total is not None and not lo <= total <= hi:
            problems.append(f"clip {cid}: {total:.1f}s long, keep it between {lo:g} and {hi:g}s")
        if not c.get("hook") or len(c["hook"]) > 90:
            problems.append(f"clip {cid}: hook missing or over 90 characters")
        if len(c.get("title") or c.get("hook", "")) > 100:
            problems.append(f"clip {cid}: YouTube title over 100 characters")
        problems += check_overlays(c)
        lower, end = c.get("lower") if isinstance(c.get("lower"), dict) else {}, c.get("end")
        on_screen = [lower.get("title"), lower.get("sub"), end.get("text") if isinstance(end, dict) else end]
        if "—" in c.get("hook", "") + c.get("caption", "") + "".join(x for x in on_screen if isinstance(x, str)):
            problems.append(f"clip {cid}: no em dashes")
    from .render import wrap
    for c in job.get("clips", []) + job.get("stories", []):
        if c.get("hook") and wrap(c["hook"]).endswith("..."):
            problems.append(f"clip {c.get('id')}: hook is too long for 3 lines on screen, shorten it: {c['hook']!r}")
    return problems


def check_stories(job):
    problems, seen = [], set()
    # Owner 2026-10-11: "this is just blatant AI videos". No AI-voice slideshows: a story job needs his own recording.
    if not job.get("ownerVoice"):
        problems.append("story jobs need the owner's own voice recording (ownerVoice); AI-voice videos are off (owner 2026-10-11)")
    if not job.get("stories"):
        problems.append("story job without stories")
    for st in job.get("stories", []):
        sid = st.get("id", "?")
        if sid in seen:
            problems.append(f"story {sid}: duplicate id")
        seen.add(sid)
        if not st.get("hook") or len(st["hook"]) > 90:
            problems.append(f"story {sid}: hook missing or over 90 characters")
        scenes = st.get("scenes") or []
        if not 2 <= len(scenes) <= 12:
            problems.append(f"story {sid}: 2 to 12 scenes")
        words = sum(len(sc.get("say", "").split()) for sc in scenes)
        if not 25 <= words <= 170:
            problems.append(f"story {sid}: {words} spoken words, keep 25 to 170 (about 10 to 60 seconds)")
        for sc in scenes:
            if not sc.get("say") or not isinstance(sc.get("image"), dict):
                problems.append(f"story {sid}: every scene needs 'say' and an 'image'")
                break
        if "\u2014" in (st.get("hook", "") + st.get("caption", "") + " ".join(sc.get("say", "") for sc in scenes)):
            problems.append(f"story {sid}: no em dashes")
    return problems


def run_stories(job, work, out, only=None):
    from .story import render_story
    jid = job["id"]
    plats = job.get("campaign", {}).get("platforms") or list(PLATFORMS)
    rendered = []
    for st in job["stories"]:
        if only and st["id"] not in only:
            continue
        for res in render_story(st, Path(work) / jid, Path(out) / jid, job.get("voice", "am_michael"), job.get("speed", 1.05), plats):
            rendered.append({"clip": st["id"], **res, **post_text(job, st, res.get("platform"))})
    manifest = {"id": jid, "stage": "rendered", "campaign": job.get("campaign", {}), "files": rendered}
    write_json(Path(out) / jid / "manifest.json", manifest)
    return manifest


def post_text(job, clip, platform=None):
    """Caption: "Werbung | Paid promotion for <brand>", blank line, the clip caption, blank line, hashtags.
    The label is the first line, seen before "more", because German law wants the ad clear at a glance; "#ad" stays
    among the hashtags (after the clip's own, before the campaign's required ones) but never as the only label.
    With a platform, the campaign's tagsByPlatform for it come last (the same handle is spelled differently per app)."""
    camp = job.get("campaign", {})
    d = disclosure(job)
    own = list(dict.fromkeys(clip.get("hashtags", [])))
    must = list(camp.get("mustInclude", []))
    per = list((camp.get("tagsByPlatform") or {}).get(platform) or []) if platform else []
    if d and AD_TAG not in own + must + per:
        own.append(AD_TAG)
    tags = list(dict.fromkeys(own + must + per))
    head = [ad_line(d)] if d else []
    tail = [" ".join(tags)] if tags else []
    caption = (clip.get("caption") or clip["hook"]).strip()
    room = CAPTION_MAX - len("\n\n".join(head + [""] + tail))  # a long caption is cut, never the label or tags
    text = "\n\n".join(head + [caption[:max(0, room)].rstrip()] + tail)
    return {"caption": text[:CAPTION_MAX], "title": (clip.get("title") or clip["hook"])[:100], "tags": tags}


def alarm(title, msg):
    """A failure that must not go unseen: an error annotation on the GitHub run page, a plain ERROR line elsewhere."""
    msg = " ".join(str(msg).split())
    if os.environ.get("GITHUB_ACTIONS"):  # workflow-command escaping: % always, : and , inside the title
        title = title.replace("%", "%25").replace(":", "%3A").replace(",", "%2C")
        print(f"::error title={title}::{msg.replace('%', '%25')}")
    else:
        print(f"ERROR {title}: {msg}")


def get_watermark(job, wdir):
    """{"path", "width", "position"} for the renderer, fetched once into <work>/<job>/assets/watermark, or None."""
    conf = watermark_conf(job)
    if not conf:
        return None
    path = fetch_asset(conf["url"], Path(wdir) / "assets" / "watermark", conf.get("pick", "png"))
    if not has_alpha(path):
        alarm("watermark", f"{path.name} has no see-through pixels: it will show as a solid box (pick another file?)")
    print(f"watermark: {path.name}")
    return {"path": str(path), "width": conf.get("width", 0.55), "position": conf.get("position", WM_POSITIONS[0])}


def run_job(job_path, work="work", out="out", only=None):
    job = read_json(job_path)
    problems = check_job(job)
    if problems:
        raise SystemExit("job not valid:\n- " + "\n- ".join(problems))
    if job.get("type") == "story":
        return run_stories(job, work, out, only)
    jid = job["id"]
    wdir, odir = Path(work) / jid, Path(out) / jid
    watermark = None
    if job.get("clips") and watermark_conf(job):  # before the long source download: no clip may go out without it
        try:
            watermark = get_watermark(job, wdir)
        except Exception as e:
            why = str(e)[-500:]
            alarm("watermark", f"could not fetch the campaign watermark: {why}")
            write_json(odir / "manifest.json", {"id": jid, "stage": "failed", "failed": {"watermark": why}})
            raise SystemExit(f"no clip rendered: the campaign watermark is required and could not be fetched: {why}")
    sources, failed = {}, {}
    for s in job["sources"]:
        try:
            files = fetch(s["url"], wdir / s["id"], want=s.get("file"))
        except Exception as e:  # one blocked source must not stop the others
            failed[s["id"]] = str(e)[-500:]
            alarm(f"source {s['id']}", f"could not be fetched: {failed[s['id']]}")
            continue
        media = next((f for f in files if s.get("file") and f.name == s["file"]), files[0])
        tr_path = wdir / f"{s['id']}.words.json"
        saved = Path("results") / jid / f"{s['id']}.words.json"
        if not tr_path.exists() and saved.exists():
            tr_path.parent.mkdir(parents=True, exist_ok=True)
            tr_path.write_text(saved.read_text())
        if not tr_path.exists():
            from .transcribe import transcribe
            write_json(tr_path, transcribe(media, language=s.get("language")))
        sources[s["id"]] = {"media": media, "transcript": read_json(tr_path), "info": probe(media)}
    if not sources:
        write_json(odir / "manifest.json", {"id": jid, "stage": "failed", "failed": failed})
        raise SystemExit(f"no source could be fetched: {failed}")

    if not job.get("clips"):
        summary = {}
        for sid, s in sources.items():
            found = cand.find(s["transcript"], s["media"])
            write_json(odir / f"candidates-{sid}.json", found)
            summary[sid] = len(found)
        write_json(odir / "manifest.json", {"id": jid, "stage": "candidates", "candidates": summary, "failed": failed})
        return {"stage": "candidates", "candidates": summary, "failed": failed}

    plats = job.get("campaign", {}).get("platforms") or list(PLATFORMS)
    d = disclosure(job)
    lo, hi = clip_limits(job)
    rendered, failed_clips = [], {}
    for c in job["clips"]:
        if only and c["id"] not in only:
            continue
        if c["source"] not in sources:
            print(f"clip {c['id']}: source {c['source']} unavailable, skipped")
            continue
        s = sources[c["source"]]
        entries = []
        try:  # a clip that cannot be cut or rendered fails alone, loudly; the others still go out
            segs = [resolve_segment(s["transcript"]["words"], x) for x in c["segments"]]
            total = sum(b - a for a, b in segs)
            if not lo <= total <= hi:
                raise ValueError(f"{total:.1f}s after finding the text in the transcript, the campaign takes {lo:g} to {hi:g}s")
            cap_words = fix_words(fix_phrases(s["transcript"]["words"], job.get("fixPhrases")), job.get("fixWords"))
            ov = overlays_for(job, c, watermark)
            kw = {"overlays": ov} if ov else {}  # renders without overlays keep the plain call
            for p in plats:
                res = render(s["media"], segs, cap_words, c["hook"], p,
                             odir / f"{c['id']}-{p}.mp4", c.get("layout", "auto"), wdir / "render", **kw)
                entry = {"clip": c["id"], **res, **post_text(job, c, p)}
                if d:
                    entry["disclosure"] = manifest_disclosure(d)
                entries.append(entry)
        except Exception as e:
            failed_clips[c["id"]] = str(e)[-500:]
            alarm(f"clip {c['id']} failed", failed_clips[c["id"]])
            for p in plats:  # no half-rendered clip reaches the media branch
                (odir / f"{c['id']}-{p}.mp4").unlink(missing_ok=True)
            continue
        rendered += entries
    stage = "failed" if failed_clips and not rendered else "rendered"
    manifest = {"id": jid, "stage": stage, "campaign": job.get("campaign", {}), "files": rendered}
    if failed_clips:
        manifest["failedClips"] = failed_clips
    if failed:
        manifest["failed"] = failed
    write_json(odir / "manifest.json", manifest)
    if stage == "failed":
        raise SystemExit(f"no clip rendered, {len(failed_clips)} failed: {failed_clips}")
    return manifest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("job")
    ap.add_argument("--work", default="work")
    ap.add_argument("--out", default="out")
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    res = run_job(a.job, a.work, a.out, a.only)
    print({k: v for k, v in res.items() if k not in ("files", "campaign")}, len(res.get("files", [])), "files")


if __name__ == "__main__":
    main()
