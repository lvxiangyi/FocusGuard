import json
import base64
import random
import re
import time

from ai_status_manager import (
    has_api_key,
    is_mock_enabled,
    record_ai_error,
    record_ai_success,
)
from settings_manager import get_selected_model, get_supervision_rules
from llm_client import extra_body_for_model, get_client, message_text, missing_key_message

JUDGE_MAX_ATTEMPTS = 3

PROMPT_TEMPLATE = """You are a focus monitoring agent.

The user's declared task is:
"{task}"

{memory_context}

{precedents}

Look at the screenshot and decide on_task using ONLY the supervision rules below.
The declared task is background context. It is the decision criterion only when the supervision level is TASK_RELATED.

{supervision_rules}

Shared rules:
- Hard-blocked content is always off-task: porn/adult sexual content, reading novels/web novels, and reading manga/comics.
- Personal calibration cases above are user-labeled similar screens. If the current screen is visually similar to a case, follow that human_label. They are not a blanket whitelist for entertainment.
- Learned exceptions listed above are dispute-memory only: those specific activities are on-task.
- If the screenshot is blank, dark, idle, or unclear, still return JSON. Do not treat that as entertainment by default.

CRITICAL OUTPUT RULES:
- Reply with a single JSON object only.
- Do not use markdown fences.
- Do not write any explanation before or after the JSON.

Required JSON shape:
{{
  "on_task": true or false,
  "confidence": number between 0 and 1,
  "current_activity": "short description of what the user is doing",
  "reason": "short explanation"
}}"""


DISPUTE_PROMPT_TEMPLATE = """You are a focus monitoring agent that is evaluating a user's dispute.

The user's declared task is: "{task}"

The AI previously judged the user as OFF-TASK:
- Detected activity: "{activity}"
- AI's reason: "{original_reason}"

The user disagrees and says:
"{user_reason}"

{memory_context}

Please evaluate:
1. Is the user's explanation reasonable? Could their current activity actually be related to the declared task?
2. Be fair - if the user provides a reasonable explanation, accept it.
3. But don't accept obviously false excuses.

CRITICAL OUTPUT RULES:
- Reply with a single JSON object only.
- Do not use markdown fences.
- Do not write any explanation before or after the JSON.

Required JSON shape:
{{
  "accepted": true or false,
  "ai_reason": "short explanation of why you accepted or rejected the dispute"
}}"""


GUARDIAN_PROMPT_TEMPLATE = """You are Guardian mode for a local focus assistant.

Guardian mode is always-on and only detects obvious entertainment or adult distractions.
It does not judge whether work is related to a declared task.

{whitelist_context}

{precedents}

Look at the screenshot and decide whether Guardian mode should interrupt the user.

Interrupt only for clearly visible:
- porn or adult sexual content
- reading novels or web novels for entertainment
- reading manga or comics for entertainment
- playing or watching games as entertainment

These are OR conditions. If any one category is clearly visible, set should_interrupt=true.
Adult/sexual content is only one category; novels, web novels, manga, comics, and games do not need to be adult/sexual to trigger.

Do not interrupt for normal work, study, coding, writing, documentation, chat about work, music players, timers, utilities, or ambiguous screens.
If a visible activity clearly matches the user-defined whitelist, do not interrupt unless it also clearly falls into one of the four interrupt categories above.
Personal calibration cases below may be allow or interrupt. Follow human_label for a visually similar screen; they are not a whitelist.
If unsure, do not interrupt.

CRITICAL OUTPUT RULES:
- Reply with a single JSON object only.
- Do not use markdown fences.
- Do not write any explanation before or after the JSON.
- Even if the screenshot is blank, dark, or unclear, still return JSON with should_interrupt=false and trigger_category="none".

Required JSON shape:
{{
  "should_interrupt": true or false,
  "trigger_category": "adult" or "novel" or "manga" or "game" or "none",
  "confidence": number between 0 and 1,
  "current_activity": "short description of what the user is doing",
  "reason": "short explanation"
}}

Meaning:
- should_interrupt=true only for the explicit Guardian categories above.
- should_interrupt=true when trigger_category is adult, novel, manga, or game.
- should_interrupt=false for papers, articles, search pages, normal work/study, ambiguous reading, or anything that is not clearly entertainment/adult content.
"""

