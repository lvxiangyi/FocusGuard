import unittest

from clip_pairwise import build_pair_rows, phash_matrix


class ClipPairwiseTests(unittest.TestCase):
    def test_phash_matrix_is_symmetric(self):
        samples = [
            {"id": "a", "image_hash": "00"},
            {"id": "b", "image_hash": "ff"},
            {"id": "c", "image_hash": "00"},
        ]
        matrix = phash_matrix(samples)
        self.assertEqual(matrix[0][0], 1.0)
        self.assertEqual(matrix[0][1], 0.0)
        self.assertEqual(matrix[0][2], 1.0)
        self.assertEqual(matrix[1][0], matrix[0][1])

    def test_pair_rows_rank_by_clip(self):
        samples = [
            {"id": "aaaa1111", "human_label": "ontask", "mode": "guardian", "activity": "youtube"},
            {"id": "bbbb2222", "human_label": "entertainment", "mode": "guardian", "activity": "manga"},
            {"id": "cccc3333", "human_label": "ontask", "mode": "session", "activity": "docs"},
        ]
        clip_scores = [
            [1.0, 0.9, 0.2],
            [0.9, 1.0, 0.1],
            [0.2, 0.1, 1.0],
        ]
        phash_scores = [
            [1.0, 0.3, 0.4],
            [0.3, 1.0, 0.5],
            [0.4, 0.5, 1.0],
        ]
        rows = build_pair_rows(samples, clip_scores, phash_scores)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["short_a"], "aaaa1111")
        self.assertEqual(rows[0]["short_b"], "bbbb2222")
        self.assertEqual(rows[0]["same_label"], 0)
        self.assertEqual(rows[0]["clip_cosine"], 0.9)
        self.assertEqual(rows[2]["clip_cosine"], 0.1)
