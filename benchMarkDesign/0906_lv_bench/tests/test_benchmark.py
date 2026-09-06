import tempfile
import unittest
from pathlib import Path

from PIL import Image

from benchmark.context import ContextStore
from benchmark.schema import coerce_human_label, normalize_label, should_interrupt
from benchmark.store import BenchmarkStore


class BenchmarkStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = BenchmarkStore(self.root / "data")
        self.image = self.root / "source.jpg"
        Image.new("RGB", (40, 30), (10, 30, 80)).save(self.image, "JPEG")

    def test_unified_activity_labels(self):
        self.assertEqual(normalize_label("guardian", "allow"), "ontask")
        self.assertEqual(normalize_label("guardian", "interrupt"), "entertainment")
        self.assertEqual(normalize_label("session", "on_task"), "ontask")
        self.assertEqual(normalize_label("session", "off_task"), "entertainment")
        self.assertEqual(normalize_label("session", "process"), "process")
        with self.assertRaises(ValueError):
            normalize_label("guardian", "on_task_typo")

    def test_interrupt_rules(self):
        self.assertFalse(should_interrupt("guardian", "ontask"))
        self.assertFalse(should_interrupt("guardian", "process"))
        self.assertFalse(should_interrupt("guardian", "not_entertainment_but_notFocus"))
        self.assertTrue(should_interrupt("guardian", "entertainment"))
        self.assertFalse(should_interrupt("session", "ontask"))
        self.assertFalse(should_interrupt("session", "process"))
        self.assertTrue(should_interrupt("session", "entertainment"))
        self.assertTrue(should_interrupt("session", "not_entertainment_but_notFocus"))

    def test_add_lists_full_context_and_copies_image(self):
        sample = self.store.add_sample(
            source_image=self.image,
            mode="session",
            human_label="ontask",
            task="watch tutorial",
            activity="YouTube course",
            human_reason="related to task",
            window_title="Tutorial - YouTube",
            prompt_version="p1",
            retriever_version="r1",
        )
        loaded = self.store.get(sample["id"])
        self.assertEqual(loaded["window_title"], "Tutorial - YouTube")
        self.assertEqual(loaded["prompt_version"], "p1")
        self.assertEqual(loaded["human_label"], "ontask")
        self.assertEqual(loaded["supervision_level"], "ontask")
        self.assertFalse(loaded["should_interrupt"])
        self.assertTrue(self.store.screenshot_path(loaded).is_file())

    def test_train_test_move_and_delete(self):
        sample = self.store.add_sample(
            source_image=self.image,
            mode="guardian",
            human_label="ontask",
        )
        moved = self.store.move(sample["id"], "test")
        self.assertEqual(moved["split"], "test")
        self.assertEqual(self.store.list_samples("train"), [])
        self.assertTrue(self.store.delete(sample["id"]))
        self.assertEqual(self.store.list_samples(), [])

    def test_update_human_context_and_provenance(self):
        sample = self.store.add_sample(
            source_image=self.image,
            mode="guardian",
            human_label="ambiguous",
            split="test",
            source_type="history_import",
            review_status="pending",
        )
        updated = self.store.update(sample["id"], {
            "human_label": "process",
            "human_reason": "This is a course, not entertainment",
            "source_type": "ai_correction",
            "review_status": "reviewed",
        })
        self.assertEqual(updated["human_label"], "process")
        self.assertEqual(updated["supervision_level"], "process")
        self.assertEqual(updated["source_type"], "ai_correction")
        self.assertEqual(updated["review_status"], "reviewed")
        self.assertTrue(updated["updated_at"])

    def test_human_label_defaults_to_mapped_ai_label(self):
        self.assertEqual(coerce_human_label("guardian", "allow", ""), "ontask")
        self.assertEqual(coerce_human_label("session", "off_task", ""), "entertainment")
        sample = self.store.add_sample(
            source_image=self.image,
            mode="guardian",
            human_label="",
            ai_label="interrupt",
        )
        self.assertEqual(sample["human_label"], "entertainment")
        self.assertEqual(sample["ai_label"], "entertainment")
        self.assertTrue(sample["should_interrupt"])

    def test_context_is_persisted(self):
        contexts = ContextStore(self.root / "context.json")
        contexts.save({"mode": "session", "task": "write code", "split": "test"})
        self.assertEqual(contexts.load()["task"], "write code")
        self.assertEqual(contexts.load()["split"], "test")


if __name__ == "__main__":
    unittest.main()
