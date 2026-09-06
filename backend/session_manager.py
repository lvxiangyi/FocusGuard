import asyncio
import json
import uuid
import time
import math
from datetime import datetime
from typing import Optional

from data_paths import LOGS_DIR
from report_manager import record_block
from screenshot import capture_screenshot, reused_judgement, should_reuse_previous, timestamped_screenshot_path
from vision_judge import judge_screenshot, evaluate_dispute
from blocker_window import blocker
from settings_manager import (
    get_default_check_interval_seconds,
    get_default_strict_mode,
    get_default_trigger_threshold,
    get_nudge_prompt,
    get_post_block_cooldown_seconds,
    get_supervision_level,
)


LOG_FILE = LOGS_DIR / "session_logs.jsonl"
MEMORY_FILE = LOGS_DIR / "dispute_memory.json"


def _load_memory() -> list:
    """Load dispute memory (accepted disputes that AI should remember)."""
    if MEMORY_FILE.exists():
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_memory(memory: list):
    """Save dispute memory."""
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, ensure_ascii=False, indent=2)


class SessionManager:
    """Manages a single focus monitoring session."""

    def __init__(self):
        self.session_id: Optional[str] = None
        self.task: Optional[str] = None
        self.duration_minutes: int = 10
        self.check_interval_seconds: int = get_default_check_interval_seconds()
        self.trigger_threshold: int = get_default_trigger_threshold()
        self.active: bool = False
        self.start_time: Optional[float] = None
        self.latest_judgement: Optional[dict] = None
        self.off_task_streak: int = 0
        self.should_block: bool = False
        self.logs: list = []
        self._loop_task: Optional[asyncio.Task] = None
        self.dispute_memory: list = _load_memory()
        self.source: str = "manual"
        self.schedule_id: Optional[str] = None
        self.planned_start: Optional[str] = None
        self.planned_end: Optional[str] = None
        self.late_started: bool = False
        self.tags: list = []
        self.strict_mode: bool = True
        self.supervision_level: str = get_supervision_level()
        self.recovery_actions: list = []
        self.first_check_delay_seconds: float = 0
        self._finalized: bool = False
        self._paused_at: Optional[float] = None
        self.paused_for_rest: bool = False
        self._next_check_at: float = 0
        self._cache_revision = 0
        self.block_id = None
        self.monitor_error = None
        self._last_screenshot_thumb = None

    def start_session(
        self,
        task: str,
        duration_minutes: int,
        check_interval_seconds: int,
        source: str = "manual",
        schedule_id: Optional[str] = None,
        planned_start: Optional[str] = None,
        planned_end: Optional[str] = None,
        late_started: bool = False,
        tags: Optional[list] = None,
        strict_mode: Optional[bool] = None,
        supervision_level: Optional[str] = None,
        trigger_threshold: Optional[int] = None,
        first_check_delay_seconds: float = 0,
    ) -> str:
        """Start a new monitoring session."""
        task = (task or "").strip()
        if not task:
            raise ValueError("Task cannot be empty.")
        if duration_minutes <= 0:
            raise ValueError("Duration must be greater than 0.")
        if check_interval_seconds <= 0:
            raise ValueError("Check interval must be greater than 0.")
        if trigger_threshold is not None and trigger_threshold <= 0:
            raise ValueError("Trigger threshold must be greater than 0.")

        # Guardian does not run in the MVP profile.

        if self.active:
            self.stop_session(status="replaced")

        self.session_id = str(uuid.uuid4())[:8]
        self.task = task
        self.duration_minutes = duration_minutes
        self.check_interval_seconds = check_interval_seconds
        self.trigger_threshold = trigger_threshold if trigger_threshold is not None else get_default_trigger_threshold()
        self.active = True
        self.start_time = time.time()
        self.latest_judgement = None
        self.off_task_streak = 0
        self.should_block = False
        self.logs = []
        self.dispute_memory = _load_memory()
        self.source = source
        self.schedule_id = schedule_id
        self.planned_start = planned_start
        self.planned_end = planned_end
        self.late_started = late_started
        self.tags = [str(tag).strip() for tag in (tags or []) if str(tag).strip()]
        self.strict_mode = get_default_strict_mode() if strict_mode is None else bool(strict_mode)
        self.supervision_level = supervision_level or get_supervision_level()
        self.recovery_actions = []
        self.first_check_delay_seconds = max(0, float(first_check_delay_seconds or 0))
        self._finalized = False
        self._paused_at = None
        self.paused_for_rest = False
        self._next_check_at = 0
        self._cache_revision = 0
        self.block_id = None
        self.monitor_error = None
        self._last_screenshot_thumb = None
        # MVP sessions do not inherit hidden Guardian rest state.

        # Start background monitoring loop
        self._loop_task = asyncio.create_task(self._monitor_loop())

        return self.session_id

    def _cancel_guardian_mode_state(self):
        try:
            from guardian_manager import guardian_manager

            # Rest is independent: starting a Session must not cancel it.
            guardian_manager.cancel_entertainment(commit_elapsed=True)
        except Exception as e:
            print(f"[session] Could not cancel guardian entertainment before session start: {e}")

    def _pause_if_rest_active(self):
        try:
            from guardian_manager import guardian_manager

            if guardian_manager.pending_break:
                self.pause_for_rest()
        except Exception as e:
            print(f"[session] Could not pause for existing rest: {e}")

    def stop_session(self, status: str = "stopped", notify: bool = False, stop_reason: Optional[str] = None):
        """Stop the current session."""
        self._finish_session(status=status, notify=notify, stop_reason=stop_reason)
        current_task = None
        try:
            current_task = asyncio.current_task()
        except RuntimeError:
            pass
        if self._loop_task and not self._loop_task.done() and self._loop_task is not current_task:
            self._loop_task.cancel()
        self._loop_task = None

    def _finish_session(self, status: str, notify: bool = False, stop_reason: Optional[str] = None):
        """Finalize the current session and write it to the daily report."""
        if self._finalized or not self.session_id:
            self.active = False
            return

        self.active = False
        self.should_block = False
        self._paused_at = None
        self.paused_for_rest = False

        actual_start = datetime.fromtimestamp(self.start_time).isoformat() if self.start_time else None
        actual_end = datetime.now().isoformat()
        elapsed_minutes = 0
        if self.start_time:
            elapsed_minutes = max(0, (time.time() - self.start_time) / 60)

        valid_logs = [l for l in self.logs if l.get("judgement_status", "ok") != "api_error"]
        focused_checks = sum(1 for l in valid_logs if l.get("on_task", False))
        distracted_checks = sum(1 for l in valid_logs if not l.get("on_task", False))
        api_error_checks = sum(1 for l in self.logs if l.get("judgement_status") == "api_error")
        focus_minutes = min(elapsed_minutes, focused_checks * self.check_interval_seconds / 60)

        block = {
            "session_id": self.session_id,
            "schedule_id": self.schedule_id,
            "task": self.task,
            "source": self.source,
            "status": status,
            "late_started": self.late_started,
            "planned_start": self.planned_start,
            "planned_end": self.planned_end,
            "actual_start": actual_start,
            "actual_end": actual_end,
            "duration_minutes": round(elapsed_minutes, 1),
            "focus_minutes": round(focus_minutes, 1),
            "total_checks": len(valid_logs),
            "focused_checks": focused_checks,
            "distracted_checks": distracted_checks,
            "api_error_checks": api_error_checks,
            "tags": self.tags,
            "strict_mode": self.strict_mode,
            "supervision_level": self.supervision_level,
            "trigger_threshold": self.trigger_threshold,
        }
        if stop_reason:
            block["stop_reason"] = stop_reason
        record_block(block)
        if self.schedule_id:
            try:
                from schedule_manager import remove_schedule
                remove_schedule(self.schedule_id)
            except Exception as e:
                print(f"[session] Could not remove completed schedule {self.schedule_id}: {e}")
        self._finalized = True

        blocker.dismiss()

    def acknowledge_block(self):
        """User acknowledged the block overlay."""
        self.should_block = False
        self.off_task_streak = 0
        # Dismiss system-level blocker window
        blocker.dismiss()
        self.resume_after_rest()

    def dispute(self, reason: str) -> dict:
        """User disputes the AI judgement. Ask AI to re-evaluate."""
        result = evaluate_dispute(
            task=self.task,
            activity=self.latest_judgement.get("current_activity", "") if self.latest_judgement else "",
            original_reason=self.latest_judgement.get("reason", "") if self.latest_judgement else "",
            user_reason=reason,
            memory=self.dispute_memory,
        )

        if result.get("accepted", False):
            # AI accepted the dispute - remember this for future
            memory_entry = {
                "timestamp": datetime.now().isoformat(),
                "task": self.task,
                "activity": self.latest_judgement.get("current_activity", "") if self.latest_judgement else "",
                "user_reason": reason,
                "ai_note": result.get("ai_reason", ""),
            }
            self.dispute_memory.append(memory_entry)
            _save_memory(self.dispute_memory)

            # Clear block state
            self.should_block = False
            self.off_task_streak = 0
            blocker.dismiss()

            print(f"[session] Dispute ACCEPTED: {reason}")
        else:
            print(f"[session] Dispute REJECTED: {result.get('ai_reason', '')}")

        return result

    def _rest_still_active(self) -> bool:
        try:
            from guardian_manager import guardian_manager
            return bool(guardian_manager.pending_break)
        except Exception:
            return False

    def _release_stale_rest_pause(self):
        """Unstick Session if rest already ended and no overlay is holding it."""
        if not self.paused_for_rest:
            return False
        overlay = bool(self.should_block)
        try:
            overlay = overlay or bool(blocker.is_showing)
        except Exception:
            pass
        if overlay or self._rest_still_active():
            return False
        return self.resume_after_rest()

    def _is_paused_externally(self) -> bool:
        self._release_stale_rest_pause()
        if self.paused_for_rest:
            return True
        if self.should_block:
            return True
        try:
            return bool(blocker.is_showing)
        except Exception:
            return False

    def pause_for_rest(self) -> bool:
        """Freeze Session time and skip screenshots while an independent rest runs."""
        if not self.active:
            return False
        self.paused_for_rest = True
        self._sync_overlay_pause()
        print(f"[session] Paused for rest (remaining {self.get_remaining_seconds()}s).")
        return True

    def resume_after_rest(self) -> bool:
        if not self.paused_for_rest:
            return False
        self.paused_for_rest = False
        if not self.active:
            self._paused_at = None
            return False
        self._sync_overlay_pause()
        print(f"[session] Resumed after rest (remaining {self.get_remaining_seconds()}s).")
        return True

    def _sync_overlay_pause(self) -> bool:
        """Freeze remaining time while rest, quiz, or review overlay is showing.

        Answering (and the new review screen) can take longer than the leftover
        session time. If we keep counting, the session finalizes, Electron drops
        the running status panel, and 回到工作 looks like it killed the session.
        """
        showing = self._is_paused_externally()
        if showing:
            if self._paused_at is None:
                self._paused_at = time.time()
            return True
        if self._paused_at is not None:
            self.start_time = (self.start_time or time.time()) + (time.time() - self._paused_at)
            self._paused_at = None
            self._arm_post_block_cooldown()
        return False

    def _arm_post_block_cooldown(self):
        delay = max(0, int(get_post_block_cooldown_seconds()))
        self._next_check_at = time.time() + delay
        if delay:
            print(f"[session] Post-block cooldown {delay}s before next screenshot.")

    def get_remaining_seconds(self) -> int:
        """Get remaining time in seconds."""
        if not self.active or not self.start_time:
            return 0
        elapsed = time.time() - self.start_time
        if self._paused_at is not None:
            elapsed -= time.time() - self._paused_at
        total = self.duration_minutes * 60
        remaining = max(0, total - elapsed)
        return int(remaining)

    def get_status(self) -> dict:
        """Get current session status."""
        self._release_stale_rest_pause()
        return {
            "active": self.active,
            "duration_minutes": self.duration_minutes,
            "next_check_seconds": max(0, int(self._next_check_at - time.time())),
            "monitor_error": self.monitor_error,
            "block_id": self.block_id,
            "session_id": self.session_id,
            "task": self.task,
            "remaining_seconds": self.get_remaining_seconds(),
            "latest_judgement": self.latest_judgement,
            "off_task_streak": self.off_task_streak,
            "should_block": self.should_block,
            "source": self.source,
            "schedule_id": self.schedule_id,
            "planned_start": self.planned_start,
            "planned_end": self.planned_end,
            "tags": self.tags,
            "strict_mode": self.strict_mode,
            "paused_for_rest": bool(self.paused_for_rest),
            "supervision_level": self.supervision_level,
            "trigger_threshold": self.trigger_threshold,
            "logs": self.logs[-20:],  # Return last 20 logs
            "recovery_actions": self.recovery_actions[-10:],
        }

    def record_recovery_action(self, action: str, minimum_next_step: str = "", break_minutes: Optional[int] = None):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "session_id": self.session_id,
            "action": action,
            "minimum_next_step": minimum_next_step,
        }
        if break_minutes is not None:
            entry["break_minutes"] = break_minutes
        self.recovery_actions.append(entry)

    def choose_recovery_work(self, minimum_next_step: str):
        step = (minimum_next_step or "").strip()
        if not step:
            raise ValueError("请输入一个最小下一步。")
        self.record_recovery_action("work", step)
        self.acknowledge_block()

    def choose_recovery_break(self, break_minutes: int, minimum_next_step: str) -> dict:
        step = (minimum_next_step or "").strip()
        if not step:
            raise ValueError("请输入休息后要做的最小下一步。")
        if break_minutes <= 0:
            raise ValueError("休息时长需要是正整数。")
        if not self.active:
            raise ValueError("当前没有正在运行的 Session。")

        payload = {
            "task": self.task or step,
            "duration_minutes": max(1, math.ceil(self.get_remaining_seconds() / 60)),
            "check_interval_seconds": self.check_interval_seconds,
            "trigger_threshold": self.trigger_threshold,
            "tags": self.tags,
            "strict_mode": self.strict_mode,
            "minimum_next_step": step,
        }
        self.record_recovery_action("break", step, break_minutes)
        self.stop_session(status="break_requested", stop_reason=f"Recovery break: {step}")
        payload["break_minutes"] = break_minutes
        return payload

    def invalidate_judgement_cache(self):
        self._cache_revision += 1
        self._last_screenshot_thumb = None

    def _apply_judgement(self, result: dict) -> str:
        """Apply a judgement to streak/blocking state and return its status."""
        judgement_status = result.get("judgement_status", "ok")
        if judgement_status == "api_error":
            return judgement_status

        if result.get("on_task", True):
            self.off_task_streak = 0
            self.should_block = False
        else:
            self.off_task_streak += 1

        if self.off_task_streak >= self.trigger_threshold:
            if not self.should_block:
                self.block_id = uuid.uuid4().hex
            self.should_block = True

        return judgement_status

    async def _monitor_loop(self):
        """Background loop: take screenshot, judge, update state."""
        try:
            if self.first_check_delay_seconds > 0:
                await asyncio.sleep(self.first_check_delay_seconds)
            while self.active:
                if self._sync_overlay_pause():
                    await asyncio.sleep(1)
                    continue

                # Check if session time is up
                if self.get_remaining_seconds() <= 0:
                    print(f"[session] Session {self.session_id} time is up. Stopping.")
                    self._finish_session(status="completed", notify=True)
                    break

                if time.time() < self._next_check_at:
                    await asyncio.sleep(1)
                    continue

                cache_revision = self._cache_revision
                # Take screenshot. Save each check to its own timestamped file:
                # a shared latest.jpg would be overwritten next check and every
                # historical log row would show the newest image.
                try:
                    screenshot_path, thumb = capture_screenshot(output_path=timestamped_screenshot_path())
                except Exception as e:
                    print(f"[session] Screenshot error: {e}")
                    self.monitor_error = str(e)
                    self._next_check_at = time.time() + self.check_interval_seconds
                    await asyncio.sleep(min(self.check_interval_seconds, max(0.1, self.get_remaining_seconds())))
                    continue

                if should_reuse_previous(self._last_screenshot_thumb, thumb, self.latest_judgement):
                    result = reused_judgement(self.latest_judgement)
                    print("[session] Screenshot nearly unchanged; reusing previous judgement.")
                else:
                    result = await asyncio.to_thread(
                        judge_screenshot, self.task,
                        screenshot_path,
                        memory=self.dispute_memory,
                        supervision_level=self.supervision_level,
                    )
                if self.get_remaining_seconds() <= 0:
                    self._finish_session(status="completed")
                    break
                self.monitor_error = None
                self._last_screenshot_thumb = thumb if cache_revision == self._cache_revision else None
                self.latest_judgement = result
                judgement_status = self._apply_judgement(result)

                # Check if should block
                if self.should_block:
                    # Show system-level blocker window
                    if not blocker.is_showing:
                        try:
                            blocker.show(
                                task=self.task,
                                activity=result.get("current_activity", ""),
                                reason=result.get("reason", ""),
                                strict_mode=self.strict_mode,
                                nudge_message=get_nudge_prompt(),
                            )
                        except Exception as e:
                            print(f"[session] Blocker show error (non-fatal): {e}")
                    # Freeze remaining time immediately; do not sleep the full
                    # check interval while the user is answering.
                    self._sync_overlay_pause()

                # Create log entry
                log_entry = {
                    "timestamp": datetime.now().isoformat(),
                    "session_id": self.session_id,
                    "task": self.task,
                    "source": self.source,
                    "schedule_id": self.schedule_id,
                    "judgement_status": judgement_status,
                    "on_task": result.get("on_task", True),
                    "confidence": result.get("confidence", 0),
                    "current_activity": result.get("current_activity", ""),
                    "reason": result.get("reason", ""),
                    "model": result.get("model", ""),
                    "supervision_level": self.supervision_level,
                    "trigger_threshold": self.trigger_threshold,
                    "screenshot_path": screenshot_path,
                }
                self.logs.append(log_entry)

                # Write to log file
                with open(LOG_FILE, "a", encoding="utf-8") as f:
                    f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

                print(
                    f"[session] Check: on_task={result.get('on_task')} "
                    f"streak={self.off_task_streak} "
                    f"activity={result.get('current_activity')}"
                )

                # Wait for next interval. If the overlay is up, skip the long
                # sleep so remaining time stays frozen instead of draining.
                if self._sync_overlay_pause():
                    await asyncio.sleep(1)
                    continue
                self._next_check_at = time.time() + self.check_interval_seconds
                await asyncio.sleep(min(self.check_interval_seconds, max(0.1, self.get_remaining_seconds())))

        except asyncio.CancelledError:
            print(f"[session] Session {self.session_id} cancelled.")
        except Exception as e:
            print(f"[session] Monitor loop error: {e}")
            self.monitor_error = str(e)
            self._finish_session(status="error")


# Singleton session manager
session_manager = SessionManager()
