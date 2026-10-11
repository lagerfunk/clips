"""Calendar posting tests with a fake Buffer and fake HEAD requests: no network, no API key."""
import json
import re
import shutil
import tempfile
import unittest
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from clips import buffer
from clips import schedule as sch
from clips.common import write_json

JOB = "2026-10-11-founders"
ACCOUNT = "nocode.founders"
CHANNELS = [
    {"id": "yt1", "name": "nocode.founders", "service": "youtube"},
    {"id": "tt1", "name": "nocodefounders", "service": "tiktok"},
    {"id": "ig1", "name": "NoCode Founders", "service": "instagram"},
    {"id": "yt2", "name": "Other Games", "service": "youtube"},
]


def utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


class FakeBuffer:
    """Answers the GraphQL calls clips.schedule makes and remembers what was created."""

    def __init__(self, waiting=None, page=5):
        self.waiting = list(waiting or [])
        self.created = []
        self.page = page

    def channels(self, key=None):
        return [dict(c) for c in CHANNELS]

    def gql(self, query, variables=None, key=None):
        if "createPost" in query:
            inp = variables["input"]
            pid = f"post-{len(self.created) + 1}"
            self.created.append(inp)
            self.waiting.append({"id": pid, "text": inp["text"], "dueAt": inp["dueAt"], "channelId": inp["channelId"]})
            return {"createPost": {"post": {"id": pid, "status": "scheduled", "dueAt": inp["dueAt"]}}}
        if "organizations" in query:
            return {"account": {"organizations": [{"id": "org1"}]}}
        if "posts(" in query:
            assert "status: [scheduled]" in query and '"org1"' in query
            m = re.search(r'after: "(\d+)"', query)
            start = int(m.group(1)) if m else 0
            nodes = self.waiting[start:start + self.page]
            more = start + self.page < len(self.waiting)
            return {"posts": {"edges": [{"node": n} for n in nodes],
                              "pageInfo": {"hasNextPage": more, "endCursor": str(start + self.page) if more else None}}}
        raise AssertionError(f"unexpected query: {query[:80]}")


class FakeHead:
    """Stands in for urllib.request.urlopen: HEAD only, 404 for the URLs in `missing`."""

    def __init__(self, missing=()):
        self.missing = set(missing)
        self.urls = []

    def __call__(self, req, timeout=None):
        assert req.get_method() == "HEAD"
        url = req.full_url
        self.urls.append(url)
        if any(url.endswith(m) for m in self.missing):
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return mock.MagicMock(status=200, __enter__=lambda s: s, __exit__=lambda s, *a: False)


