import os
import unittest
from unittest.mock import patch

import llm_client


class LlmClientTests(unittest.TestCase):
    def test_deepseek_and_minimax_go_through_openrouter(self):
        self.assertEqual(
            llm_client.provider_id_for_model("qwen/qwen3.7-flash"),
            "openrouter",
        )
        self.assertEqual(
            llm_client.provider_config("qwen/qwen3.7-flash")["base_url"],
            "https://openrouter.ai/api/v1",
        )
        self.assertEqual(llm_client.provider_id_for_model("minimax/minimax-m3"), "openrouter")

    def test_minimax_disables_thinking_for_json_answers(self):
        extra = llm_client.extra_body_for_model("minimax/minimax-m3")
        self.assertEqual(extra, {"thinking": {"type": "disabled"}})

    def test_qwen_flash_disables_thinking(self):
        extra = llm_client.extra_body_for_model("qwen/qwen3.7-flash")
        self.assertFalse(extra["enable_thinking"])
        self.assertEqual(extra["reasoning"], {"enabled": False})

    def test_message_text_uses_content(self):
        response = type("Resp", (), {})()
        response.choices = [type("Choice", (), {})()]
        response.choices[0].message = type("Msg", (), {"content": ' {"ok": true} '})()
        self.assertEqual(llm_client.message_text(response), '{"ok": true}')

    def test_message_text_falls_back_when_content_is_none(self):
        response = type("Resp", (), {})()
        response.choices = [type("Choice", (), {})()]
        response.choices[0].finish_reason = "length"
        response.choices[0].message = type(
            "Msg",
            (),
            {"content": None, "reasoning_content": '{"accepted": true}'},
        )()
        self.assertEqual(llm_client.message_text(response), '{"accepted": true}')

    def test_message_text_raises_on_empty(self):
        response = type("Resp", (), {})()
        response.choices = [type("Choice", (), {})()]
        response.choices[0].finish_reason = "length"
        response.choices[0].message = type("Msg", (), {"content": None})()
        with self.assertRaisesRegex(ValueError, "empty content"):
            llm_client.message_text(response)

    def test_has_api_key_uses_openrouter_key(self):
        env = {
            "OPENROUTER_API_KEY": "sk-or-test",
            "DEEPSEEK_API_KEY": "",
            "MINIMAX_API_KEY": "",
            "OPENAI_API_KEY": "",
            "ANTHROPIC_API_KEY": "",
        }
        with patch.dict(os.environ, env, clear=False):
            self.assertTrue(llm_client.has_api_key("qwen/qwen3.7-flash"))
            self.assertTrue(llm_client.has_api_key("minimax/minimax-m3"))
            self.assertTrue(llm_client.has_api_key("anthropic/claude-sonnet-4"))
            self.assertFalse(llm_client.has_api_key("gpt-4o-mini"))
            self.assertFalse(llm_client.has_api_key("claude-sonnet-4-5"))

    def test_official_openai_and_claude_use_their_own_keys(self):
        self.assertEqual(llm_client.provider_id_for_model("gpt-4o-mini"), "openai")
        self.assertEqual(llm_client.provider_id_for_model("claude-sonnet-4-5"), "anthropic")
        env = {
            "OPENROUTER_API_KEY": "",
            "OPENAI_API_KEY": "sk-openai-test",
            "ANTHROPIC_API_KEY": "sk-ant-test",
        }
        with patch.dict(os.environ, env, clear=False):
            self.assertTrue(llm_client.has_api_key("gpt-4o-mini"))
            self.assertTrue(llm_client.has_api_key("claude-sonnet-4-5"))
            self.assertFalse(llm_client.has_api_key("qwen/qwen3.7-flash"))

    def test_claude_key_alias(self):
        env = {"ANTHROPIC_API_KEY": "", "CLAUDE_API_KEY": "sk-ant-alias"}
        with patch.dict(os.environ, env, clear=False):
            self.assertTrue(llm_client.has_api_key("claude-sonnet-4-5"))

    def test_missing_key_message_names_openrouter_env(self):
        message = llm_client.missing_key_message("qwen/qwen3.7-flash")
        self.assertIn("OPENROUTER_API_KEY", message)
        self.assertIn("OPENAI_API_KEY", llm_client.missing_key_message("gpt-4o-mini"))
        self.assertIn("ANTHROPIC_API_KEY", llm_client.missing_key_message("claude-sonnet-4-5"))
