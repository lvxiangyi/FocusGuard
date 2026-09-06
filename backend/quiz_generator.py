"""
Quiz generator: generates questions related to the user's task.
When the user is distracted, they must answer a quiz to continue.
Wrong answers are recorded for review.
"""

import json
import random
import uuid
import re
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from data_paths import ENV_FILE, LOGS_DIR, PRACTICE_ATTEMPTS_FILE, PRACTICE_DIR, PRACTICE_STATE_FILE, PROJECT_ROOT
from llm_client import extra_body_for_model, get_client, has_api_key, message_text
from settings_manager import get_practice_source_path, get_practice_target_language, get_selected_model, save_settings

load_dotenv(dotenv_path=ENV_FILE)

WRONG_ANSWERS_FILE = LOGS_DIR / "wrong_answers.json"


def _llm_complete(messages, max_tokens: int):
    model = get_selected_model()
    kwargs = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "timeout": 45,
    }
    extra = extra_body_for_model(model)
    if extra:
        kwargs["extra_body"] = extra
    print(f"[quiz_generator] Using model: {model}")
    return get_client().chat.completions.create(**kwargs), model


def _parse_llm_json(response) -> dict:
    content = message_text(response)
    if content.startswith("```"):
        content = content.split("\n", 1)[1] if "\n" in content else content[3:]
        content = content.rsplit("```", 1)[0].strip()
        if content.lower().startswith("json"):
            content = content[4:].strip()
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        raise ValueError("Model returned non-object JSON.")
    return parsed

QUIZ_PROMPT = """You are a quiz generator for a study assistant app.

The user's study task is: "{task}"

Generate ONE quiz question related to this study topic.
The question should be educational and help reinforce the subject matter.
Difficulty: medium.

IMPORTANT: Generate the question and all options in Japanese (日本語).

Return JSON only:
{{
  "question": "問題文（日本語）",
  "options": ["選択肢A", "選択肢B", "選択肢C", "選択肢D"],
  "correct_index": 0,
  "explanation": "正解の説明（日本語）"
}}

Important:
- correct_index is 0-based (0=A, 1=B, 2=C, 3=D)
- Make the question specific and educational
- All options should be plausible
- Everything must be in Japanese
"""

TRANSLATION_GRADE_PROMPT = """You are grading a short translation task.

Source text:
"{source_text}"

Target language:
"{target_language}"

User's translation:
"{user_answer}"

Grade whether the user's translation preserves the main meaning in natural or acceptable {target_language}.
Be fair about minor grammar/spelling issues. Reject answers that are empty, unrelated, copied source text, or miss the core meaning.

Return JSON only:
{{
  "accepted": true or false,
  "score": number between 0 and 1,
  "feedback": "one short sentence",
  "model_translation": "a concise reference translation in {target_language}",
  "explanation": "1-2 sentences: key phrase, why it is accepted or rejected"
}}
"""

TRANSLATION_EXPLAIN_PROMPT = """You are a language tutor. The student could not translate this sentence and asked for the answer.

Source text:
"{source_text}"

Target language:
"{target_language}"

Give a correct reference translation and a teaching explanation in the requested feedback language.

Return JSON only:
{{
  "model_translation": "the full translation in {target_language}",
  "explanation": "2-4 sentences: key words/grammar and why this translation is correct"
}}
"""

TRANSLATION_CHALLENGES = [
    "I will return to my task and work with focus.",
    "Small steps every day lead to real progress.",
    "Please close distractions and continue studying.",
    "A clear plan makes deep work easier.",
    "I can take a break after finishing this session.",
]

PRACTICE_FILE = PROJECT_ROOT.parent / "document" / "0718_Practice.md"

