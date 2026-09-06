"""Widget smoke checks use a withdrawn root: no screen capture or model calls."""
import os
os.environ["AIMONITOR_NO_BLOCKER_SINGLETON"] = "1"

import queue
import subprocess
import sys
import tkinter as tk
import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from PIL import Image
from mvp_blocker import MvpBlockerView
from mvp_i18n import LANGUAGES


class NativeWidgetTests(unittest.TestCase):
    def test_all_languages_render_question_review_and_feedback_on_same_root(self):
        # A destroyed Tcl interpreter must not later be GC'd by TestClient's
        # worker threads. Keep all Tk creation, rendering and teardown isolated.
        if os.environ.get("FOCUSGUARD_WIDGET_CHILD") != "1":
            result = subprocess.run(
                [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", "test_mvp_desktop.py"],
                env={**os.environ, "FOCUSGUARD_WIDGET_CHILD": "1"},
                capture_output=True, text=True, timeout=30,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return
        try:
            root = tk.Tk()
        except tk.TclError as e:
            self.skipTest(str(e))
        root.withdraw()
        try:
            for language in LANGUAGES:
                frame = tk.Frame(root)
                frame.pack()
                host = SimpleNamespace(_root=root, _content_frame=frame, is_showing=True, _command_queue=queue.Queue())
                with patch("mvp_blocker.load_settings", return_value={"ui_language": language}), patch.object(MvpBlockerView, "run"):
                    view = MvpBlockerView(host, "http://unused", "Task", "Activity", "Reason", (0, 0, 960, 680))
                    host._mvp_view = view
                    challenge = {"challenge_id": "one", "block_key": ["session", "block"], "source_text": "A clear plan makes deep work easier.", "target_language": LANGUAGES[language]}
                    view.render(challenge)
                    view.answer.insert("1.0", "a translation")
                    view.review({"accepted": True, "model_translation": "reference", "explanation": "explanation"}, False)
                    view.review({"accepted": False, "model_translation": "reference", "explanation": "explanation"}, True)
                    image = BytesIO()
                    Image.new("RGB", (300, 200)).save(image, "PNG")
                    view.render_correction(({"id": "record"}, image.getvalue()))
                    root.update_idletasks()
                    self.assertTrue(view.right.winfo_exists())
                    self.assertIs(view.host._root, root)
                frame.destroy()
        finally:
            root.destroy()
