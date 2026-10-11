"""Stats report tests with mocked HTTP: no network, no keys."""
import io
import json
import shutil
import tempfile
import unittest
import urllib.parse
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path

from clips import stats

NOW = datetime(2026, 11, 20, 6, 41, tzinfo=timezone.utc)
SINCE = datetime(2026, 10, 1, tzinfo=timezone.utc)
KEY, CHAN = "AIzaFAKEKEY123", "UCsecretchannel000000001"


def ts(days_ago):
    return (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


class FakeYouTube:
    """Answers channels, playlistItems and videos like the Data API v3, three pages of uploads."""

    def __init__(self):
        self.calls = []
        fresh = [(f"vid{i:08d}", ts(1 + i * 0.1)) for i in range(75)]
        old = [(f"old{i:08d}", "2024-05-01T10:00:00Z") for i in range(75)]
        self.pages = {None: (fresh[:50], "p2"), "p2": (fresh[50:] + old[:25], "p3"), "p3": (old[25:75], "p4"),
                      "p4": ([], None)}

    def __call__(self, url):
        u = urllib.parse.urlparse(url)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        method = u.path.rsplit("/", 1)[-1]
        self.calls.append((method, q))
        assert q["key"] == KEY
        if method == "channels":
            items = [{"id": CHAN, "snippet": {"title": "nocode.founders"},
                      "contentDetails": {"relatedPlaylists": {"uploads": "UU" + CHAN[2:]}}}] if q.get("id") == CHAN else []
            return {"items": items}
        if method == "playlistItems":
            items, nxt = self.pages[q.get("pageToken")]
            out = {"items": [{"contentDetails": {"videoId": v, "videoPublishedAt": p}} for v, p in items]}
            if nxt:
                out["nextPageToken"] = nxt
            return out
        if method == "videos":
            ids = q["id"].split(",")
            assert len(ids) <= 50
            items = []
            for v in ids:
                if v == "vid00000003":
                    continue  # deleted
                n = int(v[3:])
                dur = "PT12M5S" if v == "vid00000004" else "PT41S"
                items.append({"id": v, "contentDetails": {"duration": dur},
                              "statistics": {"viewCount": str(n * 100), "likeCount": str(n), "commentCount": "1"}})
            return {"items": items}
        raise AssertionError(method)


class YouTubeSource(unittest.TestCase):
    def test_pagination_stops_at_old_page_and_batches_by_50(self):
        fake = FakeYouTube()
        posts, info = stats.yt_collect(KEY, [CHAN], SINCE, get=fake)
        methods = [m for m, _ in fake.calls]
        self.assertEqual(methods, ["channels", "playlistItems", "playlistItems", "playlistItems", "videos", "videos"])
        self.assertNotIn("p4", [q.get("pageToken") for _, q in fake.calls])
        self.assertEqual([len(q["id"].split(",")) for m, q in fake.calls if m == "videos"], [50, 25])
        self.assertEqual(info["units"], 6)
        self.assertEqual(len(posts), 73)  # 75 fresh, one deleted, one long-form video left out
        p = next(x for x in posts if x["id"] == "vid00000010")
        self.assertEqual((p["views"], p["likes"], p["comments"], p["account"]), (1000, 10, 1, "nocode.founders"))
        self.assertEqual(p["url"], "https://www.youtube.com/shorts/vid00000010")
        self.assertNotIn(CHAN, json.dumps([{**x, "published": str(x["published"])} for x in posts]))

    def test_quota_budget_stops_cleanly(self):
        posts, info = stats.yt_collect(KEY, [CHAN], SINCE, get=FakeYouTube(), max_units=2)
        self.assertEqual(posts, [])
        self.assertTrue(info["errors"] and "quota budget" in info["errors"][0])

    def test_unknown_channel_counts_as_unresolved(self):
        posts, info = stats.yt_collect(KEY, ["UCnope"], SINCE, get=FakeYouTube())
        self.assertEqual((posts, info["unresolved"], info["units"]), ([], 1, 1))

    def test_duration_parsing(self):
        self.assertEqual(stats.iso_seconds("PT41S"), 41)
        self.assertEqual(stats.iso_seconds("PT1M"), 60)
        self.assertEqual(stats.iso_seconds("PT1H2M3S"), 3723)
        self.assertEqual(stats.iso_seconds("P1D"), 86400)


class FakeBuffer:
    def __init__(self, refuse_metrics=False):
        self.refuse, self.queries = refuse_metrics, []

    def __call__(self, query, variables=None, key=None):
        self.queries.append(query)
        if "organizations" in query:
            return {"account": {"organizations": [{"id": "org1"}]}}
        if "channels(" in query:
            return {"channels": [{"id": "c-tt", "name": "nocode.founders", "service": "tiktok"},
                                 {"id": "c-yt", "name": "nocode.founders", "service": "youtube"}]}
        if "metrics" in query and self.refuse:
            raise RuntimeError("Buffer error: not authorised to read insights")
        page2 = 'after: "cur1"' in query
        nodes = [{"id": "b3", "channelId": "c-tt", "channelService": "tiktok", "sentAt": ts(9),
                  "externalLink": "https://www.tiktok.com/@nocode.founders/video/7300000000000000003",
                  "metrics": [{"type": "views", "value": 2500.0}, {"type": "likes", "value": 40.0}]}] if page2 else [
            {"id": "b1", "channelId": "c-tt", "channelService": "tiktok", "sentAt": ts(3),
             "externalLink": "https://www.tiktok.com/@nocode.founders/video/7300000000000000001",
             "metrics": [{"type": "views", "value": 120.0}, {"type": "comments", "value": 2.0}]},
            {"id": "b2", "channelId": "c-yt", "channelService": "youtube", "sentAt": ts(1 + 1.0),
             "externalLink": "https://www.youtube.com/shorts/vid00000010",
             "metrics": [{"type": "views", "value": 5.0}]},
            {"id": "b0", "channelId": "c-tt", "channelService": "tiktok", "sentAt": "2026-09-01T00:00:00Z",
             "externalLink": "https://www.tiktok.com/@x/video/1", "metrics": []}]
        if self.refuse:
            nodes = [{k: v for k, v in n.items() if k != "metrics"} for n in nodes]
        return {"posts": {"edges": [{"node": n} for n in nodes],
                          "pageInfo": {"hasNextPage": not page2, "endCursor": "cur1"}}}


class BufferSource(unittest.TestCase):
    def test_sent_posts_with_metrics_and_paging(self):
        fake = FakeBuffer()
        posts, info = stats.buffer_collect("bufkey", SINCE, gql=fake)
        self.assertTrue(info["metrics"])
        self.assertEqual(sorted(p["id"] for p in posts), ["7300000000000000001", "7300000000000000003", "vid00000010"])
        self.assertIn("status: [sent]", fake.queries[2])
        self.assertIn("externalLink", fake.queries[2])
        tt = next(p for p in posts if p["id"].endswith("3"))
        self.assertEqual((tt["views"], tt["likes"], tt["platform"]), (2500, 40, "tiktok"))

    def test_links_only_when_metrics_refused(self):
        posts, info = stats.buffer_collect("bufkey", SINCE, gql=FakeBuffer(refuse_metrics=True))
        self.assertFalse(info["metrics"])
        self.assertEqual(info["errors"], [])
        self.assertEqual(len(posts), 3)
        self.assertTrue(all(p["views"] is None and p["url"] for p in posts))

    def test_youtube_api_numbers_win_over_buffer(self):
        yt, _ = stats.yt_collect(KEY, [CHAN], SINCE, get=FakeYouTube())
        buf, _ = stats.buffer_collect("bufkey", SINCE, gql=FakeBuffer())
        rows = stats.merge(yt, buf)
        v = [r for r in rows if r["id"] == "vid00000010"]
        self.assertEqual((len(v), v[0]["views"], v[0]["source"]), (1, 1000, "youtube"))


def row(views, age, pub_age=None, rid=None, plat="tiktok", acc="nocode.founders"):
    return {"platform": plat, "account": acc, "id": rid or f"id{views}-{age}", "url": f"https://x/{views}",
            "views": views, "age_days": age, "published": ts(age if pub_age is None else pub_age)}


class Maths(unittest.TestCase):
    def test_median_only_counts_posts_older_than_48h(self):
        rows = [row(100, 3), row(300, 4), row(900, 5), row(50000, 1), row(None, 6)]
        m = stats.measure(rows, {})
        self.assertEqual((m["median_48h"], m["n_48h"]), (300, 3))

    def test_share_over_1000_within_7_days_uses_history(self):
        rows = [row(1500, 10, rid="a"), row(1500, 10, rid="b"), row(200, 8, rid="c"), row(5000, 2, rid="d")]
        hist = {("tiktok", "a"): [(6.9, 1200)], ("tiktok", "b"): [(6.9, 700), (7.9, 1400)]}
        m = stats.measure(rows, hist)
        # a reached 1,000 by day 7; b only later; c never; d is too young to judge
        self.assertEqual((m["hit_7d"], m["n_7d"]), (1, 3))
        self.assertAlmostEqual(m["share_7d"], 1 / 3)

    def test_without_early_reading_today_stands_in(self):
        self.assertEqual(stats.views_7d(row(1500, 10, rid="z"), {}), 1500)

    def test_day_14_reformat_pass_and_early(self):
        weak = [row(100, 15, rid="w1"), row(250, 12, rid="w2"), row(400, 9, rid="w3")]
        day, chk = stats.check(weak, {}, NOW)
        self.assertEqual((day, chk["status"]), (15, "reformat"))
        strong = [row(400, 15, rid="s1"), row(1200, 12, rid="s2"), row(300, 9, rid="s3")]
        self.assertEqual(stats.check(strong, {}, NOW)[1]["status"], "pass")
        # median fine but nobody over 1,000 in 7 days: still reformat
        flat = [row(400, 15, rid="f1"), row(500, 12, rid="f2"), row(600, 9, rid="f3")]
        self.assertEqual(stats.check(flat, {}, NOW)[1]["status"], "reformat")
        day, chk = stats.check([row(100, 5)], {}, NOW)
        self.assertEqual((day, chk["status"]), (5, "early"))
        self.assertIn((NOW + timedelta(days=9)).strftime("%Y-%m-%d"), chk["text"])

    def test_day_28_kill_flag_judges_posts_since_day_14(self):
        rows = [row(5000, 30, rid="k0"), row(100, 14, rid="k1"), row(150, 10, rid="k2"), row(80, 8, rid="k3")]
        day, chk = stats.check(rows, {}, NOW)
        self.assertEqual((day, chk["status"]), (30, "kill"))
        self.assertIn("posts since day 14", chk["text"])
        good = [row(100, 30, rid="g0"), row(1500, 14, rid="g1"), row(400, 10, rid="g2"), row(350, 8, rid="g3")]
        self.assertEqual(stats.check(good, {}, NOW)[1]["status"], "pass")


class EndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="statstest-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_missing_secrets_skip_cleanly(self):
        def boom(*a, **k):
            raise AssertionError("no network without secrets")
        out = io.StringIO()
        with redirect_stdout(out):
            rc = stats.run(self.tmp, {}, now=NOW, yt_get=boom, gql=boom, tg_post=boom)
            rc2 = stats.run(self.tmp, {"YT_API_KEY": KEY}, now=NOW, yt_get=boom, gql=boom, tg_post=boom)
        self.assertEqual((rc, rc2), (0, 0))
        self.assertEqual(list(self.tmp.iterdir()), [])
        self.assertIn("nothing to do", out.getvalue())

    def test_report_files_telegram_and_no_secrets_or_dashes(self):
        old = {"date": "2026-11-15", "posts": [{"platform": "youtube", "id": "vid00000010", "age_days": 4, "views": 1100}]}
        (self.tmp / "2026-11-15.json").write_text(json.dumps(old))
        sent = []
        env = {"YT_API_KEY": KEY, "YT_CHANNEL_IDS": f" {CHAN} , ", "BUFFER_API_KEY": "bufkey-secret",
               "TELEGRAM_BOT_TOKEN": "123:tgsecret", "CLIPS_CHAT_ID": "-100777"}
        fake_buf = FakeBuffer()
        real = fake_buf.__call__

        def buf_with_dash(query, variables=None, key=None):
            res = real(query, variables, key)
            if "channels" in res:
                res["channels"][0]["name"] = "nocode\u2014founders"
            return res
        out = io.StringIO()
        with redirect_stdout(out):
            rc = stats.run(self.tmp, env, now=NOW, yt_get=FakeYouTube(), gql=buf_with_dash, tg_post=sent.append)
        self.assertEqual(rc, 0)
        data = json.loads((self.tmp / "2026-11-20.json").read_text())
        md = (self.tmp / "latest.md").read_text()
        self.assertEqual(len(data["posts"]), 75)  # 73 Shorts plus 2 TikToks, the shared YouTube video once
        r = next(p for p in data["posts"] if p["id"] == "vid00000010")
        self.assertEqual(set(r), {"platform", "account", "id", "url", "published", "views", "likes", "comments",
                                  "age_days", "source"})
        self.assertNotIn("\u2014", md)
        self.assertNotIn("\u2013", md)
        self.assertIn("## nocode.founders on YouTube", md)
        self.assertIn("Median views, posts older than 48 h", md)
        self.assertEqual(len(sent), 1)
        self.assertEqual(urllib.parse.parse_qs(sent[0].decode())["text"][0], md)
        blob = out.getvalue() + md + json.dumps(data)
        for secret in (KEY, CHAN, "bufkey-secret", "tgsecret", "-100777"):
            self.assertNotIn(secret, blob)

    def test_source_error_is_reported_without_the_key(self):
        def bad_get(url):
            raise RuntimeError(f"failed {url}")  # worst case: an error that carries the URL with the key in it
        out = io.StringIO()
        with redirect_stdout(out):
            rc = stats.run(self.tmp, {"YT_API_KEY": KEY, "YT_CHANNEL_IDS": CHAN}, now=NOW, yt_get=bad_get, send=False)
        self.assertEqual(rc, 2)
        text = out.getvalue() + (self.tmp / "latest.md").read_text() + (self.tmp / "2026-11-20.json").read_text()
        self.assertNotIn(KEY, text)
        self.assertNotIn(CHAN, text)
        self.assertIn("error", text)


if __name__ == "__main__":
    unittest.main()
