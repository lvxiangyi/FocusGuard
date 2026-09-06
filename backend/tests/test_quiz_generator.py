import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

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
                quiz_generator, "has_api_key", return_value=False
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

    def test_grade_translation_parses_when_content_is_none(self):
        payload = json.dumps({
            "accepted": True,
            "score": 0.9,
            "feedback": "Natural enough.",
            "model_translation": "どうやってこの曲に合う伴奏スタイルを知るの？",
            "explanation": "meaning is preserved",
        })
        fake_client = MagicMock()
        fake_client.chat.completions.create.return_value.choices[0].message.content = None
        fake_client.chat.completions.create.return_value.choices[0].message.reasoning_content = payload
        fake_client.chat.completions.create.return_value.choices[0].finish_reason = "stop"

        with patch.object(quiz_generator, "has_api_key", return_value=True), patch.object(
            quiz_generator, "get_client", return_value=fake_client
        ), patch.object(quiz_generator, "get_selected_model", return_value="qwen/qwen3.7-flash"), patch.object(
            quiz_generator, "extra_body_for_model", return_value={"enable_thinking": False}
        ), patch.object(quiz_generator, "get_practice_target_language", return_value="Japanese"):
            result = quiz_generator.grade_translation_answer(
                "How do you know which accompaniment style fits this song?",
                "どうやってどんなスタイルの伴奏がこの曲に合うのを知っていますか",
                target_language="Japanese",
            )

        self.assertTrue(result["accepted"])
        self.assertEqual(result["score"], 0.9)
        self.assertEqual(result["model"], "qwen/qwen3.7-flash")

    def test_explain_translation_does_not_count_as_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            attempts_file = Path(tmp) / "attempts.jsonl"
            payload = json.dumps({
                "model_translation": "こんにちは。",
                "explanation": "hello 对应 こんにちは。",
            })
            fake_client = MagicMock()
            fake_client.chat.completions.create.return_value.choices[0].message.content = payload

            with patch.object(quiz_generator, "PRACTICE_ATTEMPTS_FILE", attempts_file), patch.object(
                quiz_generator, "has_api_key", return_value=True
            ), patch.object(quiz_generator, "get_client", return_value=fake_client), patch.object(
                quiz_generator, "get_selected_model", return_value="test-model"
            ), patch.object(quiz_generator, "extra_body_for_model", return_value=None), patch.object(
                quiz_generator, "get_practice_target_language", return_value="Japanese"
            ):
                result = quiz_generator.explain_translation(
                    "Hello.",
                    target_language="Japanese",
                    challenge={
                        "challenge_id": "skip-1",
                        "source_text": "Hello.",
                        "source_name": "practice.md",
                    },
                )
                attempts = quiz_generator.get_practice_attempts()

        self.assertFalse(result["accepted"])
        self.assertTrue(result["skipped"])
        self.assertEqual(result["model_translation"], "こんにちは。")
        self.assertIn("こんにちは", result["explanation"])
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["user_answer"], "答不出来")
        self.assertTrue(attempts[0]["skipped"])
        self.assertFalse(attempts[0]["accepted"])

    def test_explain_translation_without_model_stays_unpassed(self):
        with tempfile.TemporaryDirectory() as tmp:
            attempts_file = Path(tmp) / "attempts.jsonl"
            with patch.object(quiz_generator, "PRACTICE_ATTEMPTS_FILE", attempts_file), patch.object(
                quiz_generator, "has_api_key", return_value=False
            ):
                result = quiz_generator.explain_translation("Hello.", target_language="Japanese")

        self.assertFalse(result["accepted"])
        self.assertTrue(result["skipped"])
        self.assertEqual(result["model_translation"], "")


if __name__ == "__main__":
    unittest.main()