JSON_RETRY_HINT = (
    "Your previous reply was invalid. Return ONLY one JSON object matching the required schema. "
    "No markdown. No prose."
)


def _format_memory_context(memory: list) -> str:
    """Format dispute memory into context for the prompt."""
    if not memory:
        return ""

    lines = ["Previously learned exceptions (activities the user has explained are actually on-task):"]
    for entry in memory[-10:]:  # Last 10 entries to avoid too long context
        lines.append(f"- Activity: \"{entry.get('activity', '')}\" → Reason: \"{entry.get('user_reason', '')}\"")

    return "\n".join(lines)


def _format_whitelist_context() -> str:
    from settings_manager import get_whitelist_behaviors

    whitelist = get_whitelist_behaviors()
    if not whitelist:
        return "User-defined whitelist behaviors: none."
    lines = ["User-defined whitelist behaviors:"]
    lines.extend(f"- {item}" for item in whitelist)
    return "\n".join(lines)


def _mock_judge(task: str) -> dict:
    """Mock mode: randomly return on_task or off_task for testing."""
    on_task = random.random() > 0.4
    activities_on = [
        "reading study materials",
        "writing notes in a document",
        "viewing educational content",
        "solving practice problems",
    ]
    activities_off = [
        "watching YouTube Shorts",
        "browsing social media",
        "playing a game",
        "shopping online",
    ]

    if on_task:
        activity = random.choice(activities_on)
        reason = f"The user appears to be engaged in activities related to '{task}'."
    else:
        activity = random.choice(activities_off)
        reason = f"The user is doing '{activity}' which is unrelated to '{task}'."

    return {
        "on_task": on_task,
        "confidence": round(random.uniform(0.6, 0.95), 2),
        "current_activity": activity,
        "reason": reason,
        "judgement_status": "mock",
        "model": "mock",
    }


def _api_error_result(task: str, error: str, model: str = "", error_kind: str = "api_error") -> dict:
    return {
        "on_task": True,
        "confidence": 0,
        "current_activity": "AI 判定不可用",
        "reason": f"AI 本次无法完成判定（{error_kind}）：{error}",
        "judgement_status": "api_error",
        "error": error,
        "error_kind": error_kind,
        "model": model or "api-error",
    }


def _get_client():
    """Get the OpenAI-compatible client for the selected model."""
    return get_client()


def extract_json_object(text: str) -> dict:
    """Parse a JSON object from model output that may include prose or fences."""
    if text is None:
        raise ValueError("Model returned empty content.")
    content = str(text).strip()
    if not content:
        raise ValueError("Model returned empty content.")

    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        content = content.rsplit("```", 1)[0].strip()
        if content.lower().startswith("json"):
            content = content[4:].strip()

    try:
        parsed = json.loads(content)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{[\s\S]*\}", content)
    if not match:
        raise ValueError(f"No JSON object found in model reply: {content[:180]!r}")

    candidate = match.group(0)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        repaired = re.sub(r",\s*}", "}", candidate)
        repaired = re.sub(r",\s*]", "]", repaired)
        parsed = json.loads(repaired)

    if not isinstance(parsed, dict):
        raise ValueError("Parsed JSON is not an object.")
    return parsed


def classify_judge_error(error: Exception) -> str:
    message = str(error).lower()
    if "401" in message or "user not found" in message or "unauthorized" in message:
        return "auth_error"
    if "connection" in message or "timeout" in message or "timed out" in message or "network" in message:
        return "connection_error"
    if "json" in message or "expecting" in message or "unterminated" in message or "empty content" in message or "no json object" in message:
        return "parse_error"
    return "api_error"


def _chat_completion_json(client, *, model: str, content_parts: list, max_tokens: int) -> dict:
    """
    Call the chat API and require a JSON object.
    Retries on empty/non-JSON replies and transient connection issues.
    """
    messages = [{"role": "user", "content": content_parts}]
    last_error = None

    for attempt in range(1, JUDGE_MAX_ATTEMPTS + 1):
        try:
            kwargs = {
                "model": model,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": 0.1,
            }
            extra_body = extra_body_for_model(model)
            if extra_body:
                kwargs["extra_body"] = extra_body
            try:
                response = client.chat.completions.create(
                    **kwargs,
                    response_format={"type": "json_object"},
                )
            except Exception as format_error:
                if "response_format" in str(format_error).lower() or "json_object" in str(format_error).lower():
                    response = client.chat.completions.create(**kwargs)
                else:
                    raise

            return extract_json_object(message_text(response))
        except Exception as e:
            last_error = e
            kind = classify_judge_error(e)
            print(f"[vision_judge] Attempt {attempt}/{JUDGE_MAX_ATTEMPTS} failed ({kind}): {e}")
            if attempt >= JUDGE_MAX_ATTEMPTS:
                break
            if kind == "parse_error":
                messages = [
                    {"role": "user", "content": content_parts},
                    {"role": "user", "content": JSON_RETRY_HINT},
                ]
            else:
                time.sleep(min(1.5 * attempt, 4.0))

    raise last_error


