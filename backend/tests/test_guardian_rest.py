import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ["AIMONITOR_NO_BLOCKER_SINGLETON"] = "1"

from guardian_manager import GuardianManager


class GuardianRestQuotaTests(unittest.TestCase):
    def test_start_break_consumes_one_token_then_blocks_the_fourth(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "guardian_state.json"
            manager = GuardianManager()
            with patch("guardian_manager.GUARDIAN_STATE_FILE", state_file), patch(
                "guardian_manager.get_guardian_rest_quota_per_day", return_value=3
            ), patch("guardian_manager.blocker.dismiss"), patch.object(
                manager, "_is_session_active", return_value=False
            ):
                manager.pending_break = None
                for _ in range(3):
                    manager.pending_break = None
                    payload = manager.start_break(10, "回到工作")
                    self.assertEqual(payload["rest_quota"], 3)
                manager.pending_break = None
                with self.assertRaisesRegex(ValueError, "已用完"):
                    manager.start_break(10, "回到工作")
                self.assertEqual(manager._rest_status()["used_count"], 3)
                self.assertEqual(manager._rest_status()["remaining"], 0)

    def test_start_break_pauses_active_session(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "guardian_state.json"
            manager = GuardianManager()
            fake_session = type("Session", (), {"active": True, "paused_for_rest": False})()

            def pause_for_rest():
                fake_session.paused_for_rest = True
                return True

            fake_session.pause_for_rest = pause_for_rest

            with patch("guardian_manager.GUARDIAN_STATE_FILE", state_file), patch(
                "guardian_manager.get_guardian_rest_quota_per_day", return_value=3
            ), patch("guardian_manager.blocker.dismiss"), patch(
                "session_manager.session_manager", fake_session
            ), patch.object(manager, "_is_session_active", return_value=True):
                payload = manager.start_break(10, "回到工作")

            self.assertEqual(payload["activity"], "休息")
            self.assertTrue(fake_session.paused_for_rest)


class GuardianTimerWarningTests(unittest.IsolatedAsyncioTestCase):
    async def test_entertainment_warns_five_minutes_before_end(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "guardian_state.json"
            manager = GuardianManager()
            sleeps = []

            async def fake_sleep(seconds):
                sleeps.append(seconds)

            with patch("guardian_manager.GUARDIAN_STATE_FILE", state_file), patch(
                "guardian_manager.get_guardian_entertainment_daily_limit_minutes", return_value=60
            ), patch.object(manager, "_is_session_active", return_value=False), patch(
                "guardian_manager.blocker"
            ) as guardian_blocker, patch("blocker_window.blocker") as warning_blocker, patch(
                "time_warning.asyncio.sleep", side_effect=fake_sleep
            ):
                guardian_blocker.is_showing = False
                manager.start_entertainment(12)
                await manager._entertainment_task

        self.assertGreaterEqual(sleeps[0], 6 * 60)
        warning_blocker.show_message.assert_called_once()
        guardian_blocker.show_break_end_translation.assert_called_once()
