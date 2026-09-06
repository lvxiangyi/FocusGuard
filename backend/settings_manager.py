import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

from data_paths import DATA_DIR, PROJECT_ROOT


SETTINGS_FILE = DATA_DIR / "settings.json"
DEFAULT_PRACTICE_FILE = PROJECT_ROOT.parent / "document" / "0718_Practice.md"

MODEL_OPTIONS: List[Dict[str, str]] = [
    {
        "id": "qwen/qwen3.7-flash",
        "label": "Qwen 3.7 Flash（OpenRouter）",
        "description": "经 OpenRouter 调用。便宜的视觉模型，适合截图监测。",
    },
    {
        "id": "z-ai/glm-5.3-flash",
        "label": "GLM 5.3 Flash（OpenRouter）",
        "description": "经 OpenRouter 调用。便宜多模态，智谱节点较多。",
    },
    {
        "id": "qwen/qwen3.8-flash",
        "label": "Qwen 3.8 Flash（OpenRouter）",
        "description": "经 OpenRouter 调用。稍强的视觉理解，仍较便宜。",
    },
    {
        "id": "minimax/minimax-m3",
        "label": "MiniMax M3（OpenRouter）",
        "description": "经 OpenRouter 调用。多模态更细，稍慢更贵。",
    },
    {
        "id": "deepseek/deepseek-v4-flash-vision-exp",
        "label": "DeepSeek V4 Flash Vision（OpenRouter）",
        "description": "经 OpenRouter 调用。便宜，但可能被隐私策略拦住。",
    },
    {
        "id": "deepseek-v4-flash-vision-exp",
        "label": "DeepSeek V4 Flash Vision（官方 API）",
        "description": "直连 platform.deepseek.com。需要 DEEPSEEK_API_KEY。",
    },
    {
        "id": "google/gemini-2.5-flash-lite",
        "label": "Gemini 2.5 Flash-Lite（OpenRouter）",
        "description": "经 OpenRouter 调用。更快，国内有时地区不可用。",
    },
    {
        "id": "openai/gpt-4o-mini",
        "label": "GPT-4o mini（OpenRouter）",
        "description": "经 OpenRouter 调用。适合文本题，看图更贵。",
    },
]

SUPERVISION_LEVEL_OPTIONS: List[Dict[str, str]] = [
    {
        "id": "task_related",
        "label": "必须和任务强相关",
        "description": "Session mode: only clearly task-related work is accepted. User-defined whitelist behaviors are accepted unless they are hard-blocked content.",
    },
    {
        "id": "not_entertainment",
        "label": "不是明显娱乐即可",
        "description": "Session mode: general productivity, learning, reading, writing, and research are accepted. User-defined whitelist behaviors are accepted unless they are hard-blocked content.",
    },
]

DEFAULT_NUDGE_PROMPT = (
    "先和冲动保持一点距离：你不是这个念头本身，只是在看见一个念头。"
    "请做一个最小下一步，或者明确休息多久后回来。"
)

DEFAULT_SETTINGS = {
    "model": "qwen/qwen3.7-flash",
    "ui_language": "zh",
    "strict_mode_enabled": True,
    "strict_locked_until": None,
    "supervision_level": "not_entertainment",
    "nudge_prompt": DEFAULT_NUDGE_PROMPT,
    "default_check_interval_seconds": 300,
    "trigger_threshold": 1,
    "whitelist_behaviors": ["听音乐"],
    "guardian_mode_enabled": True,
    "guardian_check_interval_seconds": 300,
    "guardian_entertainment_daily_limit_minutes": 60,
    "guardian_entertainment_day_start_time": "04:00",
    "guardian_rest_quota_per_day": 3,
    "guardian_rest_quota_pending": None,
    "guardian_rest_quota_pending_day": None,
    "practice_source_path": str(DEFAULT_PRACTICE_FILE),
    "practice_target_language": "Japanese",
    "post_block_cooldown_seconds": 300,
    "dataset_tag_options": ["guardian mode"],
    "dataset_retention_days": None,
}


def _valid_model_ids() -> set:
    return {model["id"] for model in MODEL_OPTIONS}


def _valid_supervision_level_ids() -> set:
    return {level["id"] for level in SUPERVISION_LEVEL_OPTIONS}


