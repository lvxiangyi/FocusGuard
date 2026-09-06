import unittest

from PIL import Image, ImageDraw

from screenshot import (
    CHANGE_RATIO_THRESHOLD,
    changed_pixel_ratio,
    compare_thumbnail,
    reused_judgement,
    should_reuse_previous,
)


def _desk(color=(32, 36, 48)) -> Image.Image:
    return Image.new("RGB", (320, 180), color)


class ScreenshotReuseTests(unittest.TestCase):
    def test_identical_screens_have_zero_change(self):
        a = _desk()
        b = _desk()
        self.assertEqual(changed_pixel_ratio(a, b), 0.0)

    def test_clock_sized_corner_is_below_threshold(self):
        previous = _desk()
        current = previous.copy()
        draw = ImageDraw.Draw(current)
        draw.rectangle((292, 164, 318, 178), fill=(220, 220, 220))
        ratio = changed_pixel_ratio(previous, current)
        self.assertLess(ratio, CHANGE_RATIO_THRESHOLD)
        self.assertTrue(
            should_reuse_previous(
                compare_thumbnail(previous),
                compare_thumbnail(current),
                {"on_task": True, "judgement_status": "ok"},
            )
        )

    def test_cursor_sized_dot_is_below_threshold(self):
        previous = _desk()
        current = previous.copy()
        draw = ImageDraw.Draw(current)
        draw.rectangle((160, 90, 164, 96), fill=(255, 255, 255))
        self.assertLess(changed_pixel_ratio(previous, current), CHANGE_RATIO_THRESHOLD)

    def test_half_screen_change_is_above_threshold(self):
        previous = _desk()
        current = previous.copy()
        draw = ImageDraw.Draw(current)
        draw.rectangle((0, 0, 159, 179), fill=(200, 40, 40))
        ratio = changed_pixel_ratio(previous, current)
        self.assertGreater(ratio, CHANGE_RATIO_THRESHOLD)
        self.assertFalse(
            should_reuse_previous(
                compare_thumbnail(previous),
                compare_thumbnail(current),
                {"on_task": True, "judgement_status": "ok"},
            )
        )

    def test_reuse_requires_ok_previous_result(self):
        thumb = compare_thumbnail(_desk())
        self.assertFalse(should_reuse_previous(thumb, thumb, None))
        self.assertFalse(should_reuse_previous(thumb, thumb, {"judgement_status": "api_error"}))
        self.assertTrue(should_reuse_previous(thumb, thumb, {"judgement_status": "ok"}))

    def test_reused_judgement_keeps_conclusion(self):
        previous = {
            "on_task": False,
            "should_interrupt": True,
            "current_activity": "idle desktop",
            "reason": "blank",
            "judgement_status": "ok",
        }
        reused = reused_judgement(previous)
        self.assertFalse(reused["on_task"])
        self.assertTrue(reused["should_interrupt"])
        self.assertEqual(reused["current_activity"], "idle desktop")
        self.assertEqual(reused["judgement_status"], "unchanged")
        self.assertTrue(reused["reused_previous"])
        self.assertEqual(previous["judgement_status"], "ok")
