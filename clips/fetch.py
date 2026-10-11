"""Download a campaign source video: Google Drive (file or folder), WeTransfer, a direct file URL, or a VOD page (yt-dlp).
Also fetches small campaign assets (a watermark image from a Drive folder or file).

Only sources the campaign itself provides or allows are used; the job file records where each one came from.

WeTransfer (we.tl/... or wetransfer.com/downloads/<transfer_id>/<security_hash>, or .../<transfer_id>/<recipient_id>/
<security_hash> for e-mailed transfers) follows the flow of the open-source transferwee tool (PyPI transferwee 1.0.2,
download_url and _prepare_session): open the link (cookies, CSRF token when the page has one), POST
{"security_hash", "intent": "entire_transfer"[, "recipient_id"]} to /api/v4/transfers/<transfer_id>/download and fetch
the "direct_link" it returns. A transfer of several files arrives as one zip: the largest video in it is kept.
A captcha or bot check is never bypassed: the run stops with a message asking the owner to re-upload to Google Drive.
"""
import argparse
import email.message
import http.cookiejar
import json
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
IMAGE_EXT = {".png", ".webp", ".jpg", ".jpeg"}

UA = "Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0"
WT_HOME = "https://wetransfer.com/"
WT_DOWNLOAD_API = "https://wetransfer.com/api/v4/transfers/{transfer_id}/download"
REUPLOAD = ("The owner must download it in a browser and re-upload it to Google Drive (share: anyone with the link), "
            "then put the Drive link in the job's source url.")
CHALLENGE = ("cf-chl", "challenge-platform", "just a moment...", "captcha", "cf-turnstile", "attention required")
PAGE_CAP = 2_000_000  # bytes read from an HTML page or an API answer
CHUNK = 1 << 20
_sleep = time.sleep  # tests replace it


class WeTransferError(RuntimeError):
    """A WeTransfer link that cannot be downloaded; the message says what the owner has to do."""


def is_wetransfer(url):
    host = (urllib.parse.urlparse(str(url)).hostname or "").lower()
    return host == "we.tl" or host == "wetransfer.com" or host.endswith(".wetransfer.com")


def kind_of(url):
    if Path(url).exists():
        return "file"
    if is_wetransfer(url):
        return "wetransfer"
    if "drive.google.com" in url or "docs.google.com" in url:
        return "drive-folder" if "/folders/" in url else "drive"
    if any(h in url for h in ("youtube.com", "youtu.be", "twitch.tv", "kick.com", "tiktok.com", "instagram.com", "x.com", "twitter.com")):
        return "page"
    return "direct"


# ---------------------------------------------------------------- WeTransfer

def parse_wetransfer(url):
    """{"transfer_id", "security_hash", "recipient_id"} from a wetransfer.com/downloads/... link (not a we.tl short link).

    Two parts after /downloads/ are <transfer_id>/<security_hash>. Three parts are <transfer_id>/<recipient_id>/
    <security_hash> (transferwee's order); the security hash is the short one (6 characters), so a link written the
    other way round is read correctly too."""
    parts = [p for p in urllib.parse.urlparse(url).path.split("/") if p]
    if "downloads" not in parts:
        raise WeTransferError(f"WeTransfer: not a download link: {url}")
    parts = parts[parts.index("downloads") + 1:]
    if not all(re.fullmatch(r"[A-Za-z0-9_-]+", p) for p in parts) or len(parts) not in (2, 3):
        raise WeTransferError(f"WeTransfer: cannot read the transfer id and security hash from {url}")
    if len(parts) == 2:
        return {"transfer_id": parts[0], "security_hash": parts[1], "recipient_id": None}
    tid, mid, last = parts
    if len(mid) < len(last) and len(mid) <= 16:  # <transfer_id>/<security_hash>/<recipient_id>
        mid, last = last, mid
    return {"transfer_id": tid, "security_hash": last, "recipient_id": mid}


def download_request(ids, csrf=None, referer=None):
    """The POST that asks WeTransfer for the direct link of the whole transfer."""
    body = {"security_hash": ids["security_hash"], "intent": "entire_transfer"}
    if ids.get("recipient_id"):
        body["recipient_id"] = ids["recipient_id"]
    headers = {"User-Agent": UA, "Accept": "application/json", "Content-Type": "application/json",
               "X-Requested-With": "XMLHttpRequest", "Origin": "https://wetransfer.com",
               "Referer": referer or WT_HOME}
    if csrf:
        headers["X-CSRF-Token"] = csrf
    return urllib.request.Request(WT_DOWNLOAD_API.format(transfer_id=ids["transfer_id"]), method="POST",
                                  data=json.dumps(body).encode(), headers=headers)


