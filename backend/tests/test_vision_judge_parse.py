import unittest

from vision_judge import classify_judge_error, extract_json_object, should_force_guardian_category_interrupt


class VisionJudgeParseTests(unittest.TestCase):
    def test_extract_plain_json(self):
        data = extract_json_object('{"should_interrupt": false, "trigger_category": "none"}')
        self.assertFalse(data["should_interrupt"])

    def test_extract_json_from_prose(self):
        text = (
            "I cannot analyze a black image.\n"
            '{"should_interrupt": false, "trigger_category": "none", "confidence": 0.1, '
            '"current_activity": "blank", "reason": "unclear"}'
        )
        data = extract_json_object(text)
        self.assertEqual(data["trigger_category"], "none")

    def test_extract_json_from_fence(self):
        text = "```json\n{\"on_task\": true, \"confidence\": 0.8, \"current_activity\": \"code\", \"reason\": \"ok\"}\n```"
        data = extract_json_object(text)
        self.assertTrue(data["on_task"])

    def test_classify_parse_vs_connection(self):
        self.assertEqual(classify_judge_error(ValueError("Expecting value: line 1 column 1")), "parse_error")
        self.assertEqual(classify_judge_error(RuntimeError("Connection error.")), "connection_error")

    def test_guardian_hard_category_yields_to_close_allow_precedent(self):
        self.assertTrue(should_force_guardian_category_interrupt("novel", []))
        self.assertTrue(should_force_guardian_category_interrupt(
            "novel",
            [{"human_label": "interrupt", "retrieval_score": 0.9}],
        ))
        self.assertFalse(should_force_guardian_category_interrupt(
            "novel",
            [{"human_label": "allow", "retrieval_score": 0.8}],
        ))
        self.assertTrue(should_force_guardian_category_interrupt(
            "novel",
            [{"human_label": "allow", "retrieval_score": 0.2}],
        ))
        self.assertFalse(should_force_guardian_category_interrupt("none", []))


if __name__ == "__main__":
    unittest.main()
