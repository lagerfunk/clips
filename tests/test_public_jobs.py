"""Gated campaign links and member-only brief text never reach the public repo; the runner resolves them from a secret."""
import json
import os
import unittest
from unittest import mock

from clips.fetch import resolve, shown
from clips.public_jobs import private_table, sanitize_job

JOB = {"id": "x", "rules": "member-only brief", "campaign": {"brand": "B", "rules": "also private"},
       "sources": [{"id": "p1", "url": "https://we.tl/t-EXAMPLE12345"},
                   {"id": "p2", "url": "https://example.com/public.mp4"}],
       "assets": {"watermark": {"url": "https://drive.google.com/drive/folders/1EXAMPLE"}}}


class PublicJobs(unittest.TestCase):
    def test_sanitize_hides_links_and_brief(self):
        clean = sanitize_job(JOB, "2026-10-11-x")
        text = json.dumps(clean)
        self.assertNotIn("we.tl", text)
        self.assertNotIn("drive.google.com", text)
        self.assertNotIn("member-only", text)
        self.assertNotIn("also private", text)
        self.assertEqual(clean["sources"][0]["url"], "private:2026-10-11-x:p1")
        self.assertEqual(clean["sources"][1]["url"], "https://example.com/public.mp4", "public links stay")
        self.assertEqual(clean["assets"]["watermark"]["url"], "private:2026-10-11-x:asset-watermark")
        self.assertEqual(JOB["sources"][0]["url"], "https://we.tl/t-EXAMPLE12345", "the original is not changed")

    def test_resolve_from_secret(self):
        table = {"2026-10-11-x:p1": "https://we.tl/t-EXAMPLE12345"}
        with mock.patch.dict(os.environ, {"CLIP_PRIVATE_SOURCES": json.dumps(table)}):
            self.assertEqual(resolve("private:2026-10-11-x:p1"), "https://we.tl/t-EXAMPLE12345")
        with mock.patch.dict(os.environ, {"CLIP_PRIVATE_SOURCES": "{}"}):
            with self.assertRaises(RuntimeError):
                resolve("private:2026-10-11-x:p1")
        self.assertEqual(resolve("https://example.com/a.mp4"), "https://example.com/a.mp4")

    def test_logs_show_only_the_host(self):
        self.assertEqual(shown("https://we.tl/t-EXAMPLE12345"), "we.tl")
        self.assertEqual(shown("https://example.com/a.mp4"), "https://example.com/a.mp4")

    def test_private_table_round_trip(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            Path(d, "2026-10-11-x.json").write_text(json.dumps(JOB))
            table = private_table(d)
        self.assertEqual(table, {"2026-10-11-x:p1": "https://we.tl/t-EXAMPLE12345",
                                 "2026-10-11-x:asset-watermark": "https://drive.google.com/drive/folders/1EXAMPLE"})


if __name__ == "__main__":
    unittest.main()
