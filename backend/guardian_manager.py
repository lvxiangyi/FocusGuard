import asyncio
import json
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from blocker_window import blocker
from data_paths import GUARDIAN_LOG_FILE, GUARDIAN_SCREENSHOT_DIR, GUARDIAN_STATE_FILE
from screenshot import take_screenshot
from settings_manager import (
    get_guardian_check_interval_seconds,
    get_guardian_entertainment_daily_limit_minutes,
    get_guardian_entertainment_day_start_time,
    get_nudge_prompt,
    is_guardian_mode_enabled,
)
from vision_judge import judge_guardian_screenshot


HARD_BLOCK_CATEGORIES = {"adult", "novel", "manga"}
ENTERTAINMENT_ALLOWED_CATEGORIES = {"game"}


class GuardianManager:
    """Always-on lightweight guard for obvious entertainment distractions."""

    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._break_task: Optional[asyncio.Task] = None
        self._entertainment_task: Optional[asyncio.Task] = None
        self.latest_judgement: Optional[dict] = None
        self.latest_screenshot_path: Optional[str] = None
        self.last_checked_at: Optional[str] = None
        self.pending_break: Optional[dict] = None

    def start(self):
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())
        self._sync_entertainment_timer()

    def stop(self):
        if self._task and not self._task.done():
            self._task.cancel()
        if self._break_task and not self._break_task.done():
            self._break_task.cancel()
        if self._entertainment_task and not self._entertainment_task.done():
            self._entertainment_task.cancel()
        self._task = None
        self._break_task = None
        self._entertainment_task = None

    def get_status(self) -> dict:
        self._finalize_expired_entertainment_if_needed()
        paused_by_session = self._is_session_active()
        enabled = is_guardian_mode_enabled()
        break_status = self._break_status()
        entertainment_status = self._entertainment_status()
        return {
            "enabled": enabled,
            "effective_enabled": bool(enabled and not paused_by_session and not break_status["active"]),
            "paused_by_session": paused_by_session,
            "break_status": break_status,
            "entertainment_status": entertainment_status,
            "check_interval_seconds": get_guardian_check_interval_seconds(),
            "latest_judgement": self.latest_judgement,
            "latest_screenshot_path": self.latest_screenshot_path,
            "latest_screenshot_url": "/guardian/latest-screenshot" if self.latest_screenshot_path else None,
            "last_checked_at": self.last_checked_at,
        }

    async def _loop(self):
        while True:
            interval = get_guardian_check_interval_seconds()
            await asyncio.sleep(interval)
            try:
                self._finalize_expired_entertainment_if_needed()
                if (
                    is_guardian_mode_enabled()
                    and not self._is_session_active()
                    and not self.pending_break
                    and not blocker.is_showing
                ):
                    await self._check_once()
            except Exception as e:
                print(f"[guardian] Error: {e}")

    def _is_session_active(self) -> bool:
        try:
            from session_manager import session_manager
            return bool(session_manager.active)
        except Exception:
            return False

    def return_to_work(self, minimum_next_step: str = ""):
        if self.pending_break:
            self.cancel_break()
        blocker.dismiss()

    def start_break(self, break_minutes: int, minimum_next_step: str) -> dict:
        step = (minimum_next_step or "").strip()
        if not step:
            raise ValueError("请输入休息后要做的最小下一步。")
        if break_minutes <= 0:
            raise ValueError("休息时长需要是正整数。")
        now = datetime.now().astimezone()
        ends_at = now + timedelta(minutes=break_minutes)
        payload = {
            "break_id": str(uuid.uuid4())[:8],
            "task": "Guardian mode",
            "activity": "Guardian 休息",
            "break_minutes": break_minutes,
            "minimum_next_step": step,
            "started_at": now.isoformat(),
            "ends_at": ends_at.isoformat(),
        }
        self.pending_break = payload
        if self._break_task and not self._break_task.done():
            self._break_task.cancel()
        self._break_task = asyncio.create_task(self._break_timer(payload.copy()))
        blocker.dismiss()
        return payload

    def cancel_break(self):
        self.pending_break = None
        if self._break_task and not self._break_task.done():
            self._break_task.cancel()
        self._break_task = None

    def start_entertainment(self, minutes: int) -> dict:
        if self._is_session_active():
            raise ValueError("Session mode is active. Guardian entertainment is unavailable.")
        if self.pending_break:
            raise ValueError("Guardian break is active. End the break before starting entertainment.")
        if blocker.is_showing:
            raise ValueError("A blocker is active. Complete it before starting entertainment.")
        try:
            minutes = int(minutes)
        except Exception:
            raise ValueError("Entertainment duration must be an integer number of minutes.")
        if minutes <= 0:
            raise ValueError("Entertainment duration must be positive.")

        state = self._normalized_state()
        entertainment = state["entertainment"]
        if entertainment.get("active"):
            raise ValueError("Guardian entertainment is already active.")

        limit_seconds = self._daily_limit_seconds()
        if limit_seconds <= 0:
            raise ValueError("Daily entertainment allowance is 0 minutes.")
        requested_seconds = minutes * 60
        remaining_seconds = self._remaining_allowance_seconds(state)
        if requested_seconds > remaining_seconds:
            remaining_minutes = remaining_seconds // 60
            raise ValueError(f"Not enough entertainment allowance left today ({remaining_minutes} minutes remaining).")

        now = datetime.now().astimezone()
        ends_at = now + timedelta(seconds=requested_seconds)
        active = {
            "session_id": str(uuid.uuid4())[:8],
            "started_at": now.isoformat(),
            "ends_at": ends_at.isoformat(),
            "allocated_seconds": requested_seconds,
        }
        entertainment["active"] = active
        self._save_state(state)
        self._sync_entertainment_timer()
        return self._entertainment_status()

    def cancel_entertainment(self, commit_elapsed: bool = True):
        state = self._normalized_state()
        active = state["entertainment"].get("active")
        if active and commit_elapsed:
            state["entertainment"]["used_seconds"] = int(state["entertainment"].get("used_seconds", 0)) + (
                self._active_elapsed_seconds(active)
            )
        state["entertainment"]["active"] = None
        self._save_state(state)
        if self._entertainment_task and not self._entertainment_task.done():
            self._entertainment_task.cancel()
        self._entertainment_task = None

    async def _break_timer(self, payload: dict):
        try:
            seconds = max(1, int(payload["break_minutes"]) * 60)
            if seconds > 5 * 60:
                await asyncio.sleep(seconds - 5 * 60)
                blocker.show_message(
                    "Guardian 休息提醒",
                    "休息时间还剩 5 分钟。请慢慢收尾，准备回到工作。",
                )
                await asyncio.sleep(5 * 60)
            else:
                await asyncio.sleep(seconds)
            self.pending_break = None
            blocker.show_break_end_translation({
                **payload,
                "activity": "Guardian 休息结束",
                "minimum_next_step": payload.get("minimum_next_step", ""),
                "guardian_mode": True,
                "translation_count": 3,
            })
        except asyncio.CancelledError:
            pass

    def _break_status(self) -> dict:
        if not self.pending_break:
            return {"active": False}
        try:
            ends_at = datetime.fromisoformat(self.pending_break["ends_at"])
            remaining = max(0, int((ends_at - datetime.now().astimezone()).total_seconds()))
        except Exception:
            remaining = 0
        return {
            "active": True,
            "remaining_seconds": remaining,
            **self.pending_break,
        }

    async def _entertainment_timer(self, session_id: str, ends_at: str):
        try:
            end_time = datetime.fromisoformat(ends_at)
            seconds = max(1, int((end_time - datetime.now().astimezone()).total_seconds()))
            await asyncio.sleep(seconds)
            self._finish_entertainment_due(session_id=session_id)
        except asyncio.CancelledError:
            pass

    def _sync_entertainment_timer(self):
        state = self._normalized_state()
        active = state["entertainment"].get("active")
        if not active:
            return
        try:
            ends_at = datetime.fromisoformat(active["ends_at"])
        except Exception:
            state["entertainment"]["active"] = None
            self._save_state(state)
            return
        if ends_at <= datetime.now().astimezone():
            self._finish_entertainment_due(session_id=active.get("session_id"))
            return
        if self._entertainment_task and not self._entertainment_task.done():
            return
        self._entertainment_task = asyncio.create_task(
            self._entertainment_timer(active.get("session_id", ""), active["ends_at"])
        )

    def _finalize_expired_entertainment_if_needed(self):
        state = self._normalized_state()
        active = state["entertainment"].get("active")
        if not active:
            return
        try:
            ends_at = datetime.fromisoformat(active["ends_at"])
        except Exception:
            state["entertainment"]["active"] = None
            self._save_state(state)
            return
        if ends_at <= datetime.now().astimezone():
            self._finish_entertainment_due(session_id=active.get("session_id"))

    def _finish_entertainment_due(self, session_id: str = ""):
        state = self._normalized_state()
        active = state["entertainment"].get("active")
        if not active:
            return
        if session_id and active.get("session_id") != session_id:
            return
        state["entertainment"]["used_seconds"] = int(state["entertainment"].get("used_seconds", 0)) + int(
            active.get("allocated_seconds", 0)
        )
        state["entertainment"]["active"] = None
        self._save_state(state)
        if self._entertainment_task and not self._entertainment_task.done():
            self._entertainment_task.cancel()
        self._entertainment_task = None
        if not blocker.is_showing and not self._is_session_active():
            blocker.show_break_end_translation({
                "task": "Guardian mode",
                "activity": "Guardian entertainment ended",
                "minimum_next_step": "Return to work",
                "guardian_mode": True,
                "translation_count": 3,
            })

    def _interrupt_entertainment_for_hard_block(self, result: dict):
        self.cancel_entertainment(commit_elapsed=True)
        if not blocker.is_showing:
            blocker.show(
                task="Guardian mode",
                activity=result.get("current_activity", ""),
                reason=f"Entertainment time still blocks novels, manga/comics, and adult content. {result.get('reason', '')}",
                strict_mode=True,
                nudge_message=get_nudge_prompt(),
                recovery=False,
                recovery_mode="guardian",
                translation_count=3,
            )

    def _entertainment_status(self) -> dict:
        state = self._normalized_state()
        entertainment = state["entertainment"]
        active = entertainment.get("active")
        used_seconds = int(entertainment.get("used_seconds", 0))
        active_elapsed_seconds = self._active_elapsed_seconds(active) if active else 0
        active_remaining_seconds = self._active_remaining_seconds(active) if active else 0
        total_used_seconds = min(self._daily_limit_seconds(), used_seconds + active_elapsed_seconds)
        return {
            "active": bool(active),
            "day_key": entertainment.get("day_key"),
            "daily_limit_minutes": get_guardian_entertainment_daily_limit_minutes(),
            "day_start_time": get_guardian_entertainment_day_start_time(),
            "used_seconds": total_used_seconds,
            "remaining_seconds": max(0, self._daily_limit_seconds() - total_used_seconds),
            "active_remaining_seconds": active_remaining_seconds,
            "active_started_at": active.get("started_at") if active else None,
            "active_ends_at": active.get("ends_at") if active else None,
        }

    def _daily_limit_seconds(self) -> int:
        return max(0, int(get_guardian_entertainment_daily_limit_minutes()) * 60)

    def _remaining_allowance_seconds(self, state: dict) -> int:
        active = state["entertainment"].get("active")
        used_seconds = int(state["entertainment"].get("used_seconds", 0))
        if active:
            used_seconds += self._active_elapsed_seconds(active)
        return max(0, self._daily_limit_seconds() - used_seconds)

    def _active_elapsed_seconds(self, active: Optional[dict]) -> int:
        if not active:
            return 0
        try:
            start = datetime.fromisoformat(active["started_at"])
            end = datetime.fromisoformat(active["ends_at"])
            now = datetime.now().astimezone()
            effective_now = min(max(now, start), end)
            return max(0, int((effective_now - start).total_seconds()))
        except Exception:
            return 0

    def _active_remaining_seconds(self, active: Optional[dict]) -> int:
        if not active:
            return 0
        try:
            ends_at = datetime.fromisoformat(active["ends_at"])
            return max(0, int((ends_at - datetime.now().astimezone()).total_seconds()))
        except Exception:
            return 0

    def _normalized_state(self) -> dict:
        state = self._load_state()
        today_key = self._logical_day_key(datetime.now().astimezone())
        entertainment = state.setdefault("entertainment", {})
        if entertainment.get("day_key") != today_key and not entertainment.get("active"):
            entertainment.clear()
            entertainment.update({"day_key": today_key, "used_seconds": 0, "active": None})
            self._save_state(state)
        entertainment.setdefault("used_seconds", 0)
        entertainment.setdefault("active", None)
        return state

    def _load_state(self) -> dict:
        if GUARDIAN_STATE_FILE.exists():
            try:
                with open(GUARDIAN_STATE_FILE, "r", encoding="utf-8") as f:
                    state = json.load(f)
                if isinstance(state, dict):
                    return state
            except Exception as e:
                print(f"[guardian] Could not read state: {e}")
        return {"entertainment": {"day_key": self._logical_day_key(datetime.now().astimezone()), "used_seconds": 0, "active": None}}

    def _save_state(self, state: dict):
        try:
            GUARDIAN_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(GUARDIAN_STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[guardian] Could not write state: {e}")

    def _logical_day_key(self, now: datetime) -> str:
        start_text = get_guardian_entertainment_day_start_time()
        hour, minute = [int(part) for part in start_text.split(":")]
        day_start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now < day_start:
            return (now.date() - timedelta(days=1)).isoformat()
        return now.date().isoformat()

    async def _check_once(self):
        screenshot_path = self._next_screenshot_path()
        take_screenshot(output_path=screenshot_path)
        result = judge_guardian_screenshot(screenshot_path)
        if result.get("judgement_status") == "api_error":
            self.latest_judgement = result
            self.latest_screenshot_path = screenshot_path
            self.last_checked_at = datetime.now().isoformat()
            self._append_log(result, screenshot_path)
            return

        if "should_interrupt" in result:
            should_interrupt = bool(result.get("should_interrupt"))
        else:
            should_interrupt = not result.get("on_task", True)
        category = str(result.get("trigger_category", "none")).strip().lower()
        entertainment_active = bool(self._entertainment_status().get("active"))
        result["raw_should_interrupt"] = should_interrupt
        result["guardian_entertainment_active"] = entertainment_active

        if entertainment_active and should_interrupt and category not in HARD_BLOCK_CATEGORIES:
            result["should_interrupt"] = False
            result["on_task"] = True
            result["reason"] = (
                "Allowed during Guardian entertainment time. "
                "Novels, manga/comics, and adult content still interrupt."
            )
            should_interrupt = False

        self.latest_judgement = result
        self.latest_screenshot_path = screenshot_path
        self.last_checked_at = datetime.now().isoformat()
        self._append_log(result, screenshot_path)

        if entertainment_active and category in HARD_BLOCK_CATEGORIES and should_interrupt:
            self._interrupt_entertainment_for_hard_block(result)
        elif should_interrupt and not blocker.is_showing:
            blocker.show(
                task="Guardian mode",
                activity=result.get("current_activity", ""),
                reason=result.get("reason", ""),
                strict_mode=True,
                nudge_message=get_nudge_prompt(),
                recovery=True,
                recovery_mode="guardian",
                translation_count=3,
            )

    def _next_screenshot_path(self) -> str:
        now = datetime.now().astimezone()
        day_dir = GUARDIAN_SCREENSHOT_DIR / now.date().isoformat()
        day_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{now.strftime('%H%M%S')}-{uuid.uuid4()}.jpg"
        return str(day_dir / filename)

    def _append_log(self, result: dict, screenshot_path: str):
        now = datetime.now().astimezone().isoformat()
        try:
            try:
                relative_path = str(Path(screenshot_path).resolve().relative_to(GUARDIAN_SCREENSHOT_DIR.parent.resolve()))
            except Exception:
                relative_path = screenshot_path
            entry = {
                "checked_at": now,
                "screenshot_path": relative_path.replace("\\", "/"),
                "should_interrupt": bool(result.get("should_interrupt", not result.get("on_task", True))),
                "trigger_category": result.get("trigger_category", "none"),
                "confidence": result.get("confidence", 0),
                "current_activity": result.get("current_activity", ""),
                "reason": result.get("reason", ""),
                "model": result.get("model", ""),
                "judgement_status": result.get("judgement_status", "ok"),
            }
            GUARDIAN_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(GUARDIAN_LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[guardian] Could not write log: {e}")


guardian_manager = GuardianManager()