def make_opener():
    """urllib opener with a cookie jar (WeTransfer sets session cookies on the page); proxies from the environment."""
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def _call(opener, req, timeout=60):
    """(status, headers, body, final_url) for a small response; HTTP errors are returned, not raised."""
    try:
        with opener.open(req, timeout=timeout) as r:
            return getattr(r, "status", 200), r.headers, r.read(PAGE_CAP), r.geturl()
    except urllib.error.HTTPError as e:
        try:
            body = e.read(PAGE_CAP)
        except Exception:
            body = b""
        return e.code, e.headers or email.message.Message(), body, getattr(e, "url", None) or req.full_url
    except urllib.error.URLError as e:
        raise WeTransferError(f"WeTransfer: could not reach {req.full_url}: {e.reason}") from e


def _challenged(status, headers, body, api=False):
    """True when the answer is a bot check or captcha (Cloudflare challenge, reCAPTCHA, hCaptcha, Turnstile).
    Only called on a failed answer, so a normal page that merely loads a captcha script is never mistaken for one."""
    if str(headers.get("cf-mitigated", "")).lower() == "challenge":
        return True
    text = body[:200_000].decode("utf-8", "replace").lower()
    if api and "captcha" in text:  # the API names it in its error, e.g. {"error": "captcha_required"}
        return True
    return status in (403, 429, 503) and any(m in text for m in CHALLENGE)


def _csrf(html):
    m = (re.search(r'name="csrf-token"\s+content="([^"]+)"', html)
         or re.search(r'content="([^"]+)"\s+name="csrf-token"', html))
    return m.group(1) if m else None


def direct_link(url, opener=None):
    """The signed download URL of the whole transfer. Raises WeTransferError with a plain reason."""
    opener = opener or make_opener()
    page = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*"})
    status, headers, body, final = _call(opener, page)
    if (status >= 400 or headers.get("cf-mitigated")) and _challenged(status, headers, body):
        raise WeTransferError(f"WeTransfer shows a captcha or bot check for this link (HTTP {status}); it is not bypassed. {REUPLOAD}")
    if status >= 400:
        raise WeTransferError(f"WeTransfer: the link answered HTTP {status}; it has probably expired or been deleted. {REUPLOAD}")
    try:
        ids = parse_wetransfer(final or url)
    except WeTransferError:
        raise WeTransferError(f"WeTransfer: {url} led to {final}, not to a download page (expired or deleted?). {REUPLOAD}")
    csrf = _csrf(body.decode("utf-8", "replace"))
    if not csrf:  # older pages carried the token only on the home page (transferwee's _prepare_session)
        s2, _, b2, _ = _call(opener, urllib.request.Request(WT_HOME, headers={"User-Agent": UA}))
        csrf = _csrf(b2.decode("utf-8", "replace")) if s2 < 400 else None
    status, headers, body, _ = _call(opener, download_request(ids, csrf, final or url))
    try:
        answer = json.loads(body.decode("utf-8", "replace") or "{}")
    except json.JSONDecodeError:
        answer = {}
    link = answer.get("direct_link") if isinstance(answer, dict) else None
    if status < 400 and link:
        return link
    if _challenged(status, headers, body, api=True):
        raise WeTransferError(f"WeTransfer asks for a captcha before the download (HTTP {status}); it is not bypassed. {REUPLOAD}")
    why = " ".join(str(answer.get(k)) for k in ("error", "message") if isinstance(answer, dict) and answer.get(k))
    why = why or body[:120].decode("utf-8", "replace").strip() or "no direct_link in the answer"
    raise WeTransferError(f"WeTransfer refused the download (HTTP {status}: {why[:160]}). Free transfers expire "
                          f"after a few days. {REUPLOAD}")


def _filename(headers, url, default="wetransfer-download"):
    cd = headers.get("Content-Disposition") or ""
    m = re.search(r"filename\*=UTF-8''([^;]+)", cd) or re.search(r'filename="?([^";]+)"?', cd)
    name = urllib.parse.unquote(m.group(1) if m else urllib.parse.urlparse(url).path.rsplit("/", 1)[-1])
    name = re.sub(r"[^\w.\- ()]+", "_", Path(name.replace("\\", "/")).name).strip(" .")
    return name or default


