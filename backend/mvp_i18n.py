"""Shared six-language UI resources, bundled beside this module in releases."""
import json
from pathlib import Path

STRINGS = json.loads(Path(__file__).with_name("ui_strings.json").read_text(encoding="utf-8"))
LANGUAGES = dict(zip(STRINGS["LANGS"], ["Chinese", "English", "Japanese", "Korean", "French", "Portuguese"]))


def text(key, language=None):
    if language is None:
        from settings_manager import load_settings
        language = load_settings().get("ui_language", "en")
    index = list(LANGUAGES).index(language) if language in LANGUAGES else list(LANGUAGES).index("en")
    return STRINGS["copy"].get(key, [key] * 6)[index]
