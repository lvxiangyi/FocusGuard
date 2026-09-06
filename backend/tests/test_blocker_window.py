import os
import unittest

os.environ["AIMONITOR_NO_BLOCKER_SINGLETON"] = "1"

from blocker_window import _centered_rect, _clamp_review_page, _content_position, _unlock_content_width


class BlockerWindowGeometryTests(unittest.TestCase):
    def test_centered_rect_handles_negative_monitor_coordinates(self):
        monitor = (-341, -1440, 3440, 1440)

        rect = _centered_rect(monitor, 520, 260)

        self.assertEqual(rect, (1119, -850, 520, 260))

    def test_content_position_centers_on_cursor_monitor_inside_virtual_overlay(self):
        virtual = (-341, -1440, 6341, 3040)
        monitor = (-341, -1440, 3440, 1440)

        x, y = _content_position(virtual, monitor)

        self.assertEqual((x, y), (1720, 720))

    def test_unlock_content_width_stays_inside_small_dialog(self):
        width = _unlock_content_width(760, 2560)
        self.assertLess(width, 760)
        self.assertGreaterEqual(width, 360)

    def test_unlock_content_width_uses_monitor_when_fullscreen(self):
        width = _unlock_content_width(2560, 2560)
        self.assertGreater(width, 1000)
        self.assertLess(width, 2560)

    def test_review_page_clamps_at_ends(self):
        self.assertEqual(_clamp_review_page(0, 3, -1), 0)
        self.assertEqual(_clamp_review_page(0, 3, 1), 1)
        self.assertEqual(_clamp_review_page(2, 3, 1), 2)
        self.assertEqual(_clamp_review_page(1, 0, 1), 0)
