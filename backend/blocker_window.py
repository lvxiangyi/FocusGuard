"""
System-level fullscreen blocker window using tkinter.
Uses a persistent tkinter thread to avoid Tcl_AsyncDelete crashes.
The window is hidden/shown rather than created/destroyed.
"""

import tkinter as tk
from tkinter import ttk
import threading
import requests
import os
import queue
import ctypes
from ctypes import wintypes

BACKEND_URL = "http://127.0.0.1:" + os.environ.get("FOCUSGUARD_PORT", "8899")
UI_SCALE = 2.0
TRANSLATION_REQUIRED_COUNT = 3

SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79
MONITOR_DEFAULTTONEAREST = 2
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", wintypes.LONG),
        ("top", wintypes.LONG),
        ("right", wintypes.LONG),
        ("bottom", wintypes.LONG),
    ]


class MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", RECT),
        ("rcWork", RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def _enable_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _rect_tuple(rect: RECT):
    return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)


def _virtual_screen_rect():
    try:
        user32 = ctypes.windll.user32
        return (
            user32.GetSystemMetrics(SM_XVIRTUALSCREEN),
            user32.GetSystemMetrics(SM_YVIRTUALSCREEN),
            user32.GetSystemMetrics(SM_CXVIRTUALSCREEN),
            user32.GetSystemMetrics(SM_CYVIRTUALSCREEN),
        )
    except Exception:
        return (0, 0, 0, 0)


def _cursor_monitor_rect():
    try:
        user32 = ctypes.windll.user32
        point = POINT()
        if not user32.GetCursorPos(ctypes.byref(point)):
            raise RuntimeError("GetCursorPos failed")
        monitor = user32.MonitorFromPoint(point, MONITOR_DEFAULTTONEAREST)
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            raise RuntimeError("GetMonitorInfoW failed")
        return _rect_tuple(info.rcMonitor)
    except Exception:
        virtual = _virtual_screen_rect()
        if virtual[2] > 0 and virtual[3] > 0:
            return virtual
        return (0, 0, 1024, 768)


def _centered_rect(container, width, height):
    left, top, container_width, container_height = container
    return (
        left + max(0, int((container_width - width) / 2)),
        top + max(0, int((container_height - height) / 2)),
        width,
        height,
    )


def _content_position(window_rect, monitor_rect):
    window_left, window_top, _, _ = window_rect
    monitor_left, monitor_top, monitor_width, monitor_height = monitor_rect
    return (
        monitor_left - window_left + int(monitor_width / 2),
        monitor_top - window_top + int(monitor_height / 2),
    )


def _s(value):
    return int(round(value * UI_SCALE))


def _clamp_dialog_size(monitor_rect, width, height, max_fraction=0.92):
    _, _, monitor_width, monitor_height = monitor_rect
    max_width = int(monitor_width * max_fraction)
    max_height = int(monitor_height * max_fraction)
    return min(width, max_width), min(height, max_height)


def _unlock_content_width(window_width, monitor_width):
    """Keep review/quiz text inside the current window, not the full monitor."""
    window_width = max(int(window_width or 0), 1)
    monitor_width = max(int(monitor_width or 0), 1)
    usable = window_width if window_width < monitor_width * 0.95 else monitor_width
    return max(360, min(int(usable * 0.86), usable - 48))


def _clamp_review_page(index, total, delta=0):
    """Keep the review pager on a valid card."""
    if int(total or 0) <= 0:
        return 0
    return max(0, min(int(total) - 1, int(index or 0) + int(delta)))


def _raise_window(root):
    try:
        hwnd = wintypes.HWND(root.winfo_id())
        ctypes.windll.user32.FlashWindow(hwnd, True)
        ctypes.windll.user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def _keyboard_layout_label():
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        thread_id = user32.GetWindowThreadProcessId(hwnd, None) if hwnd else 0
        hkl = user32.GetKeyboardLayout(thread_id)
        lang_id = hkl & 0xFFFF
    except Exception:
        return "Input language: unknown"

    names = {
        0x0409: "English - US",
        0x0809: "English - UK",
        0x0411: "Japanese",
        0x0804: "Chinese - Simplified",
        0x0404: "Chinese - Traditional",
        0x0412: "Korean",
    }
    return f"Input language: {names.get(lang_id, 'Unknown')} (0x{lang_id:04X})"


def _force_window_rect(root, rect, activate=True):
    left, top, width, height = rect
    root.geometry(f"{width}x{height}+{left}+{top}")
    try:
        hwnd = wintypes.HWND(root.winfo_id())
        flags = SWP_NOZORDER
        if not activate:
            flags |= SWP_NOACTIVATE
        ctypes.windll.user32.SetWindowPos(hwnd, None, left, top, width, height, flags)
    except Exception:
        pass