def load_settings() -> dict:
    settings = DEFAULT_SETTINGS.copy()

    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                settings.update(saved)
        except Exception as e:
            print(f"[settings] Could not read settings, using defaults: {e}")

    if settings.get("ui_language") not in {"zh", "en", "ja", "ko", "fr", "pt"}:
        settings["ui_language"] = "zh"

    if settings.get("model") not in _valid_model_ids():
        settings["model"] = DEFAULT_SETTINGS["model"]

    if settings.get("supervision_level") not in _valid_supervision_level_ids():
        settings["supervision_level"] = DEFAULT_SETTINGS["supervision_level"]

    if not isinstance(settings.get("nudge_prompt"), str) or not settings.get("nudge_prompt").strip():
        settings["nudge_prompt"] = DEFAULT_SETTINGS["nudge_prompt"]

    try:
        settings["default_check_interval_seconds"] = max(5, int(settings.get("default_check_interval_seconds", 300)))
    except Exception:
        settings["default_check_interval_seconds"] = DEFAULT_SETTINGS["default_check_interval_seconds"]

    try:
        settings["trigger_threshold"] = max(1, int(settings.get("trigger_threshold", 1)))
    except Exception:
        settings["trigger_threshold"] = DEFAULT_SETTINGS["trigger_threshold"]

    settings["whitelist_behaviors"] = _normalize_string_list(settings.get("whitelist_behaviors", []))
    if not settings["whitelist_behaviors"]:
        settings["whitelist_behaviors"] = DEFAULT_SETTINGS["whitelist_behaviors"].copy()

    settings["dataset_tag_options"] = _normalize_string_list(settings.get("dataset_tag_options", []))
    if "guardian mode" not in {tag.lower() for tag in settings["dataset_tag_options"]}:
        settings["dataset_tag_options"] = ["guardian mode", *settings["dataset_tag_options"]]

    settings["guardian_mode_enabled"] = bool(settings.get("guardian_mode_enabled", True))
    try:
        settings["guardian_check_interval_seconds"] = max(
            30, int(settings.get("guardian_check_interval_seconds", 300))
        )
    except Exception:
        settings["guardian_check_interval_seconds"] = DEFAULT_SETTINGS["guardian_check_interval_seconds"]

    try:
        settings["guardian_entertainment_daily_limit_minutes"] = max(
            0,
            int(
                settings.get(
                    "guardian_entertainment_daily_limit_minutes",
                    DEFAULT_SETTINGS["guardian_entertainment_daily_limit_minutes"],
                )
            ),
        )
    except Exception:
        settings["guardian_entertainment_daily_limit_minutes"] = DEFAULT_SETTINGS[
            "guardian_entertainment_daily_limit_minutes"
        ]

    settings["guardian_entertainment_day_start_time"] = _normalize_time_string(
        settings.get(
            "guardian_entertainment_day_start_time",
            DEFAULT_SETTINGS["guardian_entertainment_day_start_time"],
        ),
        DEFAULT_SETTINGS["guardian_entertainment_day_start_time"],
    )

    try:
        settings["guardian_rest_quota_per_day"] = max(
            0,
            min(20, int(settings.get("guardian_rest_quota_per_day", 3))),
        )
    except Exception:
        settings["guardian_rest_quota_per_day"] = DEFAULT_SETTINGS["guardian_rest_quota_per_day"]

    pending_quota = settings.get("guardian_rest_quota_pending")
    if pending_quota in ("", None):
        settings["guardian_rest_quota_pending"] = None
    else:
        try:
            settings["guardian_rest_quota_pending"] = max(0, min(20, int(pending_quota)))
        except Exception:
            settings["guardian_rest_quota_pending"] = None
            settings["guardian_rest_quota_pending_day"] = None
    pending_day = str(settings.get("guardian_rest_quota_pending_day") or "").strip()
    settings["guardian_rest_quota_pending_day"] = pending_day or None
    if settings["guardian_rest_quota_pending"] is None:
        settings["guardian_rest_quota_pending_day"] = None

    settings, quota_applied = _apply_due_rest_quota(settings)
    if quota_applied:
        _write_settings_file(settings)

    practice_source_path = str(settings.get("practice_source_path") or "").strip()
    if practice_source_path:
        suffix = Path(practice_source_path).suffix.lower()
        if suffix not in {".md", ".txt"}:
            practice_source_path = str(DEFAULT_PRACTICE_FILE)
    else:
        practice_source_path = str(DEFAULT_PRACTICE_FILE)
    settings["practice_source_path"] = practice_source_path

    target_language = str(settings.get("practice_target_language") or "").strip()
    settings["practice_target_language"] = target_language if target_language in {"Chinese", "English", "Japanese", "Korean", "French", "Portuguese"} else "Japanese"

    try:
        cooldown = int(settings.get(
            "post_block_cooldown_seconds",
            DEFAULT_SETTINGS["post_block_cooldown_seconds"],
        ))
    except Exception:
        cooldown = DEFAULT_SETTINGS["post_block_cooldown_seconds"]
    settings["post_block_cooldown_seconds"] = max(0, min(cooldown, 3600))

    retention = settings.get("dataset_retention_days")
    if retention in ("", 0):
        retention = None
    if retention is not None:
        try:
            retention = max(1, int(retention))
        except Exception:
            retention = None
    settings["dataset_retention_days"] = retention

    return settings


