import tempfile
import unittest
from pathlib import Path

from PIL import Image

from personal_bench.store import BenchStore


class BenchStoreMoveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="pb_store_"))
        self.store = BenchStore(self.tmp)
        src = self.tmp / "src.jpg"
        Image.new("RGB", (20, 20), (8, 8, 8)).save(src, "JPEG")
        self.sample = self.store.add_sample(
            mode="guardian",
            human_label="allow",
            source_image=src,
            split="train",
        )

    def test_move_keeps_index_if_copy_needed_first(self):
        moved = self.store.move_split(self.sample["id"], "test")
        self.assertEqual(moved["split"], "test")
        found = self.store.get(self.sample["id"])
        self.assertEqual(found["split"], "test")
        self.assertTrue(self.store.screenshot_path(found).exists())
        train_ids = [s["id"] for s in self.store.list_samples("train")]
        self.assertNotIn(self.sample["id"], train_ids)

    def test_rewrite_is_atomic_file(self):
        path = self.store._samples_path("train")
        self.store._rewrite("train", [{"id": "a", "split": "train"}, {"id": "b", "split": "train"}])
        text = path.read_text(encoding="utf-8")
        self.assertIn('"id": "a"', text)
        self.assertIn('"id": "b"', text)
        self.assertFalse(path.with_suffix(".jsonl.tmp").exists())


if __name__ == "__main__":
    unittest.main()
