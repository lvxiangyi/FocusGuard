import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import personal_bench.capture_context as cc
import personal_bench.store as store_mod


class CaptureContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pb_cc_"))
        self.pending_dir = self.tmp / "pending"
        self.pending_dir.mkdir()
        self.patches = [
            patch.object(cc, "CAPTURE_CONTEXT_FILE", self.tmp / "capture_context.json"),
            patch.object(cc, "PENDING_DIR", self.pending_dir),
            patch.object(cc, "PENDING_IMAGE", self.pending_dir / "capture.jpg"),
            patch.object(cc, "PENDING_META", self.pending_dir / "capture.json"),
            patch.object(store_mod, "default_bench_root", lambda: self.tmp),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in self.patches:
            p.stop()

    def _write_pending(self, verdict="对"):
        Image.new("RGB", (24, 24), (10, 20, 30)).save(cc.PENDING_IMAGE, "JPEG")
        cc.PENDING_META.write_text(
            json.dumps({"verdict": verdict, "captured_at": "2026-08-25T00:00:00+08:00"}),
            encoding="utf-8",
        )

    def test_binary_labels(self):
        self.assertEqual(cc.binary_label_for_mode("guardian", "对"), "allow")
        self.assertEqual(cc.binary_label_for_mode("guardian", "错"), "interrupt")
        self.assertEqual(cc.binary_label_for_mode("session", "对"), "on_task")
        self.assertEqual(cc.binary_label_for_mode("session", "错"), "off_task")

    def test_save_session_context_allows_empty_task(self):
        ctx = cc.save_capture_context({"mode": "session", "task": "", "split": "train"})
        self.assertEqual(ctx["mode"], "session")
        self.assertEqual(ctx["task"], "")

    def test_commit_requires_pending_and_session_task(self):
        with self.assertRaises(ValueError):
            cc.commit_pending_capture("对", {"mode": "guardian"})
        self._write_pending("对")
        with self.assertRaises(ValueError):
            cc.commit_pending_capture("对", {"mode": "session", "task": "", "split": "train"})

    def test_commit_copies_image_clears_pending_and_note_defaults(self):
        self._write_pending("错")
        sample = cc.commit_pending_capture(
            "错",
            {"mode": "guardian", "activity": "weibo", "note": "scroll", "split": "train"},
        )
        self.assertEqual(sample["human_label"], "interrupt")
        self.assertIsNone(cc.load_pending_capture())
        copied = self.tmp / "train" / "screenshots" / f"{sample['id']}.jpg"
        self.assertTrue(copied.exists())
        defaults = cc.load_capture_context()
        self.assertEqual(defaults["activity"], "")
        self.assertEqual(defaults["note"], "")
        self.assertEqual(defaults["mode"], "guardian")

    def test_take_pending_keeps_previous_verdict(self):
        self._write_pending("对")

        def fake_shot(output_path=None, **_kwargs):
            Image.new("RGB", (16, 16), (1, 2, 3)).save(output_path, "JPEG")
            return output_path

        with patch("screenshot.take_screenshot", side_effect=fake_shot):
            pending = cc.take_pending_capture(None)
        self.assertEqual(pending["verdict"], "对")
        self.assertTrue(pending["replaced"])

    def test_set_pending_verdict_does_not_recapture(self):
        self._write_pending("对")
        before = cc.PENDING_IMAGE.read_bytes()
        pending = cc.set_pending_verdict("错")
        self.assertEqual(pending["verdict"], "错")
        self.assertEqual(cc.PENDING_IMAGE.read_bytes(), before)

    def test_load_pending_with_corrupt_meta_still_returns_image(self):
        Image.new("RGB", (12, 12), (4, 5, 6)).save(cc.PENDING_IMAGE, "JPEG")
        cc.PENDING_META.write_text("{not json", encoding="utf-8")
        pending = cc.load_pending_capture()
        self.assertIsNotNone(pending)
        self.assertIsNone(pending["verdict"])


if __name__ == "__main__":
    unittest.main()
