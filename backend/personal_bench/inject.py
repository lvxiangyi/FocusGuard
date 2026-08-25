from __future__ import annotations

from typing import Iterable


def format_precedents_block(hits: Iterable[dict], max_items: int = 3) -> str:
    """Format retrieved train cases for prompt injection. Empty if no hits."""
    items = list(hits)[:max_items]
    if not items:
        return ""

    lines = [
        "User-labeled similar past cases (personal calibration). "
        "Follow each case's human_label. Labels may be allow or interrupt, on_task or off_task. "
        "These are not automatic exceptions or whitelist entries.",
    ]
    for i, hit in enumerate(items, start=1):
        mode = hit.get("mode", "")
        label = hit.get("human_label", "")
        task = hit.get("task") or "(none — guardian)"
        activity = hit.get("ai_activity") or hit.get("human_reason") or ""
        reason = hit.get("human_reason") or ""
        score = hit.get("retrieval_score")
        score_txt = f", similarity={score}" if score is not None else ""
        lines.append(
            f"{i}) mode={mode}, task={task}, human_label={label}{score_txt}\n"
            f"   observed_activity: {activity}\n"
            f"   user_reason: {reason}"
        )
    return "\n".join(lines)


def inject_into_prompt(base_prompt: str, hits: Iterable[dict], max_items: int = 3) -> str:
    block = format_precedents_block(hits, max_items=max_items)
    if not block:
        return base_prompt
    return f"{base_prompt.rstrip()}\n\n{block}\n"
