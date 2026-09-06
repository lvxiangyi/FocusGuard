"""Resolve the OpenAI-compatible client for the selected model."""

from __future__ import annotations

import copy
import os
from typing import Any, Optional

from openai import OpenAI
from dotenv import load_dotenv

from data_paths import ENV_FILE
from settings_manager import get_selected_model

load_dotenv(dotenv_path=ENV_FILE)

PROVIDERS = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "env_keys": ("OPENROUTER_API_KEY",),
        "label": "OpenRouter",
        "extra_body": None,
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "env_keys": ("DEEPSEEK_API_KEY",),
        "label": "DeepSeek",
        "extra_body": None,
        "signup_url": "https://platform.deepseek.com",
    },
    "minimax": {
        "base_url": "https://api.minimaxi.com/v1",
        "env_keys": ("MINIMAX_API_KEY",),
        "label": "MiniMax",
        "extra_body": {"thinking": {"type": "disabled"}},
        "signup_url": "https://platform.minimaxi.com",
    },
}

MODEL_PROVIDER = {
    "qwen/qwen3.7-flash": "openrouter",
    "qwen/qwen3.8-flash": "openrouter",
    "z-ai/glm-5.3-flash": "openrouter",
    "deepseek/deepseek-v4-flash-vision-exp": "openrouter",
    "minimax/minimax-m3": "openrouter",
    "google/gemini-2.5-flash-lite": "openrouter",
    "openai/gpt-4o": "openrouter",
    "openai/gpt-4o-mini": "openrouter",
}

# Cheap hybrid-thinking models otherwise spend max_tokens on reasoning and
# return message.content = None, which breaks JSON grading/judging.
_DISABLE_THINKING = {
    "enable_thinking": False,
    "reasoning": {"enabled": False},
}

MODEL_EXTRA_BODY = {
    "qwen/qwen3.7-flash": _DISABLE_THINKING,
    "qwen/qwen3.8-flash": _DISABLE_THINKING,
    "z-ai/glm-5.3-flash": {"reasoning": {"enabled": False}},
    "minimax/minimax-m3": {"thinking": {"type": "disabled"}},
}

PLACEHOLDER_KEYS = {"", "your_api_key_here"}


def provider_id_for_model(model: Optional[str] = None) -> str:
    model = model or get_selected_model()
    return MODEL_PROVIDER.get(model, "openrouter")


def provider_config(model: Optional[str] = None) -> dict:
    return PROVIDERS[provider_id_for_model(model)]


def _api_key_for_provider(provider: str) -> str:
    for env_name in PROVIDERS[provider]["env_keys"]:
        value = (os.getenv(env_name) or "").strip()
        if value and value not in PLACEHOLDER_KEYS:
            return value
    return ""


def api_key_for_model(model: Optional[str] = None) -> str:
    return _api_key_for_provider(provider_id_for_model(model))


def has_api_key(model: Optional[str] = None) -> bool:
    return bool(api_key_for_model(model))


def extra_body_for_model(model: Optional[str] = None) -> Optional[dict]:
    model = model or get_selected_model()
    extra = MODEL_EXTRA_BODY.get(model)
    if extra:
        return copy.deepcopy(extra)
    extra = provider_config(model).get("extra_body")
    return copy.deepcopy(extra) if extra else None


def _stringify_content(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text") or ""))
            else:
                parts.append(str(getattr(part, "text", "") or ""))
        return "".join(parts).strip()
    return str(content).strip()


def message_text(response: Any) -> str:
    """Return assistant text even when a thinking model left content empty."""
    choice = response.choices[0]
    message = choice.message
    text = _stringify_content(getattr(message, "content", None))
    if text:
        return text
    for attr in ("reasoning_content", "reasoning"):
        text = _stringify_content(getattr(message, attr, None))
        if text:
            return text
    finish = getattr(choice, "finish_reason", None)
    raise ValueError(f"Model returned empty content (finish_reason={finish}).")


def missing_key_message(model: Optional[str] = None) -> str:
    cfg = provider_config(model)
    env_name = cfg["env_keys"][0]
    signup = cfg.get("signup_url")
    suffix = f" 申请地址：{signup}" if signup else ""
    return f"未配置有效的 {cfg['label']} API Key。请在 .env 写入 {env_name}。{suffix}"


def get_client(model: Optional[str] = None) -> OpenAI:
    cfg = provider_config(model)
    return OpenAI(
        api_key=api_key_for_model(model),
        base_url=cfg["base_url"],
        timeout=60.0,
    )
