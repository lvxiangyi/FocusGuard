from __future__ import annotations

from typing import Optional

HARD_BLOCK_CATEGORIES = {"adult", "novel", "manga"}

# Known expansions so short Chinese items can match English AI activity text.
WHITELIST_ALIASES = {
    "听音乐": (
        "听音乐",
        "听歌",
        "spotify",
        "youtube music",
        "apple music",
        "amazon music",
        "网易云",
        "qq音乐",
        "qq music",
        "musescore",
        "soundcloud",
        "listen to music",
        "listening to music",
        "music player",
        "web-based music player",
    ),
}


def _needles_for(item: str) -> list[str]:
    text = (item or "").strip()
    if not text:
        return []
    aliases = WHITELIST_ALIASES.get(text) or WHITELIST_ALIASES.get(text.casefold()) or ()
    needles = [text, *aliases]
    seen = set()
    unique = []
    for needle in needles:
        key = needle.casefold()
        if len(key) < 2 or key in seen:
            continue
        seen.add(key)
        unique.append(needle)
    return unique


def match_whitelist(text: str, behaviors: Optional[list] = None) -> Optional[str]:
    if behaviors is None:
        from settings_manager import get_whitelist_behaviors
        behaviors = get_whitelist_behaviors()
    haystack = " ".join((text or "").split()).casefold()
    if not haystack:
        return None
    for item in behaviors or []:
        for needle in _needles_for(str(item)):
            if needle.casefold() in haystack:
                return str(item).strip()
    return None


def apply_whitelist_override(result: dict, behaviors: Optional[list] = None) -> dict:
    """Force on-task when the judged activity matches a user whitelist item."""
    if not isinstance(result, dict):
        return result
    if result.get("judgement_status") == "api_error":
        return result
    category = str(result.get("trigger_category") or "").strip().lower()
    if category in HARD_BLOCK_CATEGORIES:
        return result

    haystack = " ".join(
        str(result.get(key) or "")
        for key in ("current_activity", "activity", "reason", "window_title")
    )
    hit = match_whitelist(haystack, behaviors)
    if not hit:
        return result

    updated = dict(result)
    updated["on_task"] = True
    updated["should_interrupt"] = False
    updated["whitelist_hit"] = hit
    updated["whitelist_override"] = True
    reason = str(updated.get("reason") or "").strip()
    prefix = f"Whitelist override ({hit})."
    if prefix not in reason:
        updated["reason"] = f"{prefix} {reason}".strip()
    return updated
