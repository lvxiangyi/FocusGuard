import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from personal_bench.schema import judge_label_for
from personal_bench.store import BenchStore, resolve_dataset_root


class DatasetRootTests(unittest.TestCase):
    def test_judge_label_maps_activity_classes(self):
        self.assertEqual(judge_label_for("guardian", "ontask"), "allow")
        self.assertEqual(judge_label_for("guardian", "process"), "allow")
        self.assertEqual(judge_label_for("guardian", "entertainment"), "interrupt")
        self.assertEqual(judge_label_for("guardian", "not_entertainment_but_notFocus"), "allow")
        self.assertEqual(judge_label_for("session", "ontask"), "on_task")
        self.assertEqual(judge_label_for("session", "process"), "on_task")
        self.assertEqual(judge_label_for("session", "entertainment"), "off_task")
        self.assertEqual(judge_label_for("session", "not_entertainment_but_notFocus"), "off_task")

    def test_resolve_accepts_parent_or_data_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            (data / "train").mkdir(parents=True)
            (data / "train" / "samples.jsonl").write_text("", encoding="utf-8")
            self.assertEqual(resolve_dataset_root(str(root)), data.resolve())
            self.assertEqual(resolve_dataset_root(str(data)), data.resolve())

    def test_store_reads_0906_activity_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            train = root / "train" / "screenshots"
            train.mkdir(parents=True)
            image = train / "s1.jpg"
            Image.new("RGB", (16, 16), (20, 20, 20)).save(image, "JPEG")
            row = {
                "id": "s1",
                "mode": "guardian",
                "human_label": "entertainment",
                "activity": "Listening to Spotify",
                "screenshot_relpath": "screenshots/s1.jpg",
            }
            (root / "train" / "samples.jsonl").write_text(
                json.dumps(row, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            store = BenchStore(root)
            sample = store.get("s1")
            self.assertEqual(sample["ai_activity"], "Listening to Spotify")
            self.assertEqual(sample["judge_label"], "interrupt")


if __name__ == "__main__":
    unittest.main()
