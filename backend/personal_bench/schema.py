from __future__ import annotations

from typing import Optional

VALID_MODES = {"guardian", "session"}
VALID_SPLITS = {"train", "test"}
GUARDIAN_LABELS = {"allow", "interrupt", "ambiguous"}
SESSION_LABELS = {"on_task", "off_task", "ambiguous"}
VALID_LABELS = GUARDIAN_LABELS | SESSION_LABELS


def judge_label_for(mode: str, label: str) -> str:
    """Map 0906 activity labels and legacy binary labels to the live judge vocabulary."""
    mode = (mode or "").strip().lower()
    raw = (label or "").strip().lower()
    allowish = {"allow", "on_task", "ontask", "process"}
    interruptish = {"interrupt", "off_task", "entertainment"}
    if raw == "not_entertainment_but_notfocus":
        return "allow" if mode == "guardian" else "off_task"
    if raw in allowish:
        return "allow" if mode == "guardian" else "on_task"
    if raw in interruptish:
        return "interrupt" if mode == "guardian" else "off_task"
    if mode == "guardian":
        return raw if raw in GUARDIAN_LABELS else "allow"
    return raw if raw in SESSION_LABELS else "on_task"


def normalize_label_for_mode(mode: str, label: str) -> str:
    """Validate label for mode; raise ValueError if incompatible."""
    mode = (mode or "").strip().lower()
    label = (label or "").strip().lower()
    if mode not in VALID_MODES:
        raise ValueError(f"Unsupported mode: {mode}")
    allowed = GUARDIAN_LABELS if mode == "guardian" else SESSION_LABELS
    if label not in allowed:
        raise ValueError(f"Label {label!r} not allowed for mode {mode}. Allowed: {sorted(allowed)}")
    return label


def ai_outcome_to_label(mode: str, entry: dict) -> Optional[str]:
    """Map a raw log / judgement dict to a normalized AI label."""
    mode = (mode or "").strip().lower()
    if mode == "guardian":
        if "should_interrupt" in entry:
            return "interrupt" if entry.get("should_interrupt") else "allow"
        if "on_task" in entry:
            return "allow" if entry.get("on_task") else "interrupt"
        return None
    if "on_task" in entry:
        return "on_task" if entry.get("on_task") else "off_task"
    return None


def labels_match(human: str, predicted: str) -> bool:
    """Exact match; ambiguous never counts as correct for accuracy."""
    human = (human or "").strip().lower()
    predicted = (predicted or "").strip().lower()
    if human == "ambiguous" or predicted == "ambiguous":
        return False
    return human == predicted and human in VALID_LABELS
