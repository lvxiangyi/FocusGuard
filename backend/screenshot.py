import ctypes
import os
import uuid
from ctypes import wintypes
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import mss
from PIL import Image

from data_paths import SCREENSHOT_DIR


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


def _get_cursor_position() -> Optional[Tuple[int, int]]:
    """Return the current Windows cursor position in virtual-screen coordinates."""
    try:
        point = POINT()
        if ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
            return point.x, point.y
    except Exception as e:
        print(f"[screenshot] Could not read cursor position: {e}")
    return None


def _monitor_contains_point(monitor: Dict, x: int, y: int) -> bool:
    return (
        monitor["left"] <= x < monitor["left"] + monitor["width"]
        and monitor["top"] <= y < monitor["top"] + monitor["height"]
    )


def _select_monitor(monitors: List[Dict]) -> Dict:
    mode = os.getenv("AIMONITOR_SCREENSHOT_MODE", "cursor").strip().lower()

    if mode == "full":
        print("[screenshot] Capturing full virtual screen because AIMONITOR_SCREENSHOT_MODE=full.")
        return monitors[0]

    cursor_pos = _get_cursor_position()
    if cursor_pos:
        x, y = cursor_pos
        for monitor in monitors[1:]:
            if _monitor_contains_point(monitor, x, y):
                print(
                    "[screenshot] Capturing monitor at "
                    f"left={monitor['left']} top={monitor['top']} "
                    f"width={monitor['width']} height={monitor['height']} "
                    f"for cursor=({x},{y})."
                )
                return monitor

        print(f"[screenshot] Cursor position {cursor_pos} did not match a monitor; using primary monitor.")

    return monitors[1] if len(monitors) > 1 else monitors[0]


# Ignore clock/cursor-sized changes: compare a small grayscale grid.
COMPARE_SIZE = (64, 36)
PIXEL_TOLERANCE = 16
CHANGE_RATIO_THRESHOLD = 0.04


def compare_thumbnail(image: Image.Image) -> Image.Image:
    return image.convert("L").resize(COMPARE_SIZE, Image.BILINEAR)


def changed_pixel_ratio(previous: Image.Image, current: Image.Image, pixel_tolerance: int = PIXEL_TOLERANCE) -> float:
    """Fraction of downscaled pixels that differ by more than pixel_tolerance."""
    a = compare_thumbnail(previous) if previous.mode != "L" or previous.size != COMPARE_SIZE else previous
    b = compare_thumbnail(current) if current.mode != "L" or current.size != COMPARE_SIZE else current
    if a.size != b.size:
        b = b.resize(a.size, Image.BILINEAR)
    pixels_a = a.tobytes()
    pixels_b = b.tobytes()
    if not pixels_a:
        return 1.0
    changed = 0
    for left, right in zip(pixels_a, pixels_b):
        if abs(left - right) > pixel_tolerance:
            changed += 1
    return changed / len(pixels_a)


def reused_judgement(previous: dict) -> dict:
    """Copy the last conclusion without calling the vision model."""
    result = dict(previous or {})
    result["judgement_status"] = "unchanged"
    result["reused_previous"] = True
    return result


def should_reuse_previous(
    previous_thumb: Optional[Image.Image],
    current_thumb: Optional[Image.Image],
    previous_result: Optional[dict],
    change_ratio_threshold: float = CHANGE_RATIO_THRESHOLD,
) -> bool:
    if previous_thumb is None or current_thumb is None:
        return False
    if not previous_result:
        return False
    if previous_result.get("judgement_status") == "api_error":
        return False
    ratio = changed_pixel_ratio(previous_thumb, current_thumb)
    reuse = ratio <= change_ratio_threshold
    print(
        f"[screenshot] change_ratio={ratio:.4f} "
        f"threshold={change_ratio_threshold:.4f} reuse={reuse}"
    )
    return reuse


def timestamped_screenshot_path(directory: Optional[Path] = None) -> str:
    """Unique per-check screenshot under <directory>/<yyyy-mm-dd>/<HHMMSS>-<uuid>.jpg.

    Every check must keep its own file: a shared "latest.jpg" gets overwritten
    by the next check, so historical log rows would all resolve to the newest image.
    """
    directory = Path(directory) if directory else SCREENSHOT_DIR
    now = datetime.now().astimezone()
    day_dir = directory / now.date().isoformat()
    day_dir.mkdir(parents=True, exist_ok=True)
    return str(day_dir / f"{now.strftime('%H%M%S')}-{uuid.uuid4().hex[:8]}.jpg")


def capture_screenshot(width: int = 768, output_path: Optional[str] = None) -> Tuple[str, Image.Image]:
    """Take a screenshot and return (path, comparison thumbnail)."""
    output = Path(output_path) if output_path else SCREENSHOT_DIR / "latest.jpg"
    output.parent.mkdir(parents=True, exist_ok=True)

    with mss.mss() as sct:
        monitor = _select_monitor(sct.monitors)
        raw = sct.grab(monitor)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

    ratio = width / img.width
    new_height = int(img.height * ratio)
    img = img.resize((width, new_height), Image.LANCZOS)
    thumb = compare_thumbnail(img)
    img.save(str(output), "JPEG", quality=70)
    return str(output), thumb


def take_screenshot(width: int = 768, output_path: Optional[str] = None) -> str:
    """Take a screenshot of the cursor's monitor, resize it, and return the file path."""
    path, _thumb = capture_screenshot(width=width, output_path=output_path)
    return path
