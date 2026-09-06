from __future__ import annotations

import ctypes
import sys
import tempfile
from ctypes import wintypes
from datetime import datetime
from pathlib import Path


def foreground_window_title() -> str:
    if sys.platform != "win32":
        return ""
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        ctypes.windll.user32.GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value.strip()
    except Exception:
        return ""


def capture_to_temp_jpg() -> tuple[Path, dict]:
    """Capture the monitor under the cursor and return image plus capture metadata."""
    title = foreground_window_title()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = Path(tempfile.gettempdir()) / f"focusguard_bench_{stamp}.jpg"

    repo_root = Path(__file__).resolve().parents[3]
    app_backend = repo_root / "AIMonitor" / "backend"
    try:
        if app_backend.is_dir() and str(app_backend) not in sys.path:
            sys.path.insert(0, str(app_backend))
        from screenshot import take_screenshot

        take_screenshot(output_path=str(path))
        if path.is_file():
            return path, {"window_title": title, "capture_backend": "aimonitor"}
    except Exception as error:
        print(f"[capture] AIMonitor screenshot unavailable: {error}")

    try:
        import mss
        from PIL import Image
    except ImportError as error:
        raise RuntimeError("Screenshot capture requires AIMonitor or mss + pillow") from error

    with mss.mss() as screen:
        monitor = screen.monitors[1]
        try:
            point = wintypes.POINT()
            ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
            monitor = next(
                candidate
                for candidate in screen.monitors[1:]
                if candidate["left"] <= point.x < candidate["left"] + candidate["width"]
                and candidate["top"] <= point.y < candidate["top"] + candidate["height"]
            )
        except Exception:
            pass
        shot = screen.grab(monitor)
        image = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        image.save(path, "JPEG", quality=88)
    return path, {"window_title": title, "capture_backend": "mss"}

