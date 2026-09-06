from __future__ import annotations

VALID_MODES = {"guardian", "session"}
VALID_SPLITS = {"train", "test"}
VALID_SOURCE_TYPES = {"manual_seed", "ai_correction", "history_import"}
VALID_REVIEW_STATUSES = {"pending", "reviewed"}
VALID_LABELS = {
    "ontask",
    "process",
    "entertainment",
    "not_entertainment_but_notFocus",
    "ambiguous",
}
SESSION_INTERRUPT_LABELS = {"entertainment", "not_entertainment_but_notFocus"}
GUARDIAN_INTERRUPT_LABELS = {"entertainment"}
LEGACY_LABELS = {
    "allow": "ontask",
    "on_task": "ontask",
    "task_related": "ontask",
    "interrupt": "entertainment",
    "off_task": "entertainment",
    "offtask": "entertainment",
    "off-task": "entertainment",
    "not_entertainment": "not_entertainment_but_notFocus",
}


def canonicalize_label(label: str) -> str:
    value = (label or "").strip()
    if not value:
        return "ambiguous"
    value = LEGACY_LABELS.get(value, LEGACY_LABELS.get(value.lower(), value))
    if value not in VALID_LABELS:
        raise ValueError(
            f"Unsupported label: {label!r}. "
            f"Allowed: {sorted(VALID_LABELS)}"
        )
    return value


def normalize_label(mode: str, label: str) -> str:
    mode = (mode or "").strip().lower()
    if mode not in VALID_MODES:
        raise ValueError(f"Unsupported mode: {mode}")
    return canonicalize_label(label)


def normalize_split(split: str) -> str:
    split = (split or "").strip().lower()
    if split not in VALID_SPLITS:
        raise ValueError(f"Unsupported split: {split}")
    return split


def normalize_source_type(source_type: str) -> str:
    source_type = (source_type or "").strip().lower()
    if source_type not in VALID_SOURCE_TYPES:
        raise ValueError(f"Unsupported source_type: {source_type}")
    return source_type


def normalize_review_status(review_status: str) -> str:
    review_status = (review_status or "").strip().lower()
    if review_status not in VALID_REVIEW_STATUSES:
        raise ValueError(f"Unsupported review_status: {review_status}")
    return review_status


def normalize_supervision_level(supervision_level: str | None) -> str | None:
    if not (supervision_level or "").strip():
        return None
    label = canonicalize_label(supervision_level)
    return None if label == "ambiguous" else label


def coerce_human_label(mode: str, ai_label: str = "", human_label: str = "") -> str:
    if (human_label or "").strip():
        return normalize_label(mode, human_label)
    if (ai_label or "").strip():
        return normalize_label(mode, ai_label)
    return "ambiguous"


def should_interrupt(mode: str, label: str) -> bool:
    mode = (mode or "").strip().lower()
    try:
        activity = canonicalize_label(label)
    except ValueError:
        return False
    if mode == "guardian":
        return activity in GUARDIAN_INTERRUPT_LABELS
    if mode == "session":
        return activity in SESSION_INTERRUPT_LABELS
    return False
