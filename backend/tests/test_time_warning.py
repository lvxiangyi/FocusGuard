import os
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ["AIMONITOR_NO_BLOCKER_SINGLETON"] = "1"

from time_warning import remaining_seconds_until, sleep_with_five_minute_warning, warning_sleep_plan


class TimeWarningTests(unittest.IsolatedAsyncioTestCase):
    def test_plan_warns_when_more_than_five_minutes_remain(self):
        first, second, should_warn = warning_sleep_plan(20 * 60)
        self.assertEqual(first, 15 * 60)
        self.assertEqual(second, 5 * 60)
        self.assertTrue(should_warn)

    def test_plan_skips_warning_when_five_minutes_or_less(self):
        first, second, should_warn = warning_sleep_plan(5 * 60)
        self.assertEqual(first, 5 * 60)
        self.assertEqual(second, 0)
        self.assertFalse(should_warn)

    def test_remaining_seconds_until_future_end(self):
        ends_at = datetime.now() + timedelta(seconds=42)
        remaining = remaining_seconds_until(ends_at)
        self.assertGreaterEqual(remaining, 41)
        self.assertLessEqual(remaining, 42)

    async def test_sleep_shows_reminder_then_waits_until_end(self):
        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        with patch("time_warning.asyncio.sleep", side_effect=fake_sleep), patch(
            "blocker_window.blocker"
        ) as mock_blocker:
            await sleep_with_five_minute_warning(
                12 * 60,
                "休息提醒",
                "休息时间还剩 5 分钟。请慢慢收尾，准备回到工作。",
            )

        self.assertEqual(sleeps, [7 * 60, 5 * 60])
        mock_blocker.show_message.assert_called_once_with(
            "休息提醒",
            "休息时间还剩 5 分钟。请慢慢收尾，准备回到工作。",
        )

    async def test_sleep_skips_reminder_for_short_timers(self):
        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        with patch("time_warning.asyncio.sleep", side_effect=fake_sleep), patch(
            "blocker_window.blocker"
        ) as mock_blocker:
            await sleep_with_five_minute_warning(
                3 * 60,
                "娱乐提醒",
                "娱乐时间还剩 5 分钟。请慢慢收尾，准备回到工作。",
            )

        self.assertEqual(sleeps, [3 * 60])
        mock_blocker.show_message.assert_not_called()
