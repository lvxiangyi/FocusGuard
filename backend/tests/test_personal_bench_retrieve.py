import unittest

from personal_bench.image_hash import hash_similarity
from personal_bench.retrieve import retrieve_similar, score_pair


class _FakeStore:
    def __init__(self, samples):
        self._samples = samples

    def list_samples(self, split=None):
        if split:
            return [s for s in self._samples if s.get("split", "train") == split]
        return list(self._samples)


class RetrieveTests(unittest.TestCase):
    def test_empty_query_text_ranks_by_image_hash(self):
        store = _FakeStore(
            [
                {
                    "id": "far",
                    "mode": "guardian",
                    "task": "",
                    "ai_activity": "weibo",
                    "human_reason": "scroll",
                    "ai_reason": "",
                    "image_hash": "0000",
                    "human_label": "interrupt",
                    "split": "train",
                },
                {
                    "id": "near",
                    "mode": "guardian",
                    "task": "",
                    "ai_activity": "docs",
                    "human_reason": "work",
                    "ai_reason": "",
                    "image_hash": "ffff",
                    "human_label": "allow",
                    "split": "train",
                },
            ]
        )
        hits = retrieve_similar(store, mode="guardian", image_hash="fffe", k=2)
        self.assertEqual(hits[0]["id"], "near")
        self.assertGreater(hits[0]["retrieval_score"], 0.8)

    def test_never_searches_test_split(self):
        store = _FakeStore(
            [
                {
                    "id": "train-hit",
                    "mode": "guardian",
                    "task": "",
                    "ai_activity": "",
                    "image_hash": "aaaa",
                    "human_label": "allow",
                    "split": "train",
                },
                {
                    "id": "test-hit",
                    "mode": "guardian",
                    "task": "",
                    "ai_activity": "",
                    "image_hash": "aaaa",
                    "human_label": "allow",
                    "split": "test",
                },
            ]
        )
        hits = retrieve_similar(store, mode="guardian", image_hash="aaaa", k=3)
        self.assertEqual([h["id"] for h in hits], ["train-hit"])

    def test_session_prefers_same_task(self):
        store = _FakeStore(
            [
                {
                    "id": "other",
                    "mode": "session",
                    "task": "read paper",
                    "ai_activity": "pdf",
                    "image_hash": "ffff",
                    "human_label": "on_task",
                    "split": "train",
                },
                {
                    "id": "same",
                    "mode": "session",
                    "task": "write report",
                    "ai_activity": "docs",
                    "image_hash": "0000",
                    "human_label": "on_task",
                    "split": "train",
                },
            ]
        )
        hits = retrieve_similar(
            store,
            mode="session",
            task="write report",
            image_hash="ffff",
            k=1,
        )
        self.assertEqual(hits[0]["id"], "same")
        self.assertEqual(hits[0]["retrieval_bucket"], "same_task")

    def test_session_keeps_best_same_task_even_if_image_is_weak(self):
        store = _FakeStore(
            [
                {
                    "id": "desktop",
                    "mode": "session",
                    "task": "study interview",
                    "ai_activity": "Desktop background with icons",
                    "human_reason": "blank or desktop can be between tasks",
                    "image_hash": "0000",
                    "human_label": "on_task",
                    "split": "train",
                },
            ]
        )
        hits = retrieve_similar(
            store,
            mode="session",
            task="study interview",
            image_hash="ffff",
            k=3,
        )
        self.assertEqual([h["id"] for h in hits], ["desktop"])

    def test_hash_similarity_bounds(self):
        self.assertEqual(hash_similarity("ffff", "ffff"), 1.0)
        self.assertEqual(hash_similarity("", "ffff"), 0.0)
        self.assertGreater(score_pair({"image_hash": "ffff"}, {"image_hash": "fffe"}), 0.3)

    def test_empty_texts_are_not_perfect_matches(self):
        from personal_bench.retrieve import text_similarity
        self.assertEqual(text_similarity("", ""), 0.0)

    def test_skips_weak_image_matches(self):
        store = _FakeStore(
            [
                {
                    "id": "unrelated",
                    "mode": "guardian",
                    "task": "",
                    "ai_activity": "weibo",
                    "image_hash": "0000",
                    "human_label": "interrupt",
                    "split": "train",
                },
            ]
        )
        hits = retrieve_similar(store, mode="guardian", image_hash="ffff", k=3)
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
