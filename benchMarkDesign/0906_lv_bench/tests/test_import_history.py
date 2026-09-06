import unittest
from collections import Counter
from pathlib import Path

from import_history import hash_similarity, scene_bucket, select_candidates


def _item(index, activity, ai_label="allow", mode="guardian", trigger=""):
    return {
        "mode": mode,
        "image": Path(f"{mode}-{ai_label}-{index}.jpg"),
        "captured_at": f"2026-09-01T{index:02d}:00:00+08:00",
        "task": "write code" if mode == "session" else "",
        "activity": activity,
        "ai_label": ai_label,
        "ai_reason": "",
        "trigger_category": trigger,
    }


class ImportHistorySelectionTests(unittest.TestCase):
    def test_hash_similarity_does_not_use_bit_count(self):
        self.assertEqual(hash_similarity("00", "00"), 1.0)
        self.assertEqual(hash_similarity("00", "ff"), 0.0)
        self.assertGreater(hash_similarity("0f", "07"), hash_similarity("0f", "00"))

    def test_scene_bucket_clusters_near_duplicates(self):
        self.assertEqual(
            scene_bucket({"activity": "Reviewing satellite imagery for disaster detection"}),
            scene_bucket({"activity": "Analyzing satellite imagery on a research page"}),
        )
        self.assertEqual(
            scene_bucket({"activity": "Using Zoom Workplace interface"}),
            scene_bucket({"activity": "Using Zoom Workplace video conferencing software"}),
        )
        self.assertNotEqual(
            scene_bucket({"activity": "Watching a YouTube video about startups"}),
            scene_bucket({"activity": "Using Zoom Workplace"}),
        )
        self.assertEqual(scene_bucket({"trigger_category": "game", "activity": "YouTube"}), "trigger:game")

    def test_select_caps_repeated_scenes_and_keeps_interrupts(self):
        items = []
        items.extend(_item(i, "Using Zoom Workplace interface") for i in range(20))
        items.extend(_item(20 + i, "The user is working in Cursor IDE") for i in range(20))
        items.extend(_item(40 + i, "Watching a YouTube video", "off_task", "session") for i in range(6))
        items.append(_item(50, "Reading a web novel", "interrupt", "guardian", "novel"))

        selected = select_candidates(
            items,
            limit=12,
            interrupt_quota=5,
            checksum_of=lambda item: str(item["image"]),
            hash_of=lambda item: "aa" * 8,
            per_bucket=3,
            min_session=3,
        )
        buckets = Counter(scene_bucket(item) for item in selected)
        self.assertEqual(len(selected), 12)
        self.assertLessEqual(buckets["zoom"], 4)
        self.assertLessEqual(buckets["ide"], 4)
        self.assertGreaterEqual(sum(1 for item in selected if item["ai_label"] in {"interrupt", "off_task"}), 4)
        self.assertGreaterEqual(sum(1 for item in selected if item["mode"] == "session"), 3)
        self.assertIn("youtube", buckets)
        self.assertIn("trigger:novel", buckets)


if __name__ == "__main__":
    unittest.main()
