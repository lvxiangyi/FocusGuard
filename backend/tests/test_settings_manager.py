import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import settings_manager


class SettingsManagerTests(unittest.TestCase):
    def test_default_supervision_level_is_not_entertainment(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "settings.json"
            with patch.object(settings_manager, "SETTINGS_FILE", settings_file):
                settings = settings_manager.load_settings()

        self.assertEqual(settings["supervision_level"], "not_entertainment")
        self.assertEqual(settings["model"], "qwen/qwen3.7-flash")

    def test_saved_supervision_level_overrides_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "settings.json"
            settings_file.write_text(
                json.dumps({"supervision_level": "task_related"}),
                encoding="utf-8",
            )
            with patch.object(settings_manager, "SETTINGS_FILE", settings_file):
                settings = settings_manager.load_settings()

        self.assertEqual(settings["supervision_level"], "task_related")

    def test_save_settings_persists_supervision_level_locally(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "settings.json"
            with patch.object(settings_manager, "SETTINGS_FILE", settings_file):
                saved = settings_manager.save_settings({"supervision_level": "not_entertainment"})
                reloaded = json.loads(settings_file.read_text(encoding="utf-8"))

        self.assertEqual(saved["supervision_level"], "not_entertainment")
        self.assertEqual(reloaded["supervision_level"], "not_entertainment")

    def test_guardian_entertainment_settings_persist_locally(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "settings.json"
            with patch.object(settings_manager, "SETTINGS_FILE", settings_file):
                saved = settings_manager.save_settings({
                    "guardian_entertainment_daily_limit_minutes": 90,
                    "guardian_entertainment_day_start_time": "05:30",
                })
                reloaded = json.loads(settings_file.read_text(encoding="utf-8"))

        self.assertEqual(saved["guardian_entertainment_daily_limit_minutes"], 90)
        self.assertEqual(saved["guardian_entertainment_day_start_time"], "05:30")
        self.assertEqual(reloaded["guardian_entertainment_daily_limit_minutes"], 90)
        self.assertEqual(reloaded["guardian_entertainment_day_start_time"], "05:30")

    def test_post_block_cooldown_persists_locally(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "settings.json"
            with patch.object(settings_manager, "SETTINGS_FILE", settings_file):
                saved = settings_manager.save_settings({"post_block_cooldown_seconds": 120})
                reloaded = json.loads(settings_file.read_text(encoding="utf-8"))

        self.assertEqual(saved["post_block_cooldown_seconds"], 120)
        self.assertEqual(reloaded["post_block_cooldown_seconds"], 120)

    def test_rest_quota_change_takes_effect_next_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "settings.json"
            with patch.object(settings_manager, "SETTINGS_FILE", settings_file):
                with patch.object(settings_manager, "guardian_logical_day_key", return_value="2026-08-26"):
                    with patch.object(settings_manager, "next_guardian_logical_day_key", return_value="2026-08-27"):
                        saved = settings_manager.save_settings({"guardian_rest_quota_per_day": 5})
                self.assertEqual(saved["guardian_rest_quota_per_day"], 3)
                self.assertEqual(saved["guardian_rest_quota_pending"], 5)
                self.assertEqual(saved["guardian_rest_quota_pending_day"], "2026-08-27")

                with patch.object(settings_manager, "guardian_logical_day_key", return_value="2026-08-27"):
                    loaded = settings_manager.load_settings()
                self.assertEqual(loaded["guardian_rest_quota_per_day"], 5)
                self.assertIsNone(loaded["guardian_rest_quota_pending"])
                self.assertIsNone(loaded["guardian_rest_quota_pending_day"])

    def test_invalid_guardian_entertainment_day_start_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_file = Path(tmp) / "settings.json"
            with patch.object(settings_manager, "SETTINGS_FILE", settings_file):
                with self.assertRaises(ValueError):
                    settings_manager.save_settings({"guardian_entertainment_day_start_time": "25:00"})


if __name__ == "__main__":
    unittest.main()