def stream_download(link, dest, opener=None, tries=3, timeout=120):
    """Download link into dest (a folder), resuming with a Range request after a dropped connection.
    Returns the file path; raises when the size does not match what the server announced."""
    opener = opener or make_opener()
    dest = Path(dest)
    part, name, total, last = None, None, None, None
    for attempt in range(1, tries + 1):
        have = part.stat().st_size if part and part.exists() else 0
        headers = {"User-Agent": UA}
        if have:
            headers["Range"] = f"bytes={have}-"
        try:
            with opener.open(urllib.request.Request(link, headers=headers), timeout=timeout) as r:
                status = getattr(r, "status", 200)
                if name is None:
                    name = _filename(r.headers, link)
                    part = dest / (name + ".part")
                if status == 206 and have:
                    m = re.search(r"/(\d+)$", r.headers.get("Content-Range", ""))
                    total = int(m.group(1)) if m else total
                    mode = "ab"
                else:
                    total = int(r.headers.get("Content-Length") or 0) or None
                    mode = "wb"
                with open(part, mode) as f:
                    shutil.copyfileobj(r, f, CHUNK)
            size = part.stat().st_size
            if total and size != total:
                raise IOError(f"got {size} of {total} bytes")
            target = dest / name
            part.replace(target)
            print(f"  downloaded {target.name} ({size >> 20} MB)")
            return target
        except urllib.error.HTTPError as e:
            raise WeTransferError(f"WeTransfer: the download link answered HTTP {e.code} (signed links expire "
                                  f"quickly, run the job again). {REUPLOAD}") from e
        except OSError as e:  # timeouts, resets, short reads (URLError is an OSError too)
            last = e
            print(f"  download interrupted ({e}), attempt {attempt} of {tries}")
            if attempt < tries:
                _sleep(min(30, 5 * attempt))
    raise WeTransferError(f"WeTransfer: download kept failing ({last}). {REUPLOAD}")


def extract_video(archive, dest, want=None):
    """The largest video in a zip (or the one named want), written into dest; the zip is deleted to save disk."""
    with zipfile.ZipFile(archive) as z:
        vids = [i for i in z.infolist() if not i.is_dir() and Path(i.filename).suffix.lower() in VIDEO_EXT
                and "__MACOSX/" not in i.filename and not Path(i.filename).name.startswith("._")]
        if not vids:
            names = ", ".join(i.filename for i in z.infolist()[:6]) or "nothing"
            raise WeTransferError(f"WeTransfer: the transfer holds no video file (found: {names}). {REUPLOAD}")
        pick = next((i for i in vids if want and Path(i.filename).name == want), None)
        pick = pick or max(vids, key=lambda i: i.file_size)
        target = Path(dest) / re.sub(r"[^\w.\- ()]+", "_", Path(pick.filename.replace("\\", "/")).name)
        with z.open(pick) as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out, CHUNK)
        if len(vids) > 1:
            print(f"  zip holds {len(vids)} videos, kept {target.name} ({pick.file_size >> 20} MB)")
    Path(archive).unlink()
    return target


def fetch_wetransfer(url, dest, want=None, opener=None):
    """The source video from a WeTransfer link. A finished download is reused on the next run in the same work dir."""
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    marker = dest / ".wetransfer.json"
    if marker.exists():
        done = json.loads(marker.read_text())
        if done.get("url") == url and (dest / done.get("file", "")).is_file():
            return dest / done["file"]
    opener = opener or make_opener()
    print(f"  WeTransfer: asking for the download link of {url}")
    got = stream_download(direct_link(url, opener), dest, opener)
    if zipfile.is_zipfile(got):
        got = extract_video(got, dest, want)
    elif got.suffix.lower() not in VIDEO_EXT:
        raise WeTransferError(f"WeTransfer: got {got.name}, which is neither a zip nor a video file. {REUPLOAD}")
    marker.write_text(json.dumps({"url": url, "file": got.name}))
    return got


# ---------------------------------------------------------------- sources