# Fallback quiz bank for common topics
FALLBACK_QUIZZES = {
    "math": [
        {
            "question": "∫ 2x dx の結果は？",
            "options": ["x² + C", "2x² + C", "x + C", "2x + C"],
            "correct_index": 0,
            "explanation": "∫ 2x dx = x² + C（積分定数）"
        },
        {
            "question": "lim(x→0) sin(x)/x の値は？",
            "options": ["1", "0", "∞", "不定"],
            "correct_index": 0,
            "explanation": "これは有名な極限で、値は1です。"
        },
        {
            "question": "行列 [[1,0],[0,1]] は何と呼ばれますか？",
            "options": ["単位行列", "零行列", "転置行列", "逆行列"],
            "correct_index": 0,
            "explanation": "対角成分が1、他が0の行列は単位行列（Identity Matrix）です。"
        },
        {
            "question": "dy/dx = 2x のとき、y = ?",
            "options": ["x² + C", "2x² + C", "x + C", "2"],
            "correct_index": 0,
            "explanation": "両辺を積分すると y = x² + C"
        },
        {
            "question": "三角形の内角の和は？",
            "options": ["180°", "360°", "90°", "270°"],
            "correct_index": 0,
            "explanation": "三角形の内角の和は常に180°です。"
        },
    ],
    "default": [
        {
            "question": "集中力を保つために最も効果的な方法は？",
            "options": ["25分作業+5分休憩（ポモドーロ）", "3時間連続作業", "BGMを大音量で流す", "SNSを開いたまま作業"],
            "correct_index": 0,
            "explanation": "ポモドーロ・テクニックは科学的に集中力維持に効果があることが示されています。"
        },
        {
            "question": "人間の短期記憶の容量は約何個？",
            "options": ["7±2個", "3±1個", "20±5個", "100個以上"],
            "correct_index": 0,
            "explanation": "ミラーの法則により、短期記憶は約7±2個の情報を保持できます。"
        },
    ]
}


def _load_wrong_answers() -> list:
    if WRONG_ANSWERS_FILE.exists():
        try:
            with open(WRONG_ANSWERS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_wrong_answers(answers: list):
    with open(WRONG_ANSWERS_FILE, "w", encoding="utf-8") as f:
        json.dump(answers, f, ensure_ascii=False, indent=2)


def record_wrong_answer(question: str, user_answer: str, correct_answer: str, task: str):
    """Record a wrong answer for later review."""
    answers = _load_wrong_answers()
    answers.append({
        "question": question,
        "user_answer": user_answer,
        "correct_answer": correct_answer,
        "task": task,
        "timestamp": __import__("datetime").datetime.now().isoformat(),
    })
    _save_wrong_answers(answers)


def get_wrong_answers() -> list:
    """Get all recorded wrong answers."""
    return _load_wrong_answers()


def generate_quiz(task: str) -> dict:
    """Generate a quiz question related to the user's task."""
    if not has_api_key():
        return _fallback_quiz(task)

    try:
        response, model = _llm_complete(
            [{"role": "user", "content": QUIZ_PROMPT.format(task=task)}],
            300,
        )

        return _parse_llm_json(response)

    except Exception as e:
        print(f"[quiz_generator] Error: {e}, using fallback")
        return _fallback_quiz(task)


def _fallback_quiz(task: str) -> dict:
    """Return a fallback quiz from the bank."""
    task_lower = task.lower()
    if any(w in task_lower for w in ["math", "数学", "calculus", "微積分", "線形代数"]):
        quizzes = FALLBACK_QUIZZES["math"]
    else:
        quizzes = FALLBACK_QUIZZES["default"]
    return random.choice(quizzes)


def _load_practice_challenges() -> list:
    source_path = _selected_practice_path()
    if not source_path.exists():
        return []
    try:
        lines = source_path.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        print(f"[quiz_generator] Could not read practice file: {e}")
        return []

    numbered_challenges = []
    fallback_challenges = []
    in_details = False
    in_code = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if stripped.lower().startswith("<details"):
            in_details = True
            continue
        if stripped.lower().startswith("</details"):
            in_details = False
            continue
        if in_details:
            continue
        sentence = ""
        numbered = re.match(r"^\d+[\.)]\s+(.+?)\s*$", stripped)
        bullet = re.match(r"^[-*]\s+(.+?)\s*$", stripped)
        if numbered:
            sentence = numbered.group(1).strip()
        elif bullet:
            sentence = bullet.group(1).strip()
        elif stripped and not stripped.startswith("#") and len(stripped) <= 300:
            sentence = stripped
        if not sentence:
            continue
        sentence = re.sub(r"\s{2,}$", "", sentence).strip()
        if len(sentence) < 4:
            continue
        if numbered:
            numbered_challenges.append(sentence)
        else:
            fallback_challenges.append(sentence)
    return numbered_challenges or fallback_challenges


def _translation_challenge_bank() -> list:
    practice = _load_practice_challenges()
    return practice or TRANSLATION_CHALLENGES


def generate_translation_challenge() -> dict:
    """Generate the next strict-mode translation unlock challenge."""
    source_path = _selected_practice_path()
    target_language = get_practice_target_language()
    bank = _translation_challenge_bank()
    is_fallback = bank == TRANSLATION_CHALLENGES
    item_index = _next_practice_index(str(source_path), len(bank)) if not is_fallback else random.randrange(len(bank))
    source_text = bank[item_index]
    return {
        "challenge_id": str(uuid.uuid4())[:8],
        "source_text": source_text,
        "instruction": f"Translate this sentence into {target_language}.",
        "source": str(source_path) if not is_fallback else "built-in",
        "source_name": source_path.name if not is_fallback else "built-in",
        "item_index": item_index,
        "item_total": len(bank),
        "target_language": target_language,
    }


def save_practice_source_file(filename: str, content: str) -> dict:
    """Save an uploaded markdown/text practice file and select it."""
    original_name = Path(filename or "practice.md").name
    suffix = Path(original_name).suffix.lower()
    if suffix not in {".md", ".txt"}:
        raise ValueError("Practice source must be a Markdown or text file.")
    if len(content or "") > 2_000_000:
        raise ValueError("Practice source file is too large.")
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(original_name).stem).strip("._") or "practice"
    target = PRACTICE_DIR / f"{safe_stem}-{uuid.uuid4().hex[:8]}{suffix}"
    target.write_text(content or "", encoding="utf-8")
    settings = save_settings({"practice_source_path": str(target)})
    count = len(_load_practice_challenges())
    return {
        "status": "saved",
        "path": str(target),
        "name": target.name,
        "item_count": count,
        "settings": settings,
    }