class BlockerWindow:
    """Persistent tkinter-based fullscreen blocker with quiz."""

    def __init__(self):
        self._is_showing = False
        self._task = ""
        self._root = None
        self._content_frame = None
        self._result_label = None
        self._command_queue = queue.Queue()
        self._unlock_reviews = []
        self._review_wheel_bound = False
        self._review_key_bound = False
        self._review_page = 0
        self._swipe_origin = None
        # Start persistent tkinter thread
        self._thread = threading.Thread(target=self._tk_thread, daemon=True)
        self._thread.start()

    def _tk_thread(self):
        """Persistent tkinter thread. Window lives here forever."""
        _enable_dpi_awareness()
        self._root = tk.Tk()
        self._root.withdraw()  # Start hidden
        self._root.configure(bg="#0f0f23")
        self._root.overrideredirect(True)
        try:
            self._root.tk.call("tk", "scaling", 1.0)
        except Exception:
            pass

        # Force fullscreen covering the whole virtual desktop, including secondary monitors.
        rect = _virtual_screen_rect()
        if rect[2] <= 0 or rect[3] <= 0:
            rect = (0, 0, self._root.winfo_screenwidth(), self._root.winfo_screenheight())
        _force_window_rect(self._root, rect)
        self._root.attributes("-topmost", True)

        self._content_frame = tk.Frame(self._root, bg="#0f0f23")
        x, y = _content_position(rect, _cursor_monitor_rect())
        self._content_frame.place_forget()
        self._content_frame.place(x=x, y=y, anchor="center")

        # Process commands from queue periodically
        self._process_queue()
        self._root.mainloop()

    def _process_queue(self):
        """Check command queue every 100ms."""
        try:
            while not self._command_queue.empty():
                cmd = self._command_queue.get_nowait()
                cmd()
        except Exception as e:
            print(f"[blocker] UI command error: {e}")
        if self._root:
            self._root.after(100, self._process_queue)

    def show(
        self,
        task: str,
        activity: str,
        reason: str,
        strict_mode: bool = False,
        nudge_message: str = "",
        recovery: bool = True,
        recovery_mode: str = "session",
        translation_count: int = 1,
    ):
        """Show the blocker window with a quiz."""
        if self._is_showing:
            return
        self._is_showing = True
        self._task = task
        # Queue the show command to run on tkinter thread
        self._command_queue.put(
            lambda: self._do_show(
                task,
                activity,
                reason,
                strict_mode,
                nudge_message,
                recovery,
                recovery_mode,
                translation_count,
            )
        )

    def show_message(self, title: str, message: str):
        """Show a dismissible desktop message."""
        if self._is_showing:
            return
        self._is_showing = True
        self._command_queue.put(lambda: self._do_show_message(title, message))

    def show_flow_prompt(self, summary: dict):
        """Ask the user what to do after a completed work block."""
        from flow_prompt_store import save_pending_flow

        save_pending_flow(summary)
        self._is_showing = True
        self._command_queue.put(lambda: self._do_show_flow_prompt(summary))

    def show_resume_prompt(self, payload: dict):
        """Ask the user to confirm returning to work after a break."""
        self._is_showing = True
        self._command_queue.put(lambda: self._do_show_resume_prompt(payload))

    def show_break_end_translation(self, payload: dict):
        """Force a translation challenge before resuming after a strict break."""
        self._is_showing = True
        self._command_queue.put(lambda: self._do_show_break_end_translation(payload))

    def show_stop_resume_prompt(self, payload: dict):
        """Ask the user to start the next task after a stopped period."""
        self._is_showing = True
        self._command_queue.put(lambda: self._do_show_resume_prompt(payload, title="停止时间结束", endpoint="/flow/continue"))

    def dismiss(self):
        """Hide the blocker window."""
        if not self._is_showing:
            return
        self._is_showing = False
        self._command_queue.put(self._do_hide)

    @property
    def is_showing(self):
        return self._is_showing

    def _do_show(
        self,
        task,
        activity,
        reason,
        strict_mode=False,
        nudge_message="",
        recovery=True,
        recovery_mode="session",
        translation_count=1,
    ):
        """Show window and load quiz (runs on tk thread)."""
        # Force fullscreen size again in case resolution changed.
        rect = _virtual_screen_rect()
        if rect[2] <= 0 or rect[3] <= 0:
            rect = (0, 0, self._root.winfo_screenwidth(), self._root.winfo_screenheight())
        monitor_rect = _cursor_monitor_rect()
        _force_window_rect(self._root, rect)
        x, y = _content_position(rect, monitor_rect)
        self._content_frame.place_forget()
        self._content_frame.place(x=x, y=y, anchor="center")
        self._root.deiconify()
        self._root.attributes("-topmost", True)
        self._root.lift()
        self._root.focus_force()
        self._grab_modal(global_grab=not strict_mode)
        if recovery_mode == "session":
            from mvp_blocker import MvpBlockerView
            self._clear_content()
            self._mvp_view = MvpBlockerView(self, BACKEND_URL, task, activity, reason, monitor_rect)
            return
        if strict_mode:
            self._load_translation_unlock(
                task,
                activity,
                reason,
                nudge_message=nudge_message,
                recovery=recovery,
                recovery_mode=recovery_mode,
                challenge_total=translation_count,
            )
        else:
            self._load_quiz(task, activity, reason)

    def _do_show_message(self, title, message):
        """Show a small dismissible message window (runs on tk thread)."""
        self._clear_content()
        width = 520
        height = 260
        rect = _centered_rect(_cursor_monitor_rect(), width, height)
        _force_window_rect(self._root, rect)
        self._root.deiconify()
        self._root.attributes("-topmost", True)
        self._root.lift()
        self._root.focus_force()
        self._grab_modal()

        frame = self._content_frame
        frame.place_forget()
        frame.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(
            frame,
            text=title,
            font=("Segoe UI", 20, "bold"),
            fg="#ffffff",
            bg="#0f0f23",
            wraplength=460,
        ).pack(pady=(0, 14))
        tk.Label(
            frame,
            text=message,
            font=("Segoe UI", 12),
            fg="#cbd5e1",
            bg="#0f0f23",
            wraplength=460,
            justify="center",
        ).pack(pady=(0, 22))
        tk.Button(
            frame,
            text="知道了",
            font=("Segoe UI", 12, "bold"),
            fg="#ffffff",
            bg="#4a9eff",
            activebackground="#2f80ed",
            activeforeground="#ffffff",
            relief="flat",
            padx=28,
            pady=8,
            cursor="hand2",
            command=self._message_dismiss,
        ).pack()

    def _message_dismiss(self):
        self._is_showing = False
        self._do_hide()

    def _do_show_flow_prompt(self, summary):
        """Render post-block options (runs on tk thread)."""
        self._clear_content()
        monitor_rect = _cursor_monitor_rect()
        width, height = _clamp_dialog_size(monitor_rect, _s(680), _s(560))
        rect = _centered_rect(monitor_rect, width, height)
        _force_window_rect(self._root, rect)
        self._root.deiconify()
        self._root.attributes("-topmost", True)
        self._root.lift()
        self._root.focus_force()
        _raise_window(self._root)
        self._grab_modal(global_grab=False)

        frame = self._content_frame
        frame.place_forget()
        frame.place(relx=0.5, rely=0.5, anchor="center")

        task = summary.get("task", "")
        duration = int(summary.get("duration_minutes") or 30)
        interval = int(summary.get("check_interval_seconds") or 300)
        trigger_threshold = int(summary.get("trigger_threshold") or 1)
        tags = ", ".join(summary.get("tags", []))
        strict_mode = bool(summary.get("strict_mode", False))
        focus_minutes = summary.get("focus_minutes", 0)
        distracted = summary.get("distracted_checks", 0)
        api_errors = summary.get("api_error_checks", 0)

        tk.Label(
            frame,
            text="Block 已结束",
            font=("Segoe UI", _s(22), "bold"),
            fg="#ffffff",
            bg="#0f0f23",
        ).pack(pady=(0, _s(8)))
        tk.Label(
            frame,
            text=f"{task}\n专注 {focus_minutes} 分钟，分心 {distracted} 次，AI 错误 {api_errors} 次。",
            font=("Segoe UI", _s(11)),
            fg="#cbd5e1",
            bg="#0f0f23",
            wraplength=_s(600),
            justify="center",
        ).pack(pady=(0, _s(16)))

        error_label = tk.Label(
            frame, text="", font=("Segoe UI", _s(10)), fg="#ff8a80", bg="#0f0f23", wraplength=_s(560)
        )
        error_label.pack(pady=(0, _s(8)))

        continue_box = tk.Frame(frame, bg="#15172a", padx=_s(14), pady=_s(12))
        continue_box.pack(fill="x", pady=(0, _s(8)))
        tk.Label(
            continue_box, text="1. 继续任务", font=("Segoe UI", _s(12), "bold"), fg="#ffffff", bg="#15172a"
        ).pack(anchor="w")
        continue_task = tk.Entry(
            continue_box, font=("Segoe UI", _s(11)), width=_s(48), bg="#0f0f23", fg="#ffffff",
            insertbackground="#ffffff", relief="flat",
        )
        continue_task.insert(0, task)
        continue_task.pack(fill="x", pady=(_s(8), _s(8)))
        duration_row = tk.Frame(continue_box, bg="#15172a")
        duration_row.pack(fill="x")
        tk.Label(
            duration_row, text="下一轮分钟", font=("Segoe UI", _s(10)), fg="#cbd5e1", bg="#15172a"
        ).pack(side="left")
        continue_duration = tk.Entry(
            duration_row, font=("Segoe UI", _s(10)), width=_s(8), bg="#0f0f23", fg="#ffffff",
            insertbackground="#ffffff", relief="flat",
        )
        continue_duration.insert(0, str(duration))
        continue_duration.pack(side="left", padx=(_s(8), _s(12)))
        continue_tags = tk.Entry(
            continue_box, font=("Segoe UI", _s(10)), width=_s(14), bg="#0f0f23", fg="#ffffff",
            insertbackground="#ffffff", relief="flat",
        )
        continue_tags.insert(0, tags)
        continue_tags.pack(side="left", padx=(_s(0), _s(12)))
        tk.Button(
            duration_row,
            text="开始下一轮",
            font=("Segoe UI", _s(10), "bold"),
            fg="#ffffff",
            bg="#2ecc71",
            relief="flat",
            padx=_s(14),
            pady=_s(5),
            cursor="hand2",
            command=lambda: self._submit_continue(
                continue_task, continue_duration, interval, trigger_threshold, error_label, continue_tags, strict_mode
            ),
        ).pack(side="right")

        break_box = tk.Frame(frame, bg="#15172a", padx=_s(14), pady=_s(12))
        break_box.pack(fill="x", pady=(0, _s(8)))
        tk.Label(
            break_box, text="2. 休息一下", font=("Segoe UI", _s(12), "bold"), fg="#ffffff", bg="#15172a"
        ).pack(anchor="w")
        break_row = tk.Frame(break_box, bg="#15172a")
        break_row.pack(fill="x", pady=(_s(8), _s(8)))
        tk.Label(
            break_row, text="休息分钟", font=("Segoe UI", _s(10)), fg="#cbd5e1", bg="#15172a"
        ).pack(side="left")
        break_minutes = tk.Entry(
            break_row, font=("Segoe UI", _s(10)), width=_s(8), bg="#0f0f23", fg="#ffffff",
            insertbackground="#ffffff", relief="flat",
        )
        break_minutes.insert(0, "10")
        break_minutes.pack(side="left", padx=(_s(8), _s(12)))
        break_activity = tk.Entry(
            break_box, font=("Segoe UI", _s(11)), width=_s(48), bg="#0f0f23", fg="#ffffff",
            insertbackground="#ffffff", relief="flat",
        )
        break_activity.insert(0, "散步 / 喝水 / 放松")
        break_activity.pack(fill="x", pady=(0, _s(8)))
        break_tags = tk.Entry(
            break_box, font=("Segoe UI", _s(10)), width=_s(48), bg="#0f0f23", fg="#ffffff",
            insertbackground="#ffffff", relief="flat",
        )
        break_tags.insert(0, "恢复")
        break_tags.pack(fill="x", pady=(0, _s(8)))
        tk.Button(
            break_box,
            text="开始休息",
            font=("Segoe UI", _s(10), "bold"),
            fg="#ffffff",
            bg="#4a9eff",
            relief="flat",
            padx=_s(14),
            pady=_s(5),
            cursor="hand2",
            command=lambda: self._submit_break(
                break_minutes, break_activity, task, duration, interval, trigger_threshold, error_label, break_tags, strict_mode
            ),
        ).pack(anchor="e")

        pause_box = tk.Frame(frame, bg="#15172a", padx=_s(14), pady=_s(12))
        pause_box.pack(fill="x")
        tk.Label(
            pause_box, text="3. 暂停今天的学习", font=("Segoe UI", _s(12), "bold"), fg="#ffffff", bg="#15172a"
        ).pack(anchor="w")
        pause_activity = tk.Entry(
            pause_box, font=("Segoe UI", _s(11)), width=_s(48), bg="#0f0f23", fg="#ffffff",
            insertbackground="#ffffff", relief="flat",
        )
        pause_activity.insert(0, "接下来要做的活动")
        pause_activity.pack(fill="x", pady=(_s(8), _s(8)))
        tk.Button(
            pause_box,
            text="记录并暂停",
            font=("Segoe UI", _s(10), "bold"),
            fg="#ffffff",
            bg="#e74c3c",
            relief="flat",
            padx=_s(14),
            pady=_s(5),
            cursor="hand2",
            command=lambda: self._submit_pause_day(pause_activity, error_label),
        ).pack(anchor="e")

    def _do_show_resume_prompt(self, payload, title="休息结束", endpoint="/flow/resume"):
        """Render break-finished confirmation (runs on tk thread)."""
        self._clear_content()
        monitor_rect = _cursor_monitor_rect()
        width, height = _clamp_dialog_size(monitor_rect, _s(600), _s(420))
        rect = _centered_rect(monitor_rect, width, height)
        _force_window_rect(self._root, rect)
        self._root.deiconify()
        self._root.attributes("-topmost", True)
        self._root.lift()
        self._root.focus_force()
        _raise_window(self._root)
        self._grab_modal(global_grab=False)

        frame = self._content_frame
        frame.place_forget()
        frame.place(relx=0.5, rely=0.5, anchor="center")

        task = payload.get("task", "")
        activity = payload.get("activity", "")
        duration = int(payload.get("duration_minutes") or 30)
        interval = int(payload.get("check_interval_seconds") or 300)
        tags = ", ".join(payload.get("tags", []))
        error_label = tk.Label(
            frame, text="", font=("Segoe UI", _s(10)), fg="#ff8a80", bg="#0f0f23", wraplength=_s(500)
        )

        tk.Label(
            frame, text=title, font=("Segoe UI", _s(22), "bold"), fg="#ffffff", bg="#0f0f23"
        ).pack(pady=(0, _s(10)))
        tk.Label(
            frame,
            text=f"刚才：{activity}\n请输入接下来的任务和时间。",
            font=("Segoe UI", _s(12)),
            fg="#cbd5e1",
            bg="#0f0f23",
            wraplength=_s(500),
            justify="center",
        ).pack(pady=(0, _s(16)))
        error_label.pack(pady=(0, _s(8)))
        next_task = tk.Entry(
            frame, font=("Segoe UI", _s(12)), width=_s(42), bg="#15172a", fg="#ffffff",
            insertbackground="#ffffff", relief="flat",
        )
        next_task.insert(0, task)
        next_task.pack(fill="x", pady=(0, _s(10)))
        next_task.focus_set()
        next_task.selection_range(0, tk.END)
        row = tk.Frame(frame, bg="#0f0f23")
        row.pack(fill="x", pady=(0, _s(10)))
        tk.Label(row, text="分钟", font=("Segoe UI", _s(10)), fg="#cbd5e1", bg="#0f0f23").pack(side="left")
        next_duration = tk.Entry(
            row, font=("Segoe UI", _s(10)), width=_s(8), bg="#15172a", fg="#ffffff",
            insertbackground="#ffffff", relief="flat",
        )
        next_duration.insert(0, str(duration))
        next_duration.pack(side="left", padx=(_s(8), _s(14)))
        tk.Label(row, text="标签", font=("Segoe UI", _s(10)), fg="#cbd5e1", bg="#0f0f23").pack(side="left")
        next_tags = tk.Entry(
            row, font=("Segoe UI", _s(10)), width=_s(20), bg="#15172a", fg="#ffffff",
            insertbackground="#ffffff", relief="flat",
        )
        next_tags.insert(0, tags)
        next_tags.pack(side="left", padx=(_s(8), 0), fill="x", expand=True)
        tk.Button(
            frame,
            text="开始下一轮",
            font=("Segoe UI", _s(12), "bold"),
            fg="#ffffff",
            bg="#2ecc71",
            relief="flat",
            padx=_s(24),
            pady=_s(8),
            cursor="hand2",
            command=lambda: self._submit_resume(payload, next_task, next_duration, interval, next_tags, error_label, endpoint),
        ).pack()

    def _do_show_break_end_translation(self, payload):
        """Render a mandatory translation challenge before the resume prompt."""
        self._clear_content()
        monitor_rect = _cursor_monitor_rect()
        width, height = _clamp_dialog_size(monitor_rect, _s(1280), _s(920), max_fraction=0.94)
        rect = _centered_rect(monitor_rect, width, height)
        _force_window_rect(self._root, rect)
        self._root.deiconify()
        self._root.attributes("-topmost", True)
        self._root.lift()
        self._root.focus_force()
        _raise_window(self._root)
        self._grab_modal(global_grab=False)
        self._content_frame.place_forget()
        self._content_frame.place(relx=0.5, rely=0.5, anchor="center")
        guardian_mode = bool(payload.get("guardian_mode"))
        self._load_translation_unlock(
            payload.get("task", ""),
            payload.get("activity", "休息结束"),
            "休息时间已结束，请完成翻译题后回到学习。",
            nudge_message=payload.get("minimum_next_step", ""),
            recovery=guardian_mode,
            resume_payload=None if guardian_mode else payload,
            recovery_mode="guardian" if guardian_mode else "session",
            challenge_total=int(payload.get("translation_count") or 1),
        )

    def _parse_tags(self, tags_entry):
        if not tags_entry:
            return []
        return [tag.strip() for tag in tags_entry.get().replace("，", ",").split(",") if tag.strip()]

    def _submit_continue(self, task_entry, duration_entry, interval, trigger_threshold, error_label, tags_entry=None, strict_mode=False):
        task = task_entry.get().strip()
        if not task:
            error_label.config(text="请输入要继续的任务。")
            return
        try:
            duration = int(duration_entry.get().strip())
            if duration <= 0:
                raise ValueError()
        except Exception:
            error_label.config(text="下一轮分钟需要是正整数。")
            return
        self._post_flow("/flow/continue", {
            "task": task,
            "duration_minutes": duration,
            "check_interval_seconds": interval,
            "trigger_threshold": trigger_threshold,
            "tags": self._parse_tags(tags_entry),
            "strict_mode": strict_mode,
        }, error_label)

    def _submit_break(
        self,
        minutes_entry,
        activity_entry,
        task,
        duration,
        interval,
        trigger_threshold,
        error_label,
        tags_entry=None,
        strict_mode=False,
    ):
        try:
            minutes = int(minutes_entry.get().strip())
            if minutes <= 0:
                raise ValueError()
        except Exception:
            error_label.config(text="休息分钟需要是正整数。")
            return
        activity = activity_entry.get().strip()
        if not activity:
            error_label.config(text="请输入休息方式。")
            return
        self._post_flow("/flow/break", {
            "break_minutes": minutes,
            "activity": activity,
            "task": task,
            "duration_minutes": duration,
            "check_interval_seconds": interval,
            "trigger_threshold": trigger_threshold,
            "tags": self._parse_tags(tags_entry),
            "strict_mode": strict_mode,
        }, error_label)

    def _submit_resume(self, payload, task_entry, duration_entry, interval, tags_entry, error_label, endpoint):
        task = task_entry.get().strip()
        if not task:
            error_label.config(text="请输入接下来的任务。")
            return
        try:
            duration = int(duration_entry.get().strip())
            if duration <= 0:
                raise ValueError()
        except Exception:
            error_label.config(text="下一轮分钟需要是正整数。")
            return
        resume_payload = payload.copy()
        resume_payload.update({
            "task": task,
            "duration_minutes": duration,
            "check_interval_seconds": interval,
            "trigger_threshold": int(payload.get("trigger_threshold") or 1),
            "tags": self._parse_tags(tags_entry),
        })
        print(f"[blocker] Resume submit endpoint={endpoint} task={task!r} duration={duration}")
        self._post_flow(endpoint, resume_payload, error_label)

    def _submit_pause_day(self, activity_entry, error_label):
        activity = activity_entry.get().strip()
        if not activity:
            error_label.config(text="请输入接下来要做的活动。")
            return
        self._post_flow("/flow/pause-day", {"activity": activity}, error_label)

    def _post_flow(self, path, payload, error_label):
        error_label.config(text="")
        threading.Thread(target=lambda: self._do_post_flow(path, payload, error_label), daemon=True).start()

    def _do_post_flow(self, path, payload, error_label):
        try:
            res = requests.post(f"{BACKEND_URL}{path}", json=payload, timeout=10)
            if res.status_code >= 400:
                raise RuntimeError(res.text)
            from flow_prompt_store import clear_pending_flow

            clear_pending_flow()
            print(f"[blocker] Flow post ok path={path} task={payload.get('task')!r}")
            self._command_queue.put(self._message_dismiss)
        except Exception as e:
            self._command_queue.put(lambda: error_label.config(text=f"操作失败：{e}"))

    def _do_hide(self):
        """Hide window (runs on tk thread)."""
        self._release_modal()
        self._clear_content()
        self._root.withdraw()

    def _grab_modal(self, global_grab=True):
        try:
            if global_grab:
                self._root.grab_set_global()
            else:
                self._root.grab_set()
        except Exception as e:
            print(f"[blocker] Could not grab input: {e}")

    def _release_modal(self):
        try:
            self._root.grab_release()
        except Exception:
            pass

    def _unbind_review_input(self):
        if self._review_wheel_bound and self._root:
            for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>", "<Shift-MouseWheel>"):
                try:
                    self._root.unbind_all(seq)
                except Exception:
                    pass
            self._review_wheel_bound = False
        if self._review_key_bound and self._root:
            for seq in ("<Left>", "<Right>"):
                try:
                    self._root.unbind(seq)
                except Exception:
                    pass
            self._review_key_bound = False
        self._swipe_origin = None

    def _clear_content(self):
        """Clear all widgets from content frame."""
        self._mvp_view = None
        self._unbind_review_input()
        for widget in self._content_frame.winfo_children():
            widget.destroy()

    def _unlock_layout(self):
        monitor_rect = _cursor_monitor_rect()
        _, _, monitor_width, monitor_height = monitor_rect
        try:
            self._root.update_idletasks()
            win_w = int(self._root.winfo_width() or 0)
            win_h = int(self._root.winfo_height() or 0)
        except Exception:
            win_w, win_h = 0, 0
        if win_w < 200:
            win_w = monitor_width
        if win_h < 200:
            win_h = monitor_height
        content_width = _unlock_content_width(win_w, monitor_width)
        usable_h = win_h if win_h < monitor_height * 0.95 else monitor_height
        title_font = min(max(int(usable_h * 0.022), 22), 48)
        body_font = min(max(int(usable_h * 0.014), 16), 26)
        return content_width, title_font, body_font

    def _ensure_review_window(self):
        """Give the review dialog enough room without shrinking a fullscreen overlay."""
        monitor_rect = _cursor_monitor_rect()
        _, _, monitor_width, monitor_height = monitor_rect
        try:
            self._root.update_idletasks()
            win_w = int(self._root.winfo_width() or 0)
            win_h = int(self._root.winfo_height() or 0)
        except Exception:
            win_w, win_h = 0, 0
        if win_w >= monitor_width * 0.9 and win_h >= monitor_height * 0.85:
            return
        width, height = _clamp_dialog_size(monitor_rect, _s(1280), _s(920), max_fraction=0.94)
        rect = _centered_rect(monitor_rect, width, height)
        _force_window_rect(self._root, rect)
        self._content_frame.place_forget()
        self._content_frame.place(relx=0.5, rely=0.5, anchor="center")

    def _attach_scrollable(self, parent, height, bg="#15172a", on_horizontal=None):
        holder = tk.Frame(parent, bg=bg)
        canvas = tk.Canvas(holder, bg=bg, highlightthickness=0, height=height, bd=0)
        try:
            style = ttk.Style(self._root)
            style.theme_use("clam")
            style.configure(
                "Review.Vertical.TScrollbar",
                troughcolor="#0b1220",
                background="#cbd5e1",
                bordercolor="#475569",
                lightcolor="#e2e8f0",
                darkcolor="#334155",
                arrowcolor="#0f172a",
            )
            style.map(
                "Review.Vertical.TScrollbar",
                background=[("active", "#f8fafc"), ("pressed", "#94a3b8")],
            )
            scrollbar = ttk.Scrollbar(
                holder,
                orient="vertical",
                style="Review.Vertical.TScrollbar",
                command=canvas.yview,
            )
        except Exception:
            scrollbar = tk.Scrollbar(
                holder,
                orient="vertical",
                command=canvas.yview,
                width=_s(16),
                troughcolor="#0b1220",
                bg="#cbd5e1",
                activebackground="#f8fafc",
                highlightthickness=0,
            )
        inner = tk.Frame(canvas, bg=bg)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _sync_scroll(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            try:
                canvas.itemconfigure(window_id, width=max(1, canvas.winfo_width()))
            except Exception:
                pass

        inner.bind("<Configure>", _sync_scroll)
        canvas.bind("<Configure>", _sync_scroll)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        def _on_wheel(event):
            shift = bool(getattr(event, "state", 0) & 0x0001)
            delta = int(getattr(event, "delta", 0) or 0)
            if shift and on_horizontal:
                if delta:
                    on_horizontal(-1 if delta > 0 else 1)
                return "break"
            if delta:
                canvas.yview_scroll(int(-1 * (delta / 120)), "units")
            elif getattr(event, "num", None) == 4:
                canvas.yview_scroll(-1, "units")
            elif getattr(event, "num", None) == 5:
                canvas.yview_scroll(1, "units")
            return "break"

        def _on_press(event):
            self._swipe_origin = event.x_root

        def _on_release(event):
            origin = self._swipe_origin
            self._swipe_origin = None
            if origin is None or not on_horizontal:
                return
            dx = event.x_root - origin
            if dx <= -72:
                on_horizontal(1)
            elif dx >= 72:
                on_horizontal(-1)

        for widget in (holder, canvas, inner):
            widget.bind("<MouseWheel>", _on_wheel)
            widget.bind("<Button-4>", _on_wheel)
            widget.bind("<Button-5>", _on_wheel)
            widget.bind("<Shift-MouseWheel>", _on_wheel)
            widget.bind("<ButtonPress-1>", _on_press)
            widget.bind("<ButtonRelease-1>", _on_release)
        if self._root:
            self._root.bind_all("<MouseWheel>", _on_wheel)
            self._root.bind_all("<Button-4>", _on_wheel)
            self._root.bind_all("<Button-5>", _on_wheel)
            self._root.bind_all("<Shift-MouseWheel>", _on_wheel)
        self._review_wheel_bound = True
        return holder, inner, canvas

    def _load_quiz(self, task, activity, reason):
        """Show loading state then fetch quiz in background."""
        self._clear_content()
        frame = self._content_frame

        loading = tk.Label(frame, text="\u554f\u984c\u3092\u8aad\u307f\u8fbc\u307f\u4e2d...",
                           font=("Segoe UI", 18), fg="#4a9eff", bg="#0f0f23")
        loading.pack(pady=50)

        # Fetch quiz in background
        threading.Thread(
            target=self._fetch_and_render,
            args=(task, activity, reason),
            daemon=True,
        ).start()

    def _fetch_and_render(self, task, activity, reason):
        """Fetch quiz then queue render on tk thread."""
        quiz = self._fetch_quiz(task)
        self._command_queue.put(lambda: self._render_quiz(quiz, task, activity, reason))

    def _fetch_quiz(self, task: str) -> dict:
        """Fetch a quiz from the backend."""
        try:
            res = requests.get(f"{BACKEND_URL}/quiz/generate", params={"task": task}, timeout=15)
            return res.json()
        except Exception as e:
            print(f"[blocker] Quiz fetch error: {e}")
            return {
                "question": "\u96c6\u4e2d\u529b\u3092\u4fdd\u3064\u305f\u3081\u306b\u6700\u3082\u52b9\u679c\u7684\u306a\u65b9\u6cd5\u306f\uff1f",
                "options": ["\u30dd\u30e2\u30c9\u30fc\u30ed\u30fb\u30c6\u30af\u30cb\u30c3\u30af", "3\u6642\u9593\u9023\u7d9a\u4f5c\u696d", "SNS\u3092\u958b\u3044\u305f\u307e\u307e", "\u97f3\u697d\u3092\u5927\u97f3\u91cf\u3067"],
                "correct_index": 0,
                "explanation": "\u30dd\u30e2\u30c9\u30fc\u30ed\u30fb\u30c6\u30af\u30cb\u30c3\u30af\u306f\u79d1\u5b66\u7684\u306b\u52b9\u679c\u304c\u5b9f\u8a3c\u3055\u308c\u3066\u3044\u307e\u3059\u3002"
            }

    def _load_translation_unlock(
        self,
        task,
        activity,
        reason,
        nudge_message="",
        recovery=False,
        resume_payload=None,
        recovery_mode="session",
        challenge_total=1,
        challenge_index=1,
        keep_progress=False,
    ):
        """Show loading state then fetch a strict-mode translation challenge."""
        if not keep_progress and int(challenge_index or 1) <= 1:
            self._unlock_reviews = []
        self._clear_content()
        frame = self._content_frame
        tk.Label(
            frame,
            text=f"厳格モード：翻訳問題を読み込み中... ({challenge_index}/{max(1, challenge_total)})",
            font=("Segoe UI", _s(18)),
            fg="#f1c40f",
            bg="#0f0f23",
        ).pack(pady=50)
        threading.Thread(
            target=self._fetch_and_render_translation,
            args=(task, activity, reason, nudge_message, recovery, resume_payload, recovery_mode, challenge_total, challenge_index),
            daemon=True,
        ).start()

    def _fetch_and_render_translation(
        self,
        task,
        activity,
        reason,
        nudge_message="",
        recovery=False,
        resume_payload=None,
        recovery_mode="session",
        challenge_total=1,
        challenge_index=1,
    ):
        try:
            res = requests.get(f"{BACKEND_URL}/strict/translation", timeout=10)
            challenge = res.json()
        except Exception as e:
            print(f"[blocker] Translation challenge fetch error: {e}")
            challenge = {
                "challenge_id": "fallback",
                "source_text": "I will return to my task and work with focus.",
                "instruction": "Translate this English sentence into Japanese.",
            }
        self._command_queue.put(
            lambda: self._render_translation_unlock(
                challenge,
                task,
                activity,
                reason,
                nudge_message=nudge_message,
                recovery=recovery,
                resume_payload=resume_payload,
                recovery_mode=recovery_mode,
                challenge_total=challenge_total,
                challenge_index=challenge_index,
            )
        )

    def _render_translation_unlock(
        self,
        challenge,
        task,
        activity,
        reason,
        nudge_message="",
        recovery=False,
        resume_payload=None,
        recovery_mode="session",
        challenge_total=1,
        challenge_index=1,
    ):
        """Render strict-mode English-to-Japanese unlock task."""
        self._clear_content()
        frame = self._content_frame
        content_width, title_font, body_font = self._unlock_layout()
        source_font = min(max(body_font + 6, 22), 36)
        input_font = min(max(body_font + 2, 18), 30)
        answer_width = max(48, min(96, int(content_width / max(10, input_font * 0.58))))

        tk.Frame(frame, bg="#0f0f23", width=content_width, height=1).pack()

        tk.Label(
            frame,
            text=f"厳格モード：分心を検出しました ({challenge_index}/{max(1, challenge_total)})",
            font=("Segoe UI", title_font, "bold"),
            fg="#f1c40f",
            bg="#0f0f23",
        ).pack(pady=(0, 12))
        info = f"タスク：{task}"
        if activity:
            info += f"  |  検出：{activity}"
        tk.Label(frame, text=info, font=("Segoe UI", body_font), fg="#888", bg="#0f0f23").pack(pady=(0, 18))
        tk.Label(
            frame,
            text=challenge.get("instruction", "Translate the sentence."),
            font=("Segoe UI", body_font),
            fg="#cbd5e1",
            bg="#0f0f23",
            wraplength=content_width,
            justify="center",
        ).pack(pady=(0, 16))
        source_name = challenge.get("source_name") or challenge.get("source") or "practice"
        item_index = challenge.get("item_index")
        item_total = challenge.get("item_total")
        progress = ""
        if isinstance(item_index, int) and item_total:
            progress = f"  |  {item_index + 1}/{item_total}"
        tk.Label(
            frame,
            text=f"Source: {source_name}{progress}",
            font=("Segoe UI", max(12, body_font - 2)),
            fg="#94a3b8",
            bg="#0f0f23",
            wraplength=content_width,
            justify="center",
        ).pack(pady=(0, 10))
        if nudge_message:
            tk.Label(
                frame,
                text=nudge_message,
                font=("Segoe UI", body_font),
                fg="#f8fafc",
                bg="#15172a",
                wraplength=content_width,
                justify="center",
                padx=22,
                pady=16,
            ).pack(fill="x", pady=(0, 16))
        language_label = tk.Label(
            frame,
            text=_keyboard_layout_label(),
            font=("Segoe UI", max(12, body_font - 1), "bold"),
            fg="#f1c40f",
            bg="#0f0f23",
        )
        language_label.pack(pady=(0, 14))
        self._refresh_language_label(language_label)
        tk.Label(
            frame,
            text=challenge.get("source_text", ""),
            font=("Segoe UI", source_font, "bold"),
            fg="#ffffff",
            bg="#0f0f23",
            wraplength=content_width,
            justify="center",
        ).pack(pady=(0, 20))

        answer = tk.Text(
            frame,
            font=("Segoe UI", input_font),
            width=answer_width,
            height=4,
            wrap="word",
            bg="#1a1a2e",
            fg="#ffffff",
            insertbackground="#ffffff",
            relief="flat",
            highlightthickness=1,
            highlightcolor="#f1c40f",
        )
        answer.pack(pady=(0, 16), ipadx=8, ipady=8)
        answer.focus_set()

        result_lbl = tk.Label(frame, text="", font=("Segoe UI", body_font), fg="#cbd5e1", bg="#0f0f23", wraplength=content_width)
        result_lbl.pack(pady=(0, 14))

        button_row = tk.Frame(frame, bg="#0f0f23")
        button_row.pack()

        unlock_widgets = []

        submit_btn = tk.Button(
            button_row,
            text="Submit",
            font=("Segoe UI", body_font, "bold"),
            fg="#0f0f23",
            bg="#f1c40f",
            activebackground="#d4ac0d",
            activeforeground="#0f0f23",
            relief="flat",
            padx=34,
            pady=12,
            cursor="hand2",
            command=lambda: self._submit_translation_unlock(
                challenge,
                answer,
                result_lbl,
                unlock_widgets,
                task,
                activity,
                reason,
                nudge_message,
                recovery,
                resume_payload,
                recovery_mode,
                challenge_total,
                challenge_index,
            ),
        )
        submit_btn.pack(side="left", padx=(0, 10))
        unlock_widgets.append(submit_btn)

        give_up_btn = tk.Button(
            button_row,
            text="答不出来",
            font=("Segoe UI", body_font, "bold"),
            fg="#ffffff",
            bg="#7f1d1d",
            activebackground="#991b1b",
            activeforeground="#ffffff",
            relief="flat",
            padx=28,
            pady=12,
            cursor="hand2",
            command=lambda: self._give_up_translation_unlock(
                challenge,
                result_lbl,
                unlock_widgets,
                task,
                activity,
                reason,
                nudge_message,
                recovery,
                resume_payload,
                recovery_mode,
                challenge_total,
                challenge_index,
            ),
        )
        give_up_btn.pack(side="left", padx=(0, 10))
        unlock_widgets.append(give_up_btn)

        tk.Button(
            button_row,
            text="[TEST] Exit",
            font=("Segoe UI", max(12, body_font - 2), "bold"),
            fg="#cbd5e1",
            bg="#2a2a4a",
            activebackground="#3a3a5a",
            activeforeground="#ffffff",
            relief="flat",
            padx=22,
            pady=12,
            cursor="hand2",
            command=self._correct_dismiss,
        ).pack(side="left")

        # Work / break choices appear on the review screen after all items pass.

    def _show_unlock_complete(self, task, recovery, resume_payload, recovery_mode):
        """After all translation items pass: show review, then work/break."""
        self._clear_content()
        self._ensure_review_window()
        frame = self._content_frame
        content_width, title_font, body_font = self._unlock_layout()
        wrap = max(320, content_width - 56)
        try:
            win_h = int(self._root.winfo_height() or 720)
        except Exception:
            win_h = 720
        review_height = max(240, int(win_h * 0.58))

        tk.Label(
            frame,
            text="题目回顾",
            font=("Segoe UI", title_font, "bold"),
            fg="#ffffff",
            bg="#0f0f23",
        ).pack(pady=(0, 8))
        tk.Label(
            frame,
            text=f"看完全部 {len(self._unlock_reviews)} 题解析后，选择回到工作或开始休息。滚轮上下看解析，左右滑动或方向键换题。",
            font=("Segoe UI", body_font),
            fg="#cbd5e1",
            bg="#0f0f23",
            wraplength=wrap,
            justify="center",
        ).pack(pady=(0, 12))

        review_box = tk.Frame(frame, bg="#15172a", padx=8, pady=8)
        review_box.pack(fill="both", expand=True, pady=(0, 12))
        if not self._unlock_reviews:
            tk.Label(
                review_box,
                text="没有可回顾的题目。",
                font=("Segoe UI", body_font),
                fg="#94a3b8",
                bg="#15172a",
            ).pack(anchor="w")
        else:
            self._review_page = 0
            nav = tk.Frame(review_box, bg="#15172a")
            nav.pack(fill="x", pady=(0, 8))
            page_lbl = tk.Label(
                nav,
                text="",
                font=("Segoe UI", body_font, "bold"),
                fg="#ffffff",
                bg="#15172a",
            )
            prev_btn = tk.Button(
                nav,
                text="← 上一题",
                font=("Segoe UI", max(14, body_font - 2), "bold"),
                fg="#0f0f23",
                bg="#cbd5e1",
                activebackground="#e2e8f0",
                relief="flat",
                padx=16,
                pady=8,
                cursor="hand2",
            )
            next_btn = tk.Button(
                nav,
                text="下一题 →",
                font=("Segoe UI", max(14, body_font - 2), "bold"),
                fg="#0f0f23",
                bg="#cbd5e1",
                activebackground="#e2e8f0",
                relief="flat",
                padx=16,
                pady=8,
                cursor="hand2",
            )
            prev_btn.pack(side="left")
            page_lbl.pack(side="left", expand=True)
            next_btn.pack(side="right")

            holder, inner, canvas = self._attach_scrollable(
                review_box,
                review_height,
                on_horizontal=lambda delta: go_page(delta),
            )
            holder.pack(fill="both", expand=True)

            def render_page():
                for widget in inner.winfo_children():
                    widget.destroy()
                item = self._unlock_reviews[self._review_page]
                card = tk.Frame(inner, bg="#15172a")
                card.pack(fill="x", padx=10, pady=4)
                tk.Label(
                    card,
                    text=f"{self._review_page + 1}. {item.get('source_text') or ''}",
                    font=("Segoe UI", body_font, "bold"),
                    fg="#ffffff",
                    bg="#15172a",
                    wraplength=wrap,
                    justify="left",
                    anchor="w",
                ).pack(anchor="w", fill="x")
                tk.Label(
                    card,
                    text=f"你的翻译：{item.get('user_answer') or '（未记录）'}",
                    font=("Segoe UI", max(14, body_font - 2)),
                    fg="#e2e8f0",
                    bg="#15172a",
                    wraplength=wrap,
                    justify="left",
                    anchor="w",
                ).pack(anchor="w", fill="x", pady=(6, 0))
                if item.get("model_translation"):
                    tk.Label(
                        card,
                        text=f"参考译文：{item.get('model_translation')}",
                        font=("Segoe UI", max(14, body_font - 2)),
                        fg="#2ecc71",
                        bg="#15172a",
                        wraplength=wrap,
                        justify="left",
                        anchor="w",
                    ).pack(anchor="w", fill="x", pady=(4, 0))
                explain = (item.get("explanation") or item.get("feedback") or "").strip()
                if explain:
                    tk.Label(
                        card,
                        text=f"解析：{explain}",
                        font=("Segoe UI", max(14, body_font - 2)),
                        fg="#f1c40f",
                        bg="#15172a",
                        wraplength=wrap,
                        justify="left",
                        anchor="w",
                    ).pack(anchor="w", fill="x", pady=(4, 0))
                total = len(self._unlock_reviews)
                page_lbl.config(text=f"{self._review_page + 1} / {total}")
                prev_btn.config(state="normal" if self._review_page > 0 else "disabled")
                next_btn.config(state="normal" if self._review_page < total - 1 else "disabled")
                inner.update_idletasks()
                canvas.yview_moveto(0)

            def go_page(delta):
                total = len(self._unlock_reviews)
                nxt = _clamp_review_page(self._review_page, total, delta)
                if nxt == self._review_page:
                    return
                self._review_page = nxt
                render_page()

            prev_btn.config(command=lambda: go_page(-1))
            next_btn.config(command=lambda: go_page(1))
            if self._root:
                self._root.bind("<Left>", lambda _e: go_page(-1))
                self._root.bind("<Right>", lambda _e: go_page(1))
                self._review_key_bound = True
            render_page()

        unlock_widgets = []
        if resume_payload:
            resume_button = tk.Button(
                frame,
                text="继续下一任务",
                font=("Segoe UI", body_font + 2, "bold"),
                fg="#0f0f23",
                bg="#2ecc71",
                activebackground="#27ae60",
                activeforeground="#0f0f23",
                relief="flat",
                padx=40,
                pady=16,
                cursor="hand2",
                command=lambda: self._do_show_resume_prompt(resume_payload),
            )
            resume_button.pack(pady=(8, 0))
        elif recovery:
            self._render_recovery_choices(
                frame, task, unlock_widgets, recovery_mode=recovery_mode,
                body_font=body_font, content_width=content_width,
            )
            for widget in unlock_widgets:
                widget.config(state="normal")
        else:
            tk.Button(
                frame,
                text="回到工作",
                font=("Segoe UI", body_font + 2, "bold"),
                fg="#0f0f23",
                bg="#2ecc71",
                activebackground="#27ae60",
                activeforeground="#0f0f23",
                relief="flat",
                padx=40,
                pady=16,
                cursor="hand2",
                command=self._correct_dismiss,
            ).pack(pady=(8, 0))

    def _render_recovery_choices(self, frame, task, unlock_widgets, recovery_mode="session", body_font=None, content_width=None):
        if body_font is None or content_width is None:
            content_width, _, body_font = self._unlock_layout()
        is_guardian = recovery_mode == "guardian"
        btn_font = body_font + 2
        choice_box = tk.Frame(frame, bg="#15172a", padx=20, pady=18)
        choice_box.pack(fill="x", pady=(14, 0))
        tk.Label(
            choice_box,
            text="选择下一步",
            font=("Segoe UI", btn_font, "bold"),
            fg="#ffffff",
            bg="#15172a",
        ).pack(anchor="w", pady=(0, 12))

        step_entry = tk.Entry(
            choice_box,
            font=("Segoe UI", body_font),
            bg="#0f0f23",
            fg="#ffffff",
            insertbackground="#ffffff",
            relief="flat",
        )
        step_entry.insert(0, "回到工作后的最小下一步" if is_guardian else f"{task} の最小の次の一歩")
        step_entry.pack(fill="x", ipady=8, pady=(0, 12))

        row = tk.Frame(choice_box, bg="#15172a")
        row.pack(fill="x", pady=(0, 12))
        tk.Label(row, text="休息分钟", font=("Segoe UI", body_font), fg="#cbd5e1", bg="#15172a").pack(side="left")
        break_minutes = tk.Entry(
            row,
            font=("Segoe UI", body_font),
            width=8,
            bg="#0f0f23",
            fg="#ffffff",
            insertbackground="#ffffff",
            relief="flat",
        )
        break_minutes.insert(0, "10")
        break_minutes.pack(side="left", padx=(12, 16), ipady=6)

        error_label = tk.Label(choice_box, text="", font=("Segoe UI", max(14, body_font - 2)), fg="#ff8a80", bg="#15172a", wraplength=max(320, content_width - 40))
        error_label.pack(fill="x", pady=(0, 12))

        action_row = tk.Frame(choice_box, bg="#15172a")
        action_row.pack(fill="x")
        work_button = tk.Button(
            action_row,
            text="回到工作",
            font=("Segoe UI", btn_font, "bold"),
            fg="#0f0f23",
            bg="#2ecc71",
            activebackground="#27ae60",
            activeforeground="#0f0f23",
            relief="flat",
            padx=36,
            pady=16,
            cursor="hand2",
            state="disabled",
            command=lambda: self._submit_recovery_work(step_entry, error_label, recovery_mode),
        )
        work_button.pack(side="left", padx=(0, 16))
        break_button = tk.Button(
            action_row,
            text="开始休息",
            font=("Segoe UI", btn_font, "bold"),
            fg="#ffffff",
            bg="#4a9eff",
            activebackground="#2f80ed",
            activeforeground="#ffffff",
            relief="flat",
            padx=36,
            pady=16,
            cursor="hand2",
            state="disabled",
            command=lambda: self._submit_recovery_break(break_minutes, step_entry, error_label, recovery_mode),
        )
        break_button.pack(side="left")
        unlock_widgets.extend([work_button, break_button])

    def _refresh_language_label(self, label):
        try:
            if not self._is_showing or not label.winfo_exists():
                return
            label.config(text=_keyboard_layout_label())
            self._root.after(1000, lambda: self._refresh_language_label(label))
        except Exception:
            pass

    def _submit_translation_unlock(
        self,
        challenge,
        answer_entry,
        result_lbl,
        unlock_widgets,
        task,
        activity,
        reason,
        nudge_message,
        recovery,
        resume_payload,
        recovery_mode,
        challenge_total,
        challenge_index,
    ):
        if isinstance(answer_entry, tk.Text):
            answer = answer_entry.get("1.0", "end").strip()
        else:
            answer = answer_entry.get().strip()
        if not answer:
            result_lbl.config(text="日本語訳を入力してください。", fg="#ff8a80")
            return
        result_lbl.config(text="AI判定中...", fg="#4a9eff")
        threading.Thread(
            target=lambda: self._do_translation_grade(
                challenge,
                answer,
                result_lbl,
                unlock_widgets,
                task,
                activity,
                reason,
                nudge_message,
                recovery,
                resume_payload,
                recovery_mode,
                challenge_total,
                challenge_index,
            ),
            daemon=True,
        ).start()

    def _do_translation_grade(
        self,
        challenge,
        answer,
        result_lbl,
        unlock_widgets,
        task,
        activity,
        reason,
        nudge_message,
        recovery,
        resume_payload,
        recovery_mode,
        challenge_total,
        challenge_index,
    ):
        try:
            res = requests.post(
                f"{BACKEND_URL}/strict/translation/grade",
                json={
                    "challenge_id": challenge.get("challenge_id", ""),
                    "source_text": challenge.get("source_text", ""),
                    "user_answer": answer,
                    "source": challenge.get("source", ""),
                    "source_name": challenge.get("source_name", ""),
                    "item_index": challenge.get("item_index"),
                    "item_total": challenge.get("item_total"),
                    "target_language": challenge.get("target_language", ""),
                },
                timeout=30,
            )
            result = res.json()
            review_item = {
                "source_text": challenge.get("source_text", ""),
                "user_answer": answer,
                "feedback": result.get("feedback", ""),
                "explanation": result.get("explanation") or result.get("feedback", ""),
                "model_translation": result.get("model_translation") or "",
                "accepted": bool(result.get("accepted")),
            }
            if result.get("accepted"):
                self._unlock_reviews.append(review_item)
                feedback = result.get("feedback", "OK")
                if int(challenge_index) < max(1, int(challenge_total or 1)):
                    self._command_queue.put(lambda: result_lbl.config(text=f"PASS: {feedback}\n下一题加载中...", fg="#2ecc71"))
                    self._command_queue.put(
                        lambda: self._root.after(
                            700,
                            lambda: self._load_translation_unlock(
                                task,
                                activity,
                                reason,
                                nudge_message=nudge_message,
                                recovery=recovery,
                                resume_payload=resume_payload,
                                recovery_mode=recovery_mode,
                                challenge_total=challenge_total,
                                challenge_index=int(challenge_index) + 1,
                            ),
                        )
                    )
                else:
                    self._command_queue.put(
                        lambda: self._show_unlock_complete(
                            task, recovery, resume_payload, recovery_mode
                        )
                    )
            else:
                feedback = result.get("feedback", "もう一度翻訳してください。")
                explanation = result.get("explanation") or feedback
                self._command_queue.put(
                    lambda: result_lbl.config(text=f"RETRY: {feedback}\n{explanation}", fg="#e74c3c")
                )
        except Exception as e:
            self._command_queue.put(lambda: result_lbl.config(text=f"Grade failed: {e}", fg="#e74c3c"))

    def _set_unlock_widgets_state(self, unlock_widgets, state):
        for widget in unlock_widgets or []:
            try:
                widget.config(state=state)
            except Exception:
                pass

    def _give_up_translation_unlock(
        self,
        challenge,
        result_lbl,
        unlock_widgets,
        task,
        activity,
        reason,
        nudge_message,
        recovery,
        resume_payload,
        recovery_mode,
        challenge_total,
        challenge_index,
    ):
        self._set_unlock_widgets_state(unlock_widgets, "disabled")
        result_lbl.config(text="正在生成正确答案和解析...", fg="#4a9eff")
        threading.Thread(
            target=lambda: self._do_translation_explain(
                challenge,
                result_lbl,
                unlock_widgets,
                task,
                activity,
                reason,
                nudge_message,
                recovery,
                resume_payload,
                recovery_mode,
                challenge_total,
                challenge_index,
            ),
            daemon=True,
        ).start()

    def _do_translation_explain(
        self,
        challenge,
        result_lbl,
        unlock_widgets,
        task,
        activity,
        reason,
        nudge_message,
        recovery,
        resume_payload,
        recovery_mode,
        challenge_total,
        challenge_index,
    ):
        try:
            res = requests.post(
                f"{BACKEND_URL}/strict/translation/explain",
                json={
                    "challenge_id": challenge.get("challenge_id", ""),
                    "source_text": challenge.get("source_text", ""),
                    "source": challenge.get("source", ""),
                    "source_name": challenge.get("source_name", ""),
                    "item_index": challenge.get("item_index"),
                    "item_total": challenge.get("item_total"),
                    "target_language": challenge.get("target_language", ""),
                },
                timeout=30,
            )
            result = res.json()
            if res.status_code >= 400:
                raise RuntimeError(result.get("detail") or res.text)
            self._command_queue.put(
                lambda captured=result: self._show_translation_give_up(
                    challenge,
                    captured,
                    task,
                    activity,
                    reason,
                    nudge_message,
                    recovery,
                    resume_payload,
                    recovery_mode,
                    challenge_total,
                    challenge_index,
                )
            )
        except Exception as e:
            error_text = str(e)
            self._command_queue.put(
                lambda: (
                    result_lbl.config(text=f"解析失败：{error_text}", fg="#e74c3c"),
                    self._set_unlock_widgets_state(unlock_widgets, "normal"),
                )
            )

    def _show_translation_give_up(
        self,
        challenge,
        result,
        task,
        activity,
        reason,
        nudge_message,
        recovery,
        resume_payload,
        recovery_mode,
        challenge_total,
        challenge_index,
    ):
        """Show the model answer, then load another question without counting a pass."""
        self._clear_content()
        frame = self._content_frame
        content_width, title_font, body_font = self._unlock_layout()
        wrap = max(320, content_width - 40)
        source_text = challenge.get("source_text") or ""
        model_translation = (result.get("model_translation") or "").strip()
        explanation = (result.get("explanation") or "").strip()

        tk.Label(
            frame,
            text=f"本题跳过，不算过关 ({challenge_index}/{max(1, challenge_total)})",
            font=("Segoe UI", title_font, "bold"),
            fg="#f1c40f",
            bg="#0f0f23",
        ).pack(pady=(0, 12))
        tk.Label(
            frame,
            text=source_text,
            font=("Segoe UI", body_font, "bold"),
            fg="#ffffff",
            bg="#0f0f23",
            wraplength=wrap,
            justify="center",
        ).pack(pady=(0, 16))
        if model_translation:
            tk.Label(
                frame,
                text=f"参考译文：{model_translation}",
                font=("Segoe UI", body_font),
                fg="#2ecc71",
                bg="#0f0f23",
                wraplength=wrap,
                justify="left",
            ).pack(anchor="w", pady=(0, 10))
        if explanation:
            tk.Label(
                frame,
                text=f"解析：{explanation}",
                font=("Segoe UI", body_font),
                fg="#f1c40f",
                bg="#0f0f23",
                wraplength=wrap,
                justify="left",
            ).pack(anchor="w", pady=(0, 20))
        tk.Button(
            frame,
            text="下一题",
            font=("Segoe UI", body_font + 2, "bold"),
            fg="#0f0f23",
            bg="#f1c40f",
            activebackground="#d4ac0d",
            activeforeground="#0f0f23",
            relief="flat",
            padx=40,
            pady=16,
            cursor="hand2",
            command=lambda: self._load_translation_unlock(
                task,
                activity,
                reason,
                nudge_message=nudge_message,
                recovery=recovery,
                resume_payload=resume_payload,
                recovery_mode=recovery_mode,
                challenge_total=challenge_total,
                challenge_index=challenge_index,
                keep_progress=True,
            ),
        ).pack(pady=(8, 0))

    def _submit_recovery_work(self, step_entry, error_label, recovery_mode="session"):
        step = step_entry.get().strip()
        if not step:
            error_label.config(text="请输入一个最小下一步。")
            return
        path = "/guardian/recovery/work" if recovery_mode == "guardian" else "/session/recovery/work"
        self._post_recovery(path, {"minimum_next_step": step}, error_label)

    def _submit_recovery_break(self, minutes_entry, step_entry, error_label, recovery_mode="session"):
        try:
            minutes = int(minutes_entry.get().strip())
            if minutes <= 0:
                raise ValueError()
        except Exception:
            error_label.config(text="休息时长需要是正整数。")
            return
        step = step_entry.get().strip()
        if not step:
            error_label.config(text="请输入休息后要做的最小下一步。")
            return
        path = "/guardian/recovery/break" if recovery_mode == "guardian" else "/session/recovery/break"
        self._post_recovery(path, {"break_minutes": minutes, "minimum_next_step": step}, error_label)

    def _post_recovery(self, path, payload, error_label):
        error_label.config(text="")
        threading.Thread(target=lambda: self._do_post_recovery(path, payload, error_label), daemon=True).start()

    def _do_post_recovery(self, path, payload, error_label):
        try:
            res = requests.post(f"{BACKEND_URL}{path}", json=payload, timeout=10)
            if res.status_code >= 400:
                raise RuntimeError(res.text)
            self._command_queue.put(self._message_dismiss)
        except Exception as e:
            self._command_queue.put(lambda: error_label.config(text=f"操作失败：{e}"))

    def _render_quiz(self, quiz, task, activity, reason):
        """Render quiz UI (runs on tk thread)."""
        self._clear_content()
        frame = self._content_frame

        # Title
        tk.Label(frame, text="\u26a0\ufe0f \u6c17\u304c\u6563\u3063\u3066\u3044\u307e\u3059\uff01\u554f\u984c\u306b\u7b54\u3048\u3066\u304f\u3060\u3055\u3044",
                 font=("Segoe UI", 24, "bold"), fg="#e74c3c", bg="#0f0f23").pack(pady=(0, 8))

        # Info
        info = f"\u30bf\u30b9\u30af\uff1a{task}"
        if activity and activity not in ("", "テストモード"):
            info += f"  |  \u691c\u51fa\uff1a{activity}"
        tk.Label(frame, text=info, font=("Segoe UI", 11), fg="#888", bg="#0f0f23").pack(pady=(0, 20))

        # Question
        tk.Label(frame, text=quiz.get("question", ""), font=("Segoe UI", 18, "bold"),
                 fg="#fff", bg="#0f0f23", wraplength=700).pack(pady=(0, 20))

        # Options
        options = quiz.get("options", [])
        correct_idx = quiz.get("correct_index", 0)
        labels = ["A", "B", "C", "D"]
        btn_frame = tk.Frame(frame, bg="#0f0f23")
        btn_frame.pack(pady=(0, 15))

        for i, opt in enumerate(options):
            tk.Button(
                btn_frame, text=f"  {labels[i]}.  {opt}",
                font=("Segoe UI", 14), fg="#fff", bg="#2a2a4a",
                activebackground="#3a3a5a", activeforeground="#fff",
                relief="flat", anchor="w", width=50, pady=10, padx=15, cursor="hand2",
                command=lambda idx=i: self._on_answer(idx, correct_idx, quiz, task),
            ).pack(pady=3)

        tk.Button(
            btn_frame,
            text="答不出来",
            font=("Segoe UI", 14, "bold"),
            fg="#ffffff",
            bg="#7f1d1d",
            activebackground="#991b1b",
            activeforeground="#ffffff",
            relief="flat",
            anchor="w",
            width=50,
            pady=10,
            padx=15,
            cursor="hand2",
            command=lambda: self._give_up_quiz(quiz, task),
        ).pack(pady=(10, 3))

        # Result
        self._result_label = tk.Label(frame, text="", font=("Segoe UI", 14), fg="#fff", bg="#0f0f23", wraplength=600)
        self._result_label.pack(pady=(10, 0))

        # Dispute
        tk.Button(frame, text="\u7570\u8b70\u3042\u308a\uff08\u5b9f\u306f\u96c6\u4e2d\u3057\u3066\u3044\u308b\uff09",
                  font=("Segoe UI", 10), fg="#4a9eff", bg="#0f0f23",
                  activebackground="#0f0f23", activeforeground="#4a9eff",
                  relief="flat", cursor="hand2",
                  command=lambda: self._show_dispute(frame, task)).pack(pady=(15, 0))

        # TEMP: Close button for testing
        tk.Button(frame, text="[DEBUG] \u9589\u3058\u308b",
                  font=("Segoe UI", 9), fg="#666", bg="#0f0f23",
                  activebackground="#0f0f23", activeforeground="#999",
                  relief="flat", cursor="hand2",
                  command=self._correct_dismiss).pack(pady=(10, 0))

    def _on_answer(self, selected_idx, correct_idx, quiz, task):
        """Handle answer (runs on tk thread)."""
        options = quiz.get("options", [])
        explanation = quiz.get("explanation", "")

        if selected_idx == correct_idx:
            self._show_quiz_review(quiz, task, selected_idx, correct_idx, passed=True)
        else:
            user_ans = options[selected_idx] if selected_idx < len(options) else "?"
            correct_ans = options[correct_idx] if correct_idx < len(options) else "?"
            self._result_label.config(
                text=f"\u274c \u4e0d\u6b63\u89e3\u3002\u6b63\u89e3\u306f\u300c{correct_ans}\u300d\u3002{explanation}\n\n\u6b21\u306e\u554f\u984c\u3078...",
                fg="#e74c3c",
            )
            threading.Thread(
                target=self._record_wrong,
                args=(quiz.get("question", ""), user_ans, correct_ans, task),
                daemon=True,
            ).start()
            self._root.after(4000, lambda: self._load_quiz(task, "", ""))

    def _give_up_quiz(self, quiz, task):
        options = quiz.get("options", [])
        correct_idx = quiz.get("correct_index", 0)
        correct_ans = options[correct_idx] if correct_idx < len(options) else "?"
        threading.Thread(
            target=self._record_wrong,
            args=(quiz.get("question", ""), "答不出来", correct_ans, task),
            daemon=True,
        ).start()
        self._show_quiz_review(quiz, task, selected_idx=None, correct_idx=correct_idx, next_question=True)

    def _show_quiz_review(self, quiz, task, selected_idx, correct_idx, passed=True, next_question=False):
        """Keep the question on screen with AI explanation, then a large continue button."""
        self._clear_content()
        frame = self._content_frame
        content_width, title_font, body_font = self._unlock_layout()
        wrap = max(320, content_width - 40)
        options = quiz.get("options", [])
        labels = ["A", "B", "C", "D"]
        correct_ans = options[correct_idx] if 0 <= int(correct_idx or 0) < len(options) else "?"
        if selected_idx is None:
            user_line = "你的答案：答不出来"
        else:
            user_ans = options[selected_idx] if selected_idx < len(options) else "?"
            label = labels[selected_idx] if selected_idx < 4 else "?"
            user_line = f"你的答案：{label}. {user_ans}"
        explanation = (quiz.get("explanation") or "").strip()
        title = "本题跳过，不算过关" if next_question else "题目回顾"

        tk.Label(
            frame,
            text=title,
            font=("Segoe UI", title_font, "bold"),
            fg="#ffffff",
            bg="#0f0f23",
        ).pack(pady=(0, 10))
        tk.Label(
            frame,
            text=quiz.get("question", ""),
            font=("Segoe UI", body_font, "bold"),
            fg="#ffffff",
            bg="#0f0f23",
            wraplength=wrap,
            justify="left",
        ).pack(anchor="w", pady=(0, 12))
        tk.Label(
            frame,
            text=user_line,
            font=("Segoe UI", body_font),
            fg="#94a3b8",
            bg="#0f0f23",
            wraplength=wrap,
            justify="left",
        ).pack(anchor="w")
        tk.Label(
            frame,
            text=f"正解：{labels[correct_idx] if isinstance(correct_idx, int) and correct_idx < 4 else '?'}. {correct_ans}",
            font=("Segoe UI", body_font),
            fg="#2ecc71",
            bg="#0f0f23",
            wraplength=wrap,
            justify="left",
        ).pack(anchor="w", pady=(4, 8))
        if explanation:
            tk.Label(
                frame,
                text=f"解析：{explanation}",
                font=("Segoe UI", body_font),
                fg="#f1c40f",
                bg="#0f0f23",
                wraplength=wrap,
                justify="left",
            ).pack(anchor="w", pady=(0, 20))
        next_btn = tk.Button(
            frame,
            text="下一题" if next_question else "回到工作",
            font=("Segoe UI", body_font + 2, "bold"),
            fg="#0f0f23",
            bg="#f1c40f" if next_question else "#2ecc71",
            activebackground="#d4ac0d" if next_question else "#27ae60",
            activeforeground="#0f0f23",
            relief="flat",
            padx=40,
            pady=16,
            cursor="hand2",
            command=(lambda: self._load_quiz(task, "", "")) if next_question else self._correct_dismiss,
        )
        next_btn.pack(pady=(8, 0))

    def _correct_dismiss(self):
        """Correct answer: hide and acknowledge."""
        self._is_showing = False
        self._do_hide()
        threading.Thread(target=self._call_acknowledge, daemon=True).start()

    def _record_wrong(self, question, user_ans, correct_ans, task):
        try:
            requests.post(f"{BACKEND_URL}/quiz/wrong",
                          json={"question": question, "user_answer": user_ans,
                                "correct_answer": correct_ans, "task": task}, timeout=5)
        except Exception:
            pass

    def _call_acknowledge(self):
        try:
            requests.post(f"{BACKEND_URL}/session/acknowledge", json={}, timeout=5)
        except Exception:
            pass

    def _show_dispute(self, parent_frame, task):
        """Show dispute input."""
        d_frame = tk.Frame(parent_frame, bg="#0f0f23")
        d_frame.pack(pady=(10, 0))

        entry = tk.Entry(d_frame, font=("Segoe UI", 12), width=40,
                         bg="#1a1a2e", fg="#fff", insertbackground="#fff",
                         relief="flat", highlightthickness=1, highlightcolor="#4a9eff")
        entry.pack(side="left", padx=(0, 8))
        entry.focus_set()

        result_lbl = tk.Label(parent_frame, text="", font=("Segoe UI", 11), fg="#aaa", bg="#0f0f23", wraplength=500)
        result_lbl.pack(pady=(5, 0))

        def submit():
            reason = entry.get().strip()
            if not reason:
                return
            result_lbl.config(text="AI\u8a55\u4fa1\u4e2d...", fg="#4a9eff")
            threading.Thread(target=lambda: self._do_dispute(reason, result_lbl), daemon=True).start()

        tk.Button(d_frame, text="\u9001\u4fe1", font=("Segoe UI", 12, "bold"),
                  fg="#fff", bg="#4a9eff", relief="flat", padx=15, pady=5, cursor="hand2",
                  command=submit).pack(side="left")

    def _do_dispute(self, reason, result_lbl):
        try:
            res = requests.post(f"{BACKEND_URL}/session/dispute", json={"reason": reason}, timeout=30)
            result = res.json()
            if result.get("accepted"):
                self._command_queue.put(lambda: result_lbl.config(text="\u2705 \u7570\u8b70\u304c\u8a8d\u3081\u3089\u308c\u307e\u3057\u305f", fg="#2ecc71"))
                self._command_queue.put(lambda: self._root.after(1500, self._correct_dismiss))
            else:
                msg = f"\u274c \u5374\u4e0b: {result.get('ai_reason', '')}"
                self._command_queue.put(lambda: result_lbl.config(text=msg, fg="#e74c3c"))
        except Exception as e:
            self._command_queue.put(lambda: result_lbl.config(text=f"Error: {e}", fg="#e74c3c"))


class _NoopBlocker:
    is_showing = False

    def show(self, *args, **kwargs):
        self.is_showing = True

    def show_message(self, *args, **kwargs):
        self.is_showing = True

    def show_flow_prompt(self, *args, **kwargs):
        self.is_showing = True

    def show_resume_prompt(self, *args, **kwargs):
        self.is_showing = True

    def show_break_end_translation(self, *args, **kwargs):
        self.is_showing = True

    def show_stop_resume_prompt(self, *args, **kwargs):
        self.is_showing = True

    def dismiss(self):
        self.is_showing = False


# Singleton - starts the persistent tk thread immediately unless tests opt out.
if os.getenv("AIMONITOR_NO_BLOCKER_SINGLETON") == "1":
    blocker = _NoopBlocker()
else:
    blocker = BlockerWindow()
