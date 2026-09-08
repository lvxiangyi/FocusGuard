"""MVP API: authoritative history feedback and interruption-bound challenges."""
import threading
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Literal

from session_manager import session_manager
from settings_manager import get_settings_payload, load_settings
from personal_bench.recent import load_recent_judgments
from personal_bench.store import BenchStore
from personal_bench.capture_context import load_pending_capture, commit_pending_capture
from mvp_i18n import LANGUAGES, text
from quiz_generator import grade_translation_answer, explain_translation, TRANSLATION_CHALLENGES

router = APIRouter(prefix="/mvp")


@router.get("/labels")
def labels():
    return {key: text(key) for key in ("pending", "onTask", "offTask")}


class RecoveryStore:
    """Bind the selected recovery action to one active interruption."""
    def __init__(self, manager):
        self.manager = manager
        self.current = None
        self.lock = threading.RLock()

    def block_key(self):
        if not self.manager.active or not self.manager.should_block:
            raise ValueError("No active interruption")
        return (self.manager.session_id, self.manager.block_id)

    def get(self):
        with self.lock:
            key = self.block_key()
            if self.current and self.current["block_key"] == key:
                return self.current.copy()
            mode = load_settings().get("recovery_mode", "quick_return")
            if mode not in {"quick_return", "next_step", "translation"}:
                mode = "quick_return"
            self.current = {
                "recovery_id": uuid.uuid4().hex,
                "block_key": key,
                "mode": mode,
            }
            return self.current.copy()

    def finish(self, recovery_id, next_step=""):
        with self.lock:
            recovery = self.get()
            if recovery["recovery_id"] != recovery_id:
                raise ValueError("This interruption has expired")
            mode = recovery["mode"]
            if mode == "translation":
                raise ValueError("Complete the translation first")
            step = (next_step or "").strip()
            if mode == "next_step" and not step:
                raise ValueError("Write the next action first")
            self.manager.record_recovery_action(mode, step)
            self.manager.acknowledge_block()
            self.current = None


recoveries = RecoveryStore(session_manager)


class ChallengeStore:
    """Only the active block's server-issued sentence can be graded/unlocked."""
    def __init__(self, manager):
        self.manager = manager
        self.current = None
        self.lock = threading.RLock()
        self.cursor = 0

    def block_key(self):
        if not self.manager.active or not self.manager.should_block:
            raise ValueError("No active interruption")
        return (self.manager.session_id, self.manager.block_id)

    def get(self, replace=False):
        with self.lock:
            key = self.block_key()
            if self.current and self.current["block_key"] == key and not replace:
                return self.current.copy()
            settings = load_settings()
            target = settings.get("practice_target_language", "Japanese")
            code = next((k for k, v in LANGUAGES.items() if v == target), "ja")
            source = "zh" if code == "en" else "en"
            bank = TRANSLATION_CHALLENGES if source == "en" else [
                "我会先完成一个小步骤。", "我会把注意力带回当前任务。",
                "清晰的计划让工作更容易。", "每天的一点努力都很重要。", "完成任务后，我会休息一下。",
            ]
            index = self.cursor % len(bank)
            self.cursor += 1
            self.current = {
                "challenge_id": uuid.uuid4().hex, "block_key": key,
                "source_text": bank[index],
                "source_language": source, "target_language": LANGUAGES[code],
                "source": "mvp-built-in", "source_name": "FocusGuard",
                "accepted": False, "skipped": False,
            }
            return self.current.copy()

    def require(self, challenge_id):
        if not self.current or self.current["challenge_id"] != challenge_id or self.current["block_key"] != self.block_key():
            raise ValueError("This interruption has expired")
        return self.current

    def grade(self, challenge_id, answer, skip=False):
        with self.lock:
            challenge = self.require(challenge_id)
            if challenge["skipped"]:
                raise ValueError("Request a new sentence after viewing the answer")
            if skip:
                result = explain_translation(challenge["source_text"], challenge["target_language"], challenge=challenge)
            else:
                result = grade_translation_answer(challenge["source_text"], answer, challenge["target_language"], challenge=challenge)
            # Stop/start may have occurred while the model was responding.
            self.require(challenge_id)
            if result.get("model") in {"api-error", "local-fallback"}:
                raise RuntimeError(text("gradingError"))
            challenge["result"] = result
            challenge["skipped"] = skip
            challenge["accepted"] = not skip and result.get("accepted") is True
            return result

    def finish(self, challenge_id):
        with self.lock:
            challenge = self.require(challenge_id)
            if not challenge["accepted"] or challenge["skipped"]:
                raise ValueError("Complete the translation first")
            self.manager.record_recovery_action("translation")
            self.manager.acknowledge_block()
            self.current = None