GUARDIAN_HARD_CATEGORIES = {"adult", "novel", "manga", "game"}
PERSONAL_ALLOW_OVERRIDE_SCORE = 0.55


def _retrieve_personal_hits(mode: str, task: str = "", screenshot_path: str = "", ai_activity: str = "") -> list:
    """Retrieve train precedents; never fails the judge."""
    try:
        from personal_bench.retrieve import retrieve_similar
        from personal_bench.store import BenchStore

        hits = retrieve_similar(
            BenchStore(),
            mode=mode,
            task=task or "",
            ai_activity=ai_activity or "",
            image_path=screenshot_path or None,
            k=3,
        )
        if hits:
            summary = ", ".join(
                f"{h.get('id', '')[:8]}:{h.get('human_label')}:{h.get('retrieval_score')}"
                for h in hits
            )
            print(f"[vision_judge] Personal bench hits ({mode}): {summary}")
        else:
            print(f"[vision_judge] Personal bench hits ({mode}): none")
        return hits
    except Exception as e:
        print(f"[vision_judge] Personal bench retrieval skipped: {e}")
        return []


def _personal_precedents_block(mode: str, task: str = "", screenshot_path: str = "", ai_activity: str = "") -> str:
    try:
        from personal_bench.inject import format_precedents_block
        return format_precedents_block(
            _retrieve_personal_hits(mode, task=task, screenshot_path=screenshot_path, ai_activity=ai_activity),
            max_items=3,
        )
    except Exception as e:
        print(f"[vision_judge] Personal bench format skipped: {e}")
        return ""


def should_force_guardian_category_interrupt(category: str, hits: list) -> bool:
    """Hard-interrupt entertainment categories unless a close personal allow case matches."""
    if str(category or "").strip().lower() not in GUARDIAN_HARD_CATEGORIES:
        return False
    top = hits[0] if hits else None
    if not top:
        return True
    if str(top.get("human_label") or "").strip().lower() != "allow":
        return True
    try:
        score = float(top.get("retrieval_score") or 0)
    except (TypeError, ValueError):
        score = 0.0
    return score < PERSONAL_ALLOW_OVERRIDE_SCORE


def build_session_judge_prompt(
    task: str,
    supervision_level: str = None,
    memory_context: str = "",
    precedents: str = "",
) -> str:
    """Assemble the Session judge prompt for the given supervision level."""
    return PROMPT_TEMPLATE.format(
        task=task or "",
        memory_context=memory_context or "",
        precedents=precedents or "",
        supervision_rules=get_supervision_rules(supervision_level),
    )


def judge_screenshot(task: str, screenshot_path: str, memory: list = None, supervision_level: str = None) -> dict:
    """Judge whether the user is on task based on a screenshot."""
    model = get_selected_model()

    if is_mock_enabled():
        print("[vision_judge] AIMONITOR_ENABLE_MOCK_AI is enabled, using mock mode.")
        return _mock_judge(task)

    if not has_api_key():
        error = missing_key_message(model)
        print(f"[vision_judge] {error}")
        record_ai_error(error, model=model)
        return _api_error_result(task, error, model=model, error_kind="auth_error")

    memory_context = _format_memory_context(memory or [])
    from personal_bench.inject import format_precedents_block
    hits = _retrieve_personal_hits("session", task=task, screenshot_path=screenshot_path)
    precedents = format_precedents_block(hits, max_items=3)

    try:
        client = _get_client()
        print(f"[vision_judge] Using model: {model}")

        with open(screenshot_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        result = _chat_completion_json(
            client,
            model=model,
            content_parts=[
                {
                    "type": "text",
                    "text": build_session_judge_prompt(
                        task,
                        supervision_level=supervision_level,
                        memory_context=memory_context,
                        precedents=precedents,
                    ) + "\nWrite current_activity and reason in " + _ui_output_language() + ".",
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_data}",
                        "detail": "low",
                    },
                },
            ],
            max_tokens=400,
        )
        result["model"] = model
        result["judgement_status"] = "ok"
        result["personal_reference_count"] = min(3, len(hits))
        record_ai_success(model)
        return result

    except Exception as e:
        error = str(e)
        kind = classify_judge_error(e)
        print(f"[vision_judge] Error calling API ({kind}): {error}")
        print("[vision_judge] Pausing this judgement instead of using random mock mode.")
        record_ai_error(error, model=model)
        return _api_error_result(task, error, model=model, error_kind=kind)


