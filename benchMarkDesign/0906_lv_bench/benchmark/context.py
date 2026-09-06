from __future__ import annotations

import json
from pathlib import Path

from .schema import VALID_MODES, VALID_SPLITS, normalize_supervision_level

DEFAULT_CONTEXT = {
    "mode": "guardian",
    "task": "",
    "supervision_level": "",
    "activity": "",
    "human_reason": "",
    "split": "train",
    "ai_label": "",
    "ai_reason": "",
    "ai_model": "",
    "prompt_version": "",
    "retriever_version": "",
    "source_type": "manual_seed",
    "review_status": "reviewed",
}


class ContextStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> dict:
        result = dict(DEFAULT_CONTEXT)
        if self.path.is_file():
            try:
                value = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    result.update({key: value.get(key, result[key]) for key in result})
            except Exception:
                pass
        if result["mode"] not in VALID_MODES:
            result["mode"] = "guardian"
        if result["split"] not in VALID_SPLITS:
            result["split"] = "train"
        if result["mode"] == "guardian":
            result["task"] = ""
        try:
            result["supervision_level"] = normalize_supervision_level(result.get("supervision_level")) or ""
        except ValueError:
            result["supervision_level"] = ""
        return result

    def save(self, update: dict) -> dict:
        context = self.load()
        for key in DEFAULT_CONTEXT:
            if key in update:
                value = update[key]
                context[key] = value.strip() if isinstance(value, str) else value
        if context["mode"] not in VALID_MODES:
            raise ValueError(f"Unsupported mode: {context['mode']}")
        if context["split"] not in VALID_SPLITS:
            raise ValueError(f"Unsupported split: {context['split']}")
        if context["mode"] == "guardian":
            context["task"] = ""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(context, ensure_ascii=False, indent=2), encoding="utf-8")
        return context
