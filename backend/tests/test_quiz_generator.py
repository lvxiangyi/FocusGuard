import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import quiz_generator
import settings_manager


class PracticeQuestionTests(unittest.TestCase):
    def test_translation_challenges_follow_selected_file_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            settings_file = tmp_path / "settings.json"
            state_file = tmp_path / "practice_state.json"
            practice_file = tmp_path / "practice.md"
            practice_file.write_text(
                "1. First sentence.\n2. Second sentence.\n",
                encoding="utf-8",
            )

            with patch.object(settings_manager, "SETTINGS_FILE", settings_file), patch.object(
                quiz_generator, "PRACTICE_STATE_FILE", state_file
            ):
                settings_manager.save_settings({
                    "practice_source_path": str(practice_file),
                    "practice_target_language": "Chinese",
                })
                first = quiz_generator.generate_translation_challenge()
                second = quiz_generator.generate_translation_challenge()
                third = quiz_generator.generate_translation_challenge()

        self.assertEqual(first["source_text"], "First sentence.")
        self.assertEqual(second["source_text"], "Second sentence.")
        self.assertEqual(third["source_text"], "First sentence.")
        self.assertEqual(first["target_language"], "Chinese")

    def test_translation_attempts_are_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            attempts_file = Path(tmp) / "attempts.jsonl"
            with patch.object(quiz_generator, "PRACTICE_ATTEMPTS_FILE", attempts_file), patch.object(
                quiz_generator, "OPENROUTER_API_KEY", ""
            ):
                result = quiz_generator.grade_translation_answer(
                    "Hello world.",
                    "你好啊",
                    target_language="Chinese",
                    challenge={
                        "challenge_id": "abc",
                        "source_text": "Hello world.",
                        "source_name": "practice.md",
                        "item_index": 0,
                        "item_total": 2,
                        "target_language": "Chinese",
                    },
                )
                attempts = quiz_generator.get_practice_attempts()

        self.assertTrue(result["accepted"])
        self.assertIn("explanation", result)
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["challenge_id"], "abc")
        self.assertEqual(attempts[0]["user_answer"], "你好啊")
        self.assertEqual(attempts[0]["target_language"], "Chinese")


if __name__ == "__main__":
    unittest.main()