class Schedule(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="schedtest-"))
        self.results = self.tmp / "results"
        self.ledger = self.results / "_schedule" / "queued.json"
        self.cal = self.tmp / "calendar" / "week.json"
        files = [{"clip": c, "platform": p, "out": f"out/{JOB}/{c}-{p}.mp4", "title": f"Title {c}",
                  "caption": f"#ad Clip {c} story\n\n#ai #founders", "tags": ["#ad", "#ai"]}
                 for c in ("01", "02", "03", "04", "05", "06") for p in ("tiktok", "youtube", "instagram")]
        write_json(self.results / JOB / "manifest.json", {"id": JOB, "stage": "rendered", "campaign": {}, "files": files})

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_cal(self, posts, tz="Europe/Berlin"):
        write_json(self.cal, {"timezone": tz, "posts": posts})

    def post(self, at, platform="youtube", clip="01", account=ACCOUNT, job=JOB):
        return {"at": at, "account": account, "platform": platform, "job": job, "clip": clip}

    def run_sched(self, now, fake, head=None, dry_run=False, horizon=30, **kw):
        head = head or FakeHead()
        with mock.patch.object(buffer, "gql", fake.gql), mock.patch.object(buffer, "channels", fake.channels), \
                mock.patch.object(sch.urllib.request, "urlopen", head):
            return sch.run([str(self.cal)], horizon, dry_run, now, str(self.results), str(self.ledger),
                           repo="owner/clips", key=None if dry_run else "test-key", **kw)

    # ------------------------------------------------------------ plan

    def test_plan_same_order_on_every_platform_with_offset(self):
        cal, added = sch.plan(JOB, "2026-10-13", ["19:00", "12:00", "16:00"], ["youtube", "tiktok", "instagram"],
                              ["01", "02", "03", "04"], ACCOUNT, offsets={"instagram": 1})
        self.assertEqual(added, 12)
        self.assertEqual(cal["timezone"], "Europe/Berlin")
        by = {p: [(x["at"], x["clip"]) for x in cal["posts"] if x["platform"] == p] for p in ("youtube", "tiktok", "instagram")}
        self.assertEqual(by["youtube"], [("2026-10-13T12:00", "01"), ("2026-10-13T16:00", "02"),
                                         ("2026-10-13T19:00", "03"), ("2026-10-14T12:00", "04")])
        self.assertEqual(by["tiktok"], by["youtube"])
        self.assertEqual(by["instagram"], [("2026-10-14T12:00", "01"), ("2026-10-14T16:00", "02"),
                                           ("2026-10-14T19:00", "03"), ("2026-10-15T12:00", "04")])
        self.assertTrue(all(x["account"] == ACCOUNT and x["job"] == JOB for x in cal["posts"]))
        self.assertEqual([x["at"] for x in cal["posts"]], sorted(x["at"] for x in cal["posts"]))

        again, n = sch.plan(JOB, "2026-10-13", ["12:00", "16:00", "19:00"], ["youtube", "tiktok", "instagram"],
                            ["01", "02", "03", "04"], ACCOUNT, existing=cal, offsets={"instagram": 1})
        self.assertEqual((n, len(again["posts"])), (0, 12), "running the same plan again adds nothing")
        more, n = sch.plan("2026-10-12-other", "2026-10-16", ["12:00"], ["youtube"], ["01"], ACCOUNT, existing=cal)
        self.assertEqual((n, len(more["posts"])), (1, 13), "another job extends the file")
        with self.assertRaisesRegex(ValueError, "more than 3"):
            sch.plan("2026-10-12-other", "2026-10-14", ["13:00", "17:00", "20:00"], ["youtube"], ["01", "02", "03"],
                     ACCOUNT, existing=cal)
        with self.assertRaisesRegex(ValueError, "same time"):
            sch.plan("2026-10-12-other", "2026-10-13", ["12:00"], ["youtube"], ["01"], ACCOUNT, existing=cal)
        with self.assertRaisesRegex(ValueError, "1 to 3 times"):
            sch.plan(JOB, "2026-10-13", ["09:00", "12:00", "16:00", "19:00"], ["youtube"], ["01"], ACCOUNT)
        with self.assertRaises(ValueError):
            sch.plan(JOB, "2026-10-13", ["12:00"], ["youtube"], ["01"], ACCOUNT, offsets={"instagram": 1})

    def test_plan_command_writes_the_file(self):
        out = self.tmp / "calendar" / "w.json"
        code = sch.main(["plan", "--job", JOB, "--start", "2026-10-13", "--times", "12:00,19:00", "--platforms",
                         "youtube,instagram", "--order", "02,01", "--account", ACCOUNT, "--offset", "instagram=2",
                         "--out", str(out)])
        self.assertEqual(code, 0)
        posts = json.loads(out.read_text())["posts"]
        self.assertIn({"at": "2026-10-15T19:00", "account": ACCOUNT, "platform": "instagram", "job": JOB, "clip": "01"}, posts)
        self.assertEqual(len(posts), 4)

    # ------------------------------------------------------------ time

    def test_due_window(self):
        now = utc("2026-10-13T10:00:00")  # 12:00 in Berlin (summer time)
        self.write_cal([self.post("2026-10-13T11:00", clip="01"),   # an hour ago
                        self.post("2026-10-13T12:03", clip="02"),   # in 3 minutes: too close to hand over
                        self.post("2026-10-13T14:00", clip="03"),   # in 2 hours
                        self.post("2026-10-14T17:30", clip="04"),   # in 29.5 hours
                        self.post("2026-10-14T18:30", clip="05")])  # in 30.5 hours: next run
        posts, invalid = sch.load_posts([str(self.cal)])
        self.assertEqual(invalid, [])
        due = sch.select_due(posts, now, 30)
        self.assertEqual([p["clip"] for p in due], ["03", "04"])
        rep = self.run_sched(now, FakeBuffer(), dry_run=True)
        self.assertEqual([x["clip"] for x in rep["queued"]], ["03", "04"])
        self.assertEqual(sorted(x["clip"] for x in rep["missed"]), ["01", "02"])
        self.assertFalse(self.ledger.exists(), "a dry run writes no ledger")

    def test_berlin_to_utc_across_the_25_october_2026_clock_change(self):
        self.assertEqual(sch.iso_z(sch.to_utc("2026-10-24T19:00")), "2026-10-24T17:00:00.000Z")  # CEST, UTC+2
        self.assertEqual(sch.iso_z(sch.to_utc("2026-10-25T19:00")), "2026-10-25T18:00:00.000Z")  # CET, UTC+1
        self.assertEqual(sch.iso_z(sch.to_utc("2026-10-25T01:30")), "2026-10-24T23:30:00.000Z")
        self.assertEqual(sch.iso_z(sch.to_utc("2026-10-25T02:30")), "2026-10-25T00:30:00.000Z")  # first of the two
        self.assertEqual(sch.iso_z(sch.to_utc("2026-10-25T03:30")), "2026-10-25T02:30:00.000Z")
        # 31 local hours apart but 30 real hours: the second post is exactly at the horizon and goes out too
        self.write_cal([self.post("2026-10-24T19:00", clip="01"), self.post("2026-10-25T19:00", clip="02")])
        fake = FakeBuffer()
        rep = self.run_sched(utc("2026-10-24T12:00:00"), fake)
        self.assertEqual([i["dueAt"] for i in fake.created], ["2026-10-24T17:00:00.000Z", "2026-10-25T18:00:00.000Z"])
        self.assertTrue(all(i["mode"] == "customScheduled" and i["schedulingType"] == "automatic" for i in fake.created))
        self.assertEqual(len(rep["queued"]), 2)

    # ------------------------------------------------------------ ledger

    def test_ledger_makes_reruns_safe(self):
        now = utc("2026-10-13T06:00:00")
        self.write_cal([self.post("2026-10-13T12:00", "youtube", "01"), self.post("2026-10-13T12:00", "tiktok", "01"),
                        self.post("2026-10-13T16:00", "instagram", "02")])
        fake = FakeBuffer()
        rep = self.run_sched(now, fake)
        self.assertEqual(len(fake.created), 3)
        first = fake.created[0]
        self.assertEqual(first["channelId"], "tt1")
        self.assertEqual(first["assets"][0]["video"]["url"],
                         f"https://raw.githubusercontent.com/owner/clips/media/{JOB}/01-tiktok.mp4")
        self.assertTrue(first["text"].startswith("#ad Clip 01"))
        yt = next(i for i in fake.created if i["channelId"] == "yt1")
        self.assertEqual(yt["metadata"]["youtube"]["title"], "Title 01")
        led = json.loads(self.ledger.read_text())["posts"]
        self.assertEqual(sorted(led), [f"{JOB}/01-tiktok.mp4", f"{JOB}/01-youtube.mp4", f"{JOB}/02-instagram.mp4"])
        self.assertEqual(led[f"{JOB}/01-youtube.mp4"]["dueAt"], "2026-10-13T10:00:00.000Z")
        self.assertTrue(all(e["post"].startswith("post-") for e in led.values()))
        self.assertEqual(len(rep["queued"]), 3)

        for later in (now, now + timedelta(hours=1)):
            rep = self.run_sched(later, fake)
            self.assertEqual(len(fake.created), 3, "nothing in the ledger is sent again")
            self.assertEqual(len(rep["already"]), 3)

        self.ledger.unlink()  # ledger lost (for example the commit failed): Buffer's own list prevents doubles
        rep = self.run_sched(now + timedelta(hours=2), fake)
        self.assertEqual(len(fake.created), 3)
        self.assertEqual(len(rep["adopted"]), 3)
        self.assertEqual(len(json.loads(self.ledger.read_text())["posts"]), 3)

    def test_one_file_never_on_two_accounts_and_three_a_day(self):
        now = utc("2026-10-13T06:00:00")
        write_json(self.cal.parent / "accounts.json", {"second.channel": {"youtube": "Other Games"}})
        self.write_cal([self.post("2026-10-13T12:00", "youtube", "01"),
                        self.post("2026-10-13T13:00", "youtube", "01", account="second.channel"),
                        self.post("2026-10-13T14:00", "youtube", "02", account="second.channel"),
                        self.post("2026-10-13T15:00", "youtube", "03"),
                        self.post("2026-10-13T16:00", "youtube", "04"),
                        self.post("2026-10-13T17:00", "youtube", "05")])
        fake = FakeBuffer()
        rep = self.run_sched(now, fake)
        made = [(i["channelId"], i["assets"][0]["video"]["url"].rsplit("/", 1)[1]) for i in fake.created]
        self.assertEqual(made, [("yt1", "01-youtube.mp4"), ("yt2", "02-youtube.mp4"), ("yt1", "03-youtube.mp4"),
                                ("yt1", "04-youtube.mp4")])
        why = {x["clip"] + x["account"]: x["why"] for x in rep["skipped"]}
        self.assertIn("already queued for nocode.founders", why["01second.channel"])
        self.assertIn("already has 3 youtube posts", why["05" + ACCOUNT])

    def test_cap_of_nine_waiting_posts_per_channel(self):
        now = utc("2026-10-13T06:00:00")
        others = [{"id": f"old{i}", "text": f"older post {i}", "dueAt": f"2026-10-1{4 + i // 3}T0{i % 3}:00:00.000Z",
                   "channelId": "yt1"} for i in range(8)]
        others.append({"id": "tt-old", "text": "x", "dueAt": "2026-10-14T00:00:00.000Z", "channelId": "tt1"})
        fake = FakeBuffer(others, page=4)  # 9 waiting posts come back over 3 pages
        self.write_cal([self.post("2026-10-13T12:00", "youtube", "01"), self.post("2026-10-13T16:00", "youtube", "02"),
                        self.post("2026-10-13T19:00", "youtube", "03"), self.post("2026-10-13T12:00", "tiktok", "01")])
        rep = self.run_sched(now, fake)
        self.assertEqual(sorted((i["channelId"], i["dueAt"]) for i in fake.created),
                         [("tt1", "2026-10-13T10:00:00.000Z"), ("yt1", "2026-10-13T10:00:00.000Z")])
        full = [x for x in rep["skipped"] if "cap 9" in x["why"]]
        self.assertEqual([x["clip"] for x in full], ["02", "03"])
        self.assertNotIn(f"{JOB}/02-youtube.mp4", json.loads(self.ledger.read_text())["posts"])

    # ------------------------------------------------------------ media and text

    def test_missing_media_is_skipped_reported_and_retried(self):
        now = utc("2026-10-13T06:00:00")
        self.write_cal([self.post("2026-10-13T12:00", "youtube", "01"), self.post("2026-10-13T16:00", "youtube", "02")])
        fake, head = FakeBuffer(), FakeHead(missing={"02-youtube.mp4"})
        rep = self.run_sched(now, fake, head)
        self.assertEqual([i["dueAt"] for i in fake.created], ["2026-10-13T10:00:00.000Z"])
        self.assertEqual(len(rep["skipped"]), 1)
        self.assertIn("video not reachable (404)", rep["skipped"][0]["why"])
        self.assertIn(f"/media/{JOB}/02-youtube.mp4", rep["skipped"][0]["why"])
        self.assertEqual(sch.urgent(rep, now), [], "due in 8 hours: reported, not yet a failed run")
        self.assertEqual(len(sch.urgent(rep, utc("2026-10-13T12:00:00"))), 1)
        self.assertEqual(len(head.urls), 2)
        rep = self.run_sched(now + timedelta(hours=1), fake, FakeHead())
        self.assertEqual(len(fake.created), 2, "the next run queues it once the video is there")
        self.assertEqual([x["clip"] for x in rep["queued"]], ["02"])

    def test_caption_without_ad_label_and_unknown_clip_are_skipped(self):
        m = json.loads((self.results / JOB / "manifest.json").read_text())
        m["files"][0]["caption"] = "Clip 01 with no label #adventure"  # tiktok 01
        write_json(self.results / JOB / "manifest.json", m)
        self.write_cal([self.post("2026-10-13T12:00", "tiktok", "01"), self.post("2026-10-13T12:00", "youtube", "99"),
                        {"at": "2026-10-13 12:00", "account": ACCOUNT, "platform": "youtube", "job": JOB, "clip": "02"}])
        fake = FakeBuffer()
        rep = self.run_sched(utc("2026-10-13T06:00:00"), fake)
        self.assertEqual(fake.created, [])
        self.assertEqual(sorted(x["why"] for x in rep["skipped"]),
                         ["clip 99 has no youtube render in job " + JOB, "the caption has no ad label"])
        self.assertEqual(len(rep["invalid"]), 1)
        self.assertIn("YYYY-MM-DDTHH:MM", rep["invalid"][0]["why"])


if __name__ == "__main__":
    unittest.main()


class NotifyPlatforms(unittest.TestCase):
    def test_notify_platforms_are_loaded(self):
        import tempfile, json
        from clips.schedule import load_posts
        d = tempfile.mkdtemp()
        f = f"{d}/c.json"
        json.dump({"timezone": "Europe/Berlin", "notify": ["tiktok"], "posts": [
            {"at": "2026-10-13T20:00", "account": "nocode.founders", "platform": "tiktok", "job": "j", "clip": "c1"},
            {"at": "2026-10-13T20:00", "account": "nocode.founders", "platform": "youtube", "job": "j", "clip": "c1"}]}, open(f, "w"))
        posts, bad = load_posts([f])
        self.assertEqual(bad, [])
        self.assertEqual({p["platform"]: p["notify"] for p in posts}, {"tiktok": True, "youtube": False})