def save_settings(settings_update: dict) -> dict:
    settings = load_settings()

    if "ui_language" in settings_update:
        if settings_update["ui_language"] not in {"zh", "en", "ja", "ko", "fr", "pt"}:
            raise ValueError("Unsupported interface language")
        settings["ui_language"] = settings_update["ui_language"]

    if "model" in settings_update:
        model = settings_update["model"]
        if model not in _valid_model_ids():
            raise ValueError(f"Unsupported model: {model}")
        settings["model"] = model

    if "strict_mode_enabled" in settings_update:
        requested = bool(settings_update["strict_mode_enabled"])
        if not requested and is_strict_locked(settings):
            raise ValueError("Strict mode is locked until the selected time.")
        settings["strict_mode_enabled"] = requested

    if "strict_locked_until" in settings_update:
        locked_until = settings_update["strict_locked_until"]
        if locked_until:
            try:
                datetime.fromisoformat(locked_until)
            except Exception:
                raise ValueError("Strict lock time must be a valid ISO datetime.")
        settings["strict_locked_until"] = locked_until

    if "supervision_level" in settings_update:
        level = settings_update["supervision_level"]
        if level not in _valid_supervision_level_ids():
            raise ValueError(f"Unsupported supervision level: {level}")
        settings["supervision_level"] = level

    if "nudge_prompt" in settings_update:
        prompt = str(settings_update["nudge_prompt"] or "").strip()
        if not prompt:
            raise ValueError("提示语不能为空。")
        if len(prompt) > 500:
            raise ValueError("提示语不能超过 500 个字符。")
        settings["nudge_prompt"] = prompt

    if "default_check_interval_seconds" in settings_update:
        try:
            value = int(settings_update["default_check_interval_seconds"])
        except Exception:
            raise ValueError("默认检测间隔需要是整数秒。")
        if value < 5:
            raise ValueError("默认检测间隔不能少于 5 秒。")
        settings["default_check_interval_seconds"] = value

    if "trigger_threshold" in settings_update:
        try:
            value = int(settings_update["trigger_threshold"])
        except Exception:
            raise ValueError("触发答题命中次数需要是整数。")
        if value < 1:
            raise ValueError("触发答题命中次数不能少于 1。")
        settings["trigger_threshold"] = value

    if "whitelist_behaviors" in settings_update:
        behaviors = _normalize_string_list(settings_update["whitelist_behaviors"])
        if len(behaviors) > 50:
            raise ValueError("白名单最多支持 50 条行为描述。")
        if any(len(item) > 120 for item in behaviors):
            raise ValueError("单条白名单行为不能超过 120 个字符。")
        settings["whitelist_behaviors"] = behaviors

    if "guardian_mode_enabled" in settings_update:
        settings["guardian_mode_enabled"] = bool(settings_update["guardian_mode_enabled"])

    if "guardian_check_interval_seconds" in settings_update:
        try:
            value = int(settings_update["guardian_check_interval_seconds"])
        except Exception:
            raise ValueError("Guardian mode 检测间隔需要是整数秒。")
        if value < 30:
            raise ValueError("Guardian mode 检测间隔不能少于 30 秒。")
        settings["guardian_check_interval_seconds"] = value

    if "guardian_entertainment_daily_limit_minutes" in settings_update:
        try:
            value = int(settings_update["guardian_entertainment_daily_limit_minutes"])
        except Exception:
            raise ValueError("Guardian entertainment daily limit must be an integer number of minutes.")
        if value < 0:
            raise ValueError("Guardian entertainment daily limit cannot be negative.")
        if value > 24 * 60:
            raise ValueError("Guardian entertainment daily limit cannot exceed 24 hours.")
        settings["guardian_entertainment_daily_limit_minutes"] = value

    if "guardian_entertainment_day_start_time" in settings_update:
        settings["guardian_entertainment_day_start_time"] = _normalize_time_string(
            settings_update["guardian_entertainment_day_start_time"],
            None,
        )

    if "guardian_rest_quota_per_day" in settings_update:
        try:
            value = int(settings_update["guardian_rest_quota_per_day"])
        except Exception:
            raise ValueError("每日休息次数需要是整数。")
        if value < 0 or value > 20:
            raise ValueError("每日休息次数需要在 0 到 20 次之间。")
        current = int(settings["guardian_rest_quota_per_day"])
        if value == current:
            settings["guardian_rest_quota_pending"] = None
            settings["guardian_rest_quota_pending_day"] = None
        else:
            settings["guardian_rest_quota_pending"] = value
            settings["guardian_rest_quota_pending_day"] = next_guardian_logical_day_key(
                datetime.now().astimezone(),
                settings["guardian_entertainment_day_start_time"],
            )

    if "practice_source_path" in settings_update:
        value = str(settings_update["practice_source_path"] or "").strip()
        if not value:
            raise ValueError("Practice source path cannot be empty.")
        path = Path(value).expanduser()
        if path.suffix.lower() not in {".md", ".txt"}:
            raise ValueError("Practice source must be a Markdown or text file.")
        settings["practice_source_path"] = str(path)

    if "practice_target_language" in settings_update:
        value = str(settings_update["practice_target_language"] or "").strip()
        if not value:
            raise ValueError("Practice target language cannot be empty.")
        if value not in {"Chinese", "English", "Japanese", "Korean", "French", "Portuguese"}:
            raise ValueError("Unsupported translation target language")
        settings["practice_target_language"] = value

    if "post_block_cooldown_seconds" in settings_update:
        try:
            cooldown = int(settings_update["post_block_cooldown_seconds"])
        except Exception:
            raise ValueError("答完题后的冷却时间需要是整数秒。")
        if cooldown < 0:
            raise ValueError("答完题后的冷却时间不能为负数。")
        if cooldown > 3600:
            raise ValueError("答完题后的冷却时间不能超过 3600 秒。")
        settings["post_block_cooldown_seconds"] = cooldown

    if "dataset_tag_options" in settings_update:
        tags = _normalize_string_list(settings_update["dataset_tag_options"])
        if "guardian mode" not in {tag.lower() for tag in tags}:
            tags = ["guardian mode", *tags]
        if len(tags) > 100:
            raise ValueError("数据集任务标签最多支持 100 个。")
        if any(len(item) > 80 for item in tags):
            raise ValueError("单个数据集任务标签不能超过 80 个字符。")
        settings["dataset_tag_options"] = tags

    if "dataset_retention_days" in settings_update:
        value = settings_update["dataset_retention_days"]
        if value in (None, "", 0):
            settings["dataset_retention_days"] = None
        else:
            try:
                days = int(value)
            except Exception:
                raise ValueError("数据集保留天数需要是整数。")
            if days < 1:
                raise ValueError("数据集保留天数不能少于 1 天。")
            settings["dataset_retention_days"] = days

    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

    return settings


