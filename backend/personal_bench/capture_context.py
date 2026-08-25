"""Hotkey screenshot first, then attach context on commit."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from data_paths import PERSONAL_BENCH_DIR
from personal_bench.schema import VALID_MODES, VALID_SPLITS, normalize_label_for_mode
from personal_bench.store import BenchStore

CAPTURE_CONTEXT_FILE = PERSONAL_BENCH_DIR / "capture_context.json"
PENDING_DIR = PERSONAL_BENCH_DIR / "pending"
PENDING_IMAGE = PENDING_DIR / "capture.jpg"
PENDING_META = PENDING_DIR / "capture.json"

DEFAULT_CONTEXT = {
    "mode": "guardian",
    "task": "",
    "supervision_level": None,
    "activity": "",
    "note": "",
    "split": "train",
}


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def normalize_verdict(verdict: str) -> str:
    verdict = (verdict or "").strip().lower()
    if verdict in {"对", "correct", "right", "ok", "1", "true", "yes"}:
        return "对"
    if verdict in {"错", "wrong", "incorrect", "2", "false", "no"}:
        return "错"
    raise ValueError("verdict must be 对/错 (or correct/wrong)")


def binary_label_for_mode(mode: str, verdict: str) -> str:
    mode = (mode or "").strip().lower()
    positive = normalize_verdict(verdict) == "对"
    if mode == "guardian":
        return "allow" if positive else "interrupt"
    if mode == "session":
        return "on_task" if positive else "off_task"
    raise ValueError(f"Unsupported mode: {mode}")


def load_capture_context() -> dict:
    PERSONAL_BENCH_DIR.mkdir(parents=True, exist_ok=True)
    if not CAPTURE_CONTEXT_FILE.exists():
        return dict(DEFAULT_CONTEXT)
    try:
        data = json.loads(CAPTURE_CONTEXT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return dict(DEFAULT_CONTEXT)
    out = dict(DEFAULT_CONTEXT)
    if isinstance(data, dict):
        out.update({k: data.get(k, out[k]) for k in DEFAULT_CONTEXT})
    mode = str(out.get("mode") or "guardian").strip().lower()
    out["mode"] = mode if mode in VALID_MODES else "guardian"
    split = str(out.get("split") or "train").strip().lower()
    out["split"] = split if split in VALID_SPLITS else "train"
    if out["mode"] == "guardian":
        out["task"] = ""
    return out


def save_capture_context(update: dict) -> dict:
    """Persist last-used form defaults. Task is validated only at commit."""
    current = load_capture_context()
    if not isinstance(update, dict):
        raise ValueError("context must be an object")
    for key in DEFAULT_CONTEXT:
        if key in update:
            current[key] = update[key]
    mode = str(current.get("mode") or "guardian").strip().lower()
    if mode not in VALID_MODES:
        raise ValueError(f"Unsupported mode: {mode}")
    current["mode"] = mode
    split = str(current.get("split") or "train").strip().lower()
    if split not in VALID_SPLITS:
        raise ValueError(f"Unsupported split: {split}")
    current["split"] = split
    current["task"] = (current.get("task") or "").strip()
    current["activity"] = (current.get("activity") or "").strip()
    current["note"] = (current.get("note") or "").strip()
    level = current.get("supervision_level")
    current["supervision_level"] = (str(level).strip() if level else None) or None
    if mode == "guardian":
        current["task"] = ""
    CAPTURE_CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)
    CAPTURE_CONTEXT_FILE.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def _pending_payload(meta: dict) -> dict:
    return {
        "verdict": meta.get("verdict"),
        "captured_at": meta.get("captured_at"),
        "replaced": bool(meta.get("replaced")),
        "image_url": "/personal-bench/pending-capture/image",
    }


def load_pending_capture() -> Optional[dict]:
    if not PENDING_IMAGE.exists():
        return None
    meta: dict = {}
    if PENDING_META.exists():
        try:
            data = json.loads(PENDING_META.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                if data.get("committed"):
                    return None
                meta = data
        except Exception:
            meta = {}
    captured = meta.get("captured_at")
    if not captured:
        captured = datetime.fromtimestamp(PENDING_IMAGE.stat().st_mtime).astimezone().isoformat()
    verdict = meta.get("verdict")
    if verdict not in {"对", "错"}:
        verdict = None
    return _pending_payload({
        "verdict": verdict,
        "captured_at": captured,
        "replaced": bool(meta.get("replaced")),
    })


def discard_pending_capture() -> None:
    for path in (PENDING_IMAGE, PENDING_META):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
    if PENDING_IMAGE.exists():
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        PENDING_META.write_text(
            json.dumps({"committed": True, "captured_at": _now()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def set_pending_verdict(verdict: str) -> dict:
    pending = load_pending_capture()
    if not pending:
        raise ValueError("没有待保存的截图。请先截图。")
    verdict_norm = normalize_verdict(verdict)
    meta = {
        "verdict": verdict_norm,
        "captured_at": pending.get("captured_at") or _now(),
        "replaced": False,
    }
    PENDING_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return _pending_payload(meta)


def take_pending_capture(verdict: Optional[str] = None) -> dict:
    """Screenshot immediately. Context is attached later on commit."""
    from screenshot import take_screenshot

    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    previous_verdict = None
    if PENDING_META.exists():
        try:
            old = json.loads(PENDING_META.read_text(encoding="utf-8"))
            value = (old or {}).get("verdict")
            if value in {"对", "错"}:
                previous_verdict = value
        except Exception:
            previous_verdict = None
    replaced = PENDING_META.exists() and PENDING_IMAGE.exists()
    take_screenshot(output_path=str(PENDING_IMAGE))
    if not PENDING_IMAGE.exists():
        raise RuntimeError("Screenshot failed.")

    if verdict:
        verdict_norm = normalize_verdict(verdict)
    else:
        verdict_norm = previous_verdict
    meta = {
        "verdict": verdict_norm,
        "captured_at": _now(),
        "replaced": replaced,
    }
    PENDING_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return _pending_payload(meta)


def commit_pending_capture(verdict: Optional[str] = None, context: Optional[dict] = None) -> dict:
    pending = load_pending_capture()
    if not pending:
        raise ValueError("没有待保存的截图。请先截图。")
    if not PENDING_IMAGE.exists():
        raise ValueError("待保存截图已丢失，请重新截图。")

    ctx = save_capture_context(context) if context else load_capture_context()
    if ctx["mode"] == "session" and not ctx.get("task"):
        raise ValueError("Session mode requires a non-empty task.")

    chosen = verdict or pending.get("verdict")
    if not chosen:
        raise ValueError("请选择对或错。")
    label = normalize_label_for_mode(ctx["mode"], binary_label_for_mode(ctx["mode"], chosen))

    store = BenchStore()
    sample = store.add_sample(
        mode=ctx["mode"],
        human_label=label,
        source_image=PENDING_IMAGE,
        split=ctx.get("split") or "train",
        task=ctx.get("task") or "",
        supervision_level=ctx.get("supervision_level"),
        human_reason=ctx.get("note") or "",
        ai_activity=ctx.get("activity") or "",
        ai_reason="",
        ai_label="",
        captured_at=pending.get("captured_at"),
        source="hotkey",
    )
    save_capture_context({
        "mode": ctx["mode"],
        "task": ctx.get("task") or "",
        "supervision_level": ctx.get("supervision_level"),
        "activity": "",
        "note": "",
        "split": ctx.get("split") or "train",
    })
    discard_pending_capture()
    sample["screenshot_url"] = f"/personal-bench/samples/{sample['id']}/image"
    sample["verdict"] = "对" if label in {"on_task", "allow"} else "错"
    return sample