def judge_guardian_screenshot(screenshot_path: str) -> dict:
    """Judge whether always-on Guardian mode should interrupt obvious entertainment."""
    model = get_selected_model()

    if is_mock_enabled():
        result = _mock_judge("Guardian mode")
        result["on_task"] = bool(result.get("on_task", True))
        return result

    if not has_api_key():
        error = missing_key_message(model)
        print(f"[vision_judge] {error}")
        record_ai_error(error, model=model)
        return _api_error_result("Guardian mode", error, model=model, error_kind="auth_error")

    try:
        client = _get_client()
        print(f"[vision_judge] Using model for guardian: {model}")

        with open(screenshot_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        whitelist_context = _format_whitelist_context()
        hits = _retrieve_personal_hits("guardian", screenshot_path=screenshot_path)
        from personal_bench.inject import format_precedents_block
        precedents = format_precedents_block(hits, max_items=3)

        result = _chat_completion_json(
            client,
            model=model,
            content_parts=[
                {
                    "type": "text",
                    "text": GUARDIAN_PROMPT_TEMPLATE.format(
                        whitelist_context=whitelist_context,
                        precedents=precedents,
                    ),
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_data}",
                        "detail": "low",
                    },
                },
            ],
            max_tokens=350,
        )
        if "should_interrupt" in result:
            result["on_task"] = not bool(result["should_interrupt"])
        category = str(result.get("trigger_category", "none")).strip().lower()
        if should_force_guardian_category_interrupt(category, hits):
            result["should_interrupt"] = True
            result["on_task"] = False
        elif "should_interrupt" not in result:
            result["should_interrupt"] = not bool(result.get("on_task", True))
        result["model"] = model
        result["judgement_status"] = "ok"
        record_ai_success(model)
        return result

    except Exception as e:
        error = str(e)
        kind = classify_judge_error(e)
        print(f"[vision_judge] Guardian error calling API ({kind}): {error}")
        record_ai_error(error, model=model)
        return _api_error_result("Guardian mode", error, model=model, error_kind=kind)


def evaluate_dispute(task: str, activity: str, original_reason: str, user_reason: str, memory: list = None) -> dict:
    """Evaluate a user's dispute against an AI judgement."""
    if is_mock_enabled():
        print("[vision_judge] No valid API key, auto-accepting dispute in mock mode.")
        return {"accepted": True, "ai_reason": "Mock mode: dispute auto-accepted."}

    if not has_api_key():
        return {"accepted": True, "ai_reason": "AI 未连接，默认接受本次异议。"}

    memory_context = _format_memory_context(memory or [])

    try:
        client = _get_client()
        model = get_selected_model()
        print(f"[vision_judge] Using model for dispute: {model}")

        result = _chat_completion_json(
            client,
            model=model,
            content_parts=[
                {
                    "type": "text",
                    "text": DISPUTE_PROMPT_TEMPLATE.format(
                        task=task,
                        activity=activity,
                        original_reason=original_reason,
                        user_reason=user_reason,
                        memory_context=memory_context,
                    ),
                }
            ],
            max_tokens=250,
        )
        return result

    except Exception as e:
        print(f"[vision_judge] Dispute evaluation error: {e}")
        return {"accepted": True, "ai_reason": f"Error during evaluation, accepting dispute. ({e})"}


def _ui_output_language():
    from mvp_i18n import LANGUAGES
    from settings_manager import load_settings
    return LANGUAGES.get(load_settings().get("ui_language"), "Chinese")