def _write_settings_file(settings: dict):
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def guardian_logical_day_key(now: datetime, start_text: str) -> str:
    hour, minute = [int(part) for part in start_text.split(":")]
    day_start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now < day_start:
        return (now.date() - timedelta(days=1)).isoformat()
    return now.date().isoformat()


def next_guardian_logical_day_key(now: datetime, start_text: str) -> str:
    today = guardian_logical_day_key(now, start_text)
    return (datetime.fromisoformat(today).date() + timedelta(days=1)).isoformat()


def _apply_due_rest_quota(settings: dict) -> Tuple[dict, bool]:
    pending = settings.get("guardian_rest_quota_pending")
    pending_day = settings.get("guardian_rest_quota_pending_day")
    if pending is None or not pending_day:
        return settings, False
    today = guardian_logical_day_key(
        datetime.now().astimezone(),
        settings["guardian_entertainment_day_start_time"],
    )
    if str(pending_day) > today:
        return settings, False
    settings["guardian_rest_quota_per_day"] = int(pending)
    settings["guardian_rest_quota_pending"] = None
    settings["guardian_rest_quota_pending_day"] = None
    return settings, True


def get_selected_model() -> str:
    return load_settings()["model"]


def get_default_strict_mode() -> bool:
    return bool(load_settings().get("strict_mode_enabled", True))


def get_supervision_level() -> str:
    return load_settings()["supervision_level"]


def get_nudge_prompt() -> str:
    return load_settings()["nudge_prompt"]


def get_default_check_interval_seconds() -> int:
    return int(load_settings()["default_check_interval_seconds"])


def get_default_trigger_threshold() -> int:
    return int(load_settings()["trigger_threshold"])


def get_whitelist_behaviors() -> list:
    return load_settings()["whitelist_behaviors"]


def get_dataset_tag_options() -> list:
    return load_settings()["dataset_tag_options"]


def is_guardian_mode_enabled() -> bool:
    return bool(load_settings().get("guardian_mode_enabled", True))


