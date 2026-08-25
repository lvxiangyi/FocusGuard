from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from personal_bench.schema import ai_outcome_to_label


def default_aimonitor_data_root() -> Path:
    try:
        from data_paths import DATA_DIR
        return Path(DATA_DIR)
    except Exception:
        return Path(__file__).resolve().parent.parent.parent / "data" / "dev"


def _read_jsonl_tail(path: Path, limit: int) -> list[dict]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
        if len(out) >= limit:
            break
    return out


def _resolve_screenshot(data_root: Path, raw_path: str, mode: str) -> Optional[Path]:
    if not raw_path:
        return None
    p = Path(raw_path)
    if p.is_file():
        return p.resolve()

    candidates = [
        data_root / raw_path,
        data_root / "guardian" / raw_path,
        data_root / "screenshots" / Path(raw_path).name,
    ]
    if mode == "guardian":
        candidates.insert(0, data_root / "guardian" / raw_path)
        if raw_path.replace("\\", "/").startswith("screenshots/"):
            candidates.insert(0, data_root / "guardian" / raw_path)

    for c in candidates:
        try:
            if c.is_file():
                return c.resolve()
        except OSError:
            continue
    return None


def load_recent_judgments(limit: int = 10, data_root: Optional[Path] = None) -> list[dict]:
    """Merge guardian + session logs, newest first."""
    data_root = Path(data_root) if data_root else default_aimonitor_data_root()
    guardian_logs = _read_jsonl_tail(data_root / "guardian" / "guardian_logs.jsonl", limit * 3)
    session_logs = _read_jsonl_tail(data_root / "logs" / "session_logs.jsonl", limit * 3)

    merged: list[dict] = []
    for entry in guardian_logs:
        captured = entry.get("checked_at") or entry.get("timestamp") or ""
        screenshot = _resolve_screenshot(data_root, entry.get("screenshot_path") or "", "guardian")
        ai_label = ai_outcome_to_label("guardian", entry)
        item_id = f"guardian:{captured}:{entry.get('screenshot_path') or ''}"
        merged.append(
            {
                "id": item_id,
                "mode": "guardian",
                "task": "",
                "captured_at": captured,
                "ai_activity": entry.get("current_activity") or "",
                "ai_reason": entry.get("reason") or "",
                "ai_label": ai_label or "",
                "ai_confidence": entry.get("confidence"),
                "judgement_status": entry.get("judgement_status") or "ok",
                "screenshot_path": str(screenshot) if screenshot else "",
                "screenshot_available": bool(screenshot),
                "source": "guardian_log",
                "supervision_level": None,
                "suggested_human_label": ai_label or "allow",
            }
        )

    for entry in session_logs:
        captured = entry.get("timestamp") or ""
        screenshot = _resolve_screenshot(data_root, entry.get("screenshot_path") or "", "session")
        ai_label = ai_outcome_to_label("session", entry)
        item_id = f"session:{captured}:{entry.get('screenshot_path') or ''}"
        merged.append(
            {
                "id": item_id,
                "mode": "session",
                "task": entry.get("task") or "",
                "captured_at": captured,
                "ai_activity": entry.get("current_activity") or "",
                "ai_reason": entry.get("reason") or "",
                "ai_label": ai_label or "",
                "ai_confidence": entry.get("confidence"),
                "judgement_status": entry.get("judgement_status") or "ok",
                "screenshot_path": str(screenshot) if screenshot else "",
                "screenshot_available": bool(screenshot),
                "source": "session_log",
                "supervision_level": entry.get("supervision_level"),
                "suggested_human_label": ai_label or "on_task",
            }
        )

    merged.sort(key=lambda x: x.get("captured_at") or "", reverse=True)
    with_img = [m for m in merged if m["screenshot_available"]]
    without = [m for m in merged if not m["screenshot_available"]]
    return (with_img + without)[:limit]