def get_practice_status() -> dict:
    source_path = _selected_practice_path()
    challenges = _load_practice_challenges()
    state = _load_practice_state()
    cursor = int(state.get("sources", {}).get(str(source_path), {}).get("cursor", 0))
    return {
        "source_path": str(source_path),
        "source_name": source_path.name,
        "target_language": get_practice_target_language(),
        "item_count": len(challenges),
        "next_index": cursor % len(challenges) if challenges else 0,
        "attempts_path": str(PRACTICE_ATTEMPTS_FILE),
    }


def _selected_practice_path() -> Path:
    value = get_practice_source_path()
    return Path(value).expanduser()


def _load_practice_state() -> dict:
    if PRACTICE_STATE_FILE.exists():
        try:
            with open(PRACTICE_STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)
            if isinstance(state, dict):
                state.setdefault("sources", {})
                return state
        except Exception as e:
            print(f"[quiz_generator] Could not read practice state: {e}")
    return {"sources": {}}


def _save_practice_state(state: dict):
    PRACTICE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PRACTICE_STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def _next_practice_index(source_key: str, total: int) -> int:
    if total <= 0:
        return 0
    state = _load_practice_state()
    source_state = state.setdefault("sources", {}).setdefault(source_key, {"cursor": 0})
    cursor = int(source_state.get("cursor", 0))
    index = cursor % total
    source_state["cursor"] = cursor + 1
    source_state["last_used_at"] = datetime.now().astimezone().isoformat()
    _save_practice_state(state)
    return index


def _looks_like_japanese(value: str) -> bool:
    return any("\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff" for ch in value)


def _looks_like_romaji(value: str, source_text: str) -> bool:
    lowered = value.lower()
    source_words = {word.strip(".,!?;:").lower() for word in source_text.split()}
    answer_words = [word.strip(".,!?;:").lower() for word in lowered.split()]
    japanese_markers = {"watashi", "boku", "ore", "wa", "ga", "wo", "o", "ni", "de", "desu", "masu", "suru", "shimasu", "modoru", "benkyou", "shuchu"}
    return (
        len(answer_words) >= 3
        and any(word in japanese_markers for word in answer_words)
        and not all(word in source_words for word in answer_words)
    )


def record_translation_attempt(challenge: dict, user_answer: str, result: dict):
    entry = {
        "attempt_id": str(uuid.uuid4())[:8],
        "timestamp": datetime.now().astimezone().isoformat(),
        "challenge_id": challenge.get("challenge_id", ""),
        "source_text": challenge.get("source_text", ""),
        "user_answer": user_answer,
        "accepted": bool(result.get("accepted", False)),
        "skipped": bool(result.get("skipped", False)),
        "score": result.get("score", 0),
        "feedback": result.get("feedback", ""),
        "source": challenge.get("source", ""),
        "source_name": challenge.get("source_name", ""),
        "item_index": challenge.get("item_index"),
        "item_total": challenge.get("item_total"),
        "target_language": challenge.get("target_language", get_practice_target_language()),
        "model": result.get("model", ""),
    }
    PRACTICE_ATTEMPTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PRACTICE_ATTEMPTS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def get_practice_attempts(limit: int = 200) -> list:
    if not PRACTICE_ATTEMPTS_FILE.exists():
        return []
    try:
        lines = PRACTICE_ATTEMPTS_FILE.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    attempts = []
    for line in lines[-max(1, int(limit)):]:
        try:
            attempts.append(json.loads(line))
        except Exception:
            continue
    return attempts