def get_guardian_check_interval_seconds() -> int:
    return int(load_settings()["guardian_check_interval_seconds"])


def get_guardian_entertainment_daily_limit_minutes() -> int:
    return int(load_settings()["guardian_entertainment_daily_limit_minutes"])


def get_guardian_entertainment_day_start_time() -> str:
    return load_settings()["guardian_entertainment_day_start_time"]


def get_guardian_rest_quota_per_day() -> int:
    return int(load_settings()["guardian_rest_quota_per_day"])


def get_practice_source_path() -> str:
    return load_settings()["practice_source_path"]


def get_practice_target_language() -> str:
    return load_settings()["practice_target_language"]


def get_post_block_cooldown_seconds() -> int:
    return int(load_settings()["post_block_cooldown_seconds"])


def _normalize_time_string(value, fallback: str = None) -> str:
    text = str(value or "").strip()
    try:
        parts = text.split(":")
        if len(parts) != 2:
            raise ValueError
        hour = int(parts[0])
        minute = int(parts[1])
        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError
        return f"{hour:02d}:{minute:02d}"
    except Exception:
        if fallback is not None:
            return fallback
        raise ValueError("Guardian entertainment day start time must be HH:MM.")


def _normalize_string_list(value) -> list:
    if isinstance(value, str):
        raw_items = value.replace("，", "\n").replace(",", "\n").splitlines()
    elif isinstance(value, list):
        raw_items = value
    else:
        raw_items = []

    normalized = []
    seen = set()
    for item in raw_items:
        text = str(item or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(text)
    return normalized


def get_supervision_rules(level: str = None) -> str:
    selected = level or get_supervision_level()
    whitelist = get_whitelist_behaviors()
    whitelist_rules = "User-defined whitelist behaviors: none."
    if whitelist:
        whitelist_rules = (
            "User-defined whitelist behaviors. If the screenshot's main activity clearly matches one of these descriptions, mark on_task true, "
            "unless the activity is hard-blocked content:\n"
            + "\n".join(f"- {item}" for item in whitelist)
        )
    rules = {
        "task_related": (
            "Supervision level: TASK_RELATED.\n"
            "The declared task IS the decision criterion.\n"
            f"{whitelist_rules}\n"
            "- Hard-blocked content always overrides the declared task and whitelist: porn/adult sexual content, reading novels/web novels, and reading manga/comics are off-task.\n"
            "- Mark on_task true only when the visible activity is clearly and strongly related to the declared task.\n"
            "- Idle desktop, empty search pages, and unrelated browsing are off-task unless they clearly match a whitelist behavior or a personal calibration case labeled on_task.\n"
            "- Short videos, social media, games, shopping, and unrelated browsing are off-task unless they clearly match a whitelist behavior."
        ),
        "not_entertainment": (
            "Supervision level: NOT_ENTERTAINMENT.\n"
            "Decide whether the screen is obvious entertainment. Do NOT require the activity to match the declared task.\n"
            f"{whitelist_rules}\n"
            "- Hard-blocked content is always off-task: porn/adult sexual content, reading novels/web novels, and reading manga/comics.\n"
            "- Mark on_task true for idle desktop, wallpaper, icon grid, blank or empty editor, new tab, loading or waiting page, search homepage, looking up a word or definition, email, calendar, notes, documents, coding, research, planning, and other non-entertainment work.\n"
            "- Short videos, social media feeds, games, shopping, and other obvious entertainment are off-task unless they clearly match a whitelist behavior.\n"
            "- Do not mark off_task just because the screen is idle, empty, a search page, or unrelated to the declared task.\n"
            "- If unsure and the screen is not clearly entertainment, mark on_task true."
        ),
    }
    return rules.get(selected, rules[DEFAULT_SETTINGS["supervision_level"]])


def is_strict_locked(settings: dict = None) -> bool:
    settings = settings or load_settings()
    if not settings.get("strict_mode_enabled"):
        return False
    locked_until = settings.get("strict_locked_until")
    if not locked_until:
        return False
    try:
        return datetime.now() < datetime.fromisoformat(locked_until)
    except Exception:
        return False


def get_strict_status() -> dict:
    settings = load_settings()
    return {
        "enabled": bool(settings.get("strict_mode_enabled")),
        "locked_until": settings.get("strict_locked_until"),
        "locked": is_strict_locked(settings),
    }


def get_settings_payload() -> dict:
    return {
        "settings": load_settings(),
        "model_options": MODEL_OPTIONS,
        "supervision_level_options": SUPERVISION_LEVEL_OPTIONS,
        "strict_status": get_strict_status(),
    }