def fetch(url, dest_dir, want=None):
    """Returns the list of video files fetched (a Drive folder can hold several). want: a file name inside a folder or
    a WeTransfer zip."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    kind = kind_of(url)
    if kind == "file":
        target = dest / Path(url).name
        if Path(url).resolve() != target.resolve():
            shutil.copy(url, target)
        return [target]
    if kind == "wetransfer":
        return [fetch_wetransfer(url, dest, want)]
    if kind == "drive":
        subprocess.run(["gdown", "--fuzzy", url, "-O", str(dest) + "/"], check=True)
    elif kind == "drive-folder":
        subprocess.run(["gdown", "--folder", url, "-O", str(dest)], check=True)
    elif kind == "page":
        cmd = ["yt-dlp", "-f", "bv*[height<=1080]+ba/b[height<=1080]/b", "--merge-output-format", "mp4",
               "--retries", "3", "--extractor-args", "youtube:player_client=tv_simply,web_safari,mweb,default"]
        if shutil.which("deno"):
            cmd += ["--js-runtimes", "deno"]
        subprocess.run(cmd + ["-o", str(dest / "%(id)s.%(ext)s"), url], check=True)
    else:
        name = Path(url.split("?")[0]).name or "source.mp4"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=120) as r, open(dest / name, "wb") as f:
            shutil.copyfileobj(r, f)
    files = sorted(p for p in dest.rglob("*") if p.suffix.lower() in VIDEO_EXT)
    if not files:
        raise RuntimeError(f"no video found at {url}")
    return files


# ---------------------------------------------------------------- assets (watermark)

def has_alpha(path):
    """True when the image has at least one see-through pixel (read with ffmpeg, so PNG and WebP both work)."""
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-frames:v", "1", "-vf", "alphaextract",
                        "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True)
    return r.returncode == 0 and bool(r.stdout) and min(r.stdout) < 250


def pick_image(files, pick="png"):
    """pick "png": the first PNG with transparency, else the first image. Any other pick names the file (exact
    name, or a part of it, case ignored)."""
    files = sorted(files, key=lambda p: str(p).lower())
    if pick and pick.lower() not in ("png", "image", "any"):
        want = pick.lower()
        return next((f for f in files if f.name.lower() == want), None) or next((f for f in files if want in f.name.lower()), None)
    if (pick or "png").lower() == "png":
        clear = next((f for f in files if f.suffix.lower() == ".png" and has_alpha(f)), None)
        if clear:
            return clear
    return files[0] if files else None


def _images(folder):
    return [p for p in Path(folder).rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXT]


def _drive_folder_images(url, dest):
    """Only the image files of a public Drive folder (it may also hold large reference videos)."""
    try:
        import gdown
        listed = gdown.download_folder(url=url, output=str(dest), quiet=True, skip_download=True)
    except Exception as e:  # older gdown without skip_download, or a listing problem: plain folder download
        print(f"  Drive folder listing failed ({str(e)[:120]}), downloading the whole folder")
        subprocess.run(["gdown", "--folder", url, "-O", str(dest)], check=True)
        return
    wanted = [f for f in listed if Path(f.path).suffix.lower() in IMAGE_EXT]
    if not wanted:
        raise RuntimeError(f"the Drive folder holds no image (png, webp, jpg): {[f.path for f in listed][:8]}")
    for f in wanted:
        Path(f.local_path).parent.mkdir(parents=True, exist_ok=True)
        gdown.download(id=f.id, output=f.local_path, quiet=True)


def fetch_asset(url, dest_dir, pick="png"):
    """One image for a job (a watermark), fetched once: a later call with the same url reuses the stored file."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    marker = dest / ".asset-url"
    if not (marker.exists() and marker.read_text() == url and _images(dest)):
        if marker.exists() and marker.read_text() != url:  # our own folder, filled from another url: start clean
            for p in dest.iterdir():
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()
        kind = kind_of(url)
        if kind == "file":
            src = Path(url)
            if src.is_dir():
                shutil.copytree(src, dest, dirs_exist_ok=True)
            else:
                shutil.copy(src, dest / src.name)
        elif kind == "drive-folder":
            _drive_folder_images(url, dest)
        elif kind == "drive":
            subprocess.run(["gdown", "--fuzzy", url, "-O", str(dest) + "/"], check=True)
        elif kind == "direct":
            name = Path(urllib.parse.urlparse(url).path).name or "asset.png"
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as r, open(dest / name, "wb") as f:
                shutil.copyfileobj(r, f)
        else:
            raise RuntimeError(f"assets come from Google Drive, a direct image URL or a local file, not {kind}: {url}")
        marker.write_text(url)
    choice = pick_image(_images(dest), pick)
    if choice is None:
        found = [p.name for p in dest.rglob("*") if p.is_file() and p.name != marker.name][:8]
        raise RuntimeError(f"no image matching pick={pick!r} at {url} (found: {found or 'nothing'})")
    return choice


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("dest")
    ap.add_argument("--asset", metavar="PICK", help='fetch an image instead of a video, e.g. --asset png')
    a = ap.parse_args()
    if a.asset:
        print(fetch_asset(a.url, a.dest, a.asset))
        return
    for f in fetch(a.url, a.dest):
        print(f)


if __name__ == "__main__":
    main()
