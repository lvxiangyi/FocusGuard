import unittest

from dotenv import dotenv_values

from data_paths import PROJECT_ROOT


EXPECTED_KEYS = (
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "MINIMAX_API_KEY",
)


class EnvExampleTests(unittest.TestCase):
    def test_template_is_parse_safe_and_empty(self):
        path = PROJECT_ROOT / ".env.example"
        raw = path.read_bytes()
        self.assertTrue(path.is_file())
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))
        path.read_text(encoding="ascii")

        for line in raw.decode("ascii").splitlines():
            if not line or line.startswith("#"):
                continue
            self.assertRegex(line, r"^[A-Z][A-Z0-9_]+=$")

        values = dotenv_values(path)
        for key in EXPECTED_KEYS:
            self.assertIn(key, values)
            self.assertFalse((values[key] or "").strip())