challenges = ChallengeStore(session_manager)


def recent_records():
    return [r for r in load_recent_judgments(limit=50, mode="session") if r["mode"] == "session"]


def save_feedback(record, label, reason):
    from data_paths import DATA_DIR
    if not reason.strip():
        raise ValueError("Please add context")
    path = Path(record["screenshot_path"]).resolve()
    if not path.is_relative_to(Path(DATA_DIR).resolve()) or not path.is_file():
        raise ValueError("Screenshot unavailable")
    sample = BenchStore().add_sample(
        mode="session", human_label=label, source_image=path, split="train",
        task=record["task"], human_reason=reason.strip(),
        supervision_level=record.get("supervision_level"),
        ai_activity=record.get("ai_activity", ""), ai_reason=record.get("ai_reason", ""),
        ai_label=record.get("ai_label", ""), captured_at=record.get("captured_at"), source="user_feedback",
    )

    session_manager.invalidate_judgement_cache()
    return sample


@router.get("/overview")
def overview():
    return {"status": session_manager.get_status(), "settings": get_settings_payload(),
            "recent": recent_records(), "samples": [s for s in BenchStore().list_samples("train") if s["mode"] == "session"],
            "pending": load_pending_capture()}


class StopRequest(BaseModel):
    session_id: str


@router.post("/stop")
async def stop(req: StopRequest):
    if req.session_id != session_manager.session_id:
        raise HTTPException(409, "Session changed; refresh first")
    session_manager.stop_session()
    return {"status": "stopped"}


class FeedbackRequest(BaseModel):
    record_id: str
    label: Literal["on_task", "off_task"]
    reason: str = Field(min_length=1, max_length=500)


@router.post("/feedback")
def feedback(req: FeedbackRequest):
    record = next((r for r in recent_records() if r["id"] == req.record_id), None)
    if not record:
        raise HTTPException(404, "Record unavailable; refresh first")
    try:
        return {"sample": save_feedback(record, req.label, req.reason)}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


class PendingFeedback(BaseModel):
    captured_at: str
    task: str = Field(min_length=1, max_length=500)
    label: Literal["on_task", "off_task"]
    reason: str = Field(min_length=1, max_length=500)


@router.post("/pending-feedback")
def pending_feedback(req: PendingFeedback):
    if not req.task.strip() or not req.reason.strip():
        raise HTTPException(400, "Task and context cannot be empty")
    pending = load_pending_capture()
    if not pending or pending.get("captured_at") != req.captured_at:
        raise HTTPException(409, "Pending screenshot changed; refresh first")
    # Existing capture API's verdict means desired label (对/错), not agreement with AI.
    try:
        sample = commit_pending_capture(verdict="对" if req.label == "on_task" else "错",
            context={"mode": "session", "task": req.task.strip(), "note": req.reason.strip(), "split": "train"})
        session_manager.invalidate_judgement_cache()
        return {"sample": sample}
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


class ChallengeRequest(BaseModel):
    challenge_id: str
    answer: str = Field(default="", max_length=2000)


class RecoveryRequest(BaseModel):
    recovery_id: str
    next_step: str = Field(default="", max_length=500)


def call_challenge(fn, *args):
    try:
        return fn(*args)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from e


@router.get("/recovery")
def recovery():
    return call_challenge(recoveries.get)


@router.post("/recovery/finish")
async def finish_recovery(req: RecoveryRequest):
    # Keep completion serialized with session replacement on the event loop.
    call_challenge(recoveries.finish, req.recovery_id, req.next_step)
    return {"status": "acknowledged"}


def require_translation_recovery():
    if recoveries.get()["mode"] != "translation":
        raise HTTPException(409, "Translation is not the selected recovery mode")


@router.get("/challenge")
def challenge():
    require_translation_recovery()
    return call_challenge(challenges.get)


@router.post("/challenge/next")
def next_challenge(req: ChallengeRequest):
    require_translation_recovery()
    with challenges.lock:
        call_challenge(challenges.require, req.challenge_id)
        return call_challenge(challenges.get, True)


@router.post("/challenge/grade")
def grade(req: ChallengeRequest):
    require_translation_recovery()
    return call_challenge(challenges.grade, req.challenge_id, req.answer)


@router.post("/challenge/explain")
def explain(req: ChallengeRequest):
    require_translation_recovery()
    return call_challenge(challenges.grade, req.challenge_id, "", True)


@router.post("/challenge/finish")
async def finish(req: ChallengeRequest):
    # Run on the event loop so completion and starting a new session cannot interleave.
    require_translation_recovery()
    call_challenge(challenges.finish, req.challenge_id)
    return {"status": "acknowledged"}