def grade_translation_answer(
    source_text: str,
    user_answer: str,
    target_language: str = None,
    challenge: dict = None,
) -> dict:
    """Grade a translation answer with AI when available."""
    answer = (user_answer or "").strip()
    target_language = (target_language or get_practice_target_language()).strip() or "Japanese"
    if not answer:
        result = {"accepted": False, "score": 0, "feedback": "Please enter a translation.", "explanation": "Please enter a translation.", "model_translation": "", "model": "local"}
        if challenge:
            record_translation_attempt(challenge, answer, result)
        return result

    if not has_api_key():
        from mvp_i18n import text
        result = {"accepted": False, "score": 0, "feedback": text("gradingError"), "explanation": text("gradingError"), "model": "api-error"}
        if challenge:
            record_translation_attempt(challenge, answer, result)
        return result

    try:
        response, model = _llm_complete(
            [
                {
                    "role": "user",
                    "content": TRANSLATION_GRADE_PROMPT.format(
                        source_text=source_text,
                        target_language=target_language,
                        user_answer=answer,
                    ) + "\nWrite feedback and explanation in " + _feedback_language() + ".",
                }
            ],
            350,
        )

        result = _parse_llm_json(response)
        if not isinstance(result.get("accepted"), bool):
            raise ValueError("Invalid grading result: accepted must be boolean")
        result["model"] = model
        result.setdefault("model_translation", "")
        result.setdefault("explanation", result.get("feedback", ""))
        if challenge:
            record_translation_attempt(challenge, answer, result)
        return result

    except Exception as e:
        print(f"[quiz_generator] Translation grading error: {e}")
        result = {
            "accepted": False,
            "score": 0,
            "feedback": f"AI grading failed. Please try again. ({e})",
            "model": "api-error",
        }
        if challenge:
            record_translation_attempt(challenge, answer, result)
        return result


def explain_translation(
    source_text: str,
    target_language: str = None,
    challenge: dict = None,
) -> dict:
    """Return a reference translation and teaching notes. Does not count as a pass."""
    target_language = (target_language or get_practice_target_language()).strip() or "Japanese"
    source_text = (source_text or "").strip()
    if not source_text:
        return {
            "accepted": False,
            "skipped": True,
            "score": 0,
            "model_translation": "",
            "explanation": "没有题目文本，无法生成解析。",
            "model": "local",
        }

    result = {
        "accepted": False,
        "skipped": True,
        "score": 0,
        "model_translation": "",
        "explanation": "",
        "model": "local-fallback",
    }

    if not has_api_key():
        result["explanation"] = "当前没有连接模型，无法生成参考译文。请稍后重试，或自己再翻译一次。"
        if challenge:
            record_translation_attempt(challenge, "答不出来", result)
        return result

    try:
        response, model = _llm_complete(
            [
                {
                    "role": "user",
                    "content": TRANSLATION_EXPLAIN_PROMPT.format(
                        source_text=source_text,
                        target_language=target_language,
                    ) + "\nWrite the explanation in " + _feedback_language() + ".",
                }
            ],
            400,
        )
        parsed = _parse_llm_json(response)
        result["model"] = model
        result["model_translation"] = (parsed.get("model_translation") or "").strip()
        result["explanation"] = (parsed.get("explanation") or "").strip()
        if not result["model_translation"]:
            raise ValueError("Missing reference translation")
        if not result["explanation"]:
            result["explanation"] = "请对照参考译文，注意关键词和语序后再做下一题。"
    except Exception as e:
        print(f"[quiz_generator] Translation explain error: {e}")
        result["model"] = "api-error"
        result["explanation"] = f"解析生成失败，请再试一次。({e})"

    if challenge:
        record_translation_attempt(challenge, "答不出来", result)
    return result


def _feedback_language():
    from mvp_i18n import LANGUAGES
    from settings_manager import load_settings
    return LANGUAGES.get(load_settings().get("ui_language"), "Chinese")
