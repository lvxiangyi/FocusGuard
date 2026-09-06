from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Union

from personal_bench.image_hash import average_hash_hex, hash_similarity
from personal_bench.store import BenchStore

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def tokenize(text: str) -> set[str]:
    return {t.casefold() for t in _TOKEN_RE.findall(text or "") if t.strip()}


def text_similarity(a: str, b: str) -> float:
    ta, tb = tokenize(a), tokenize(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _sample_text(sample: dict) -> str:
    return " ".join(
        [
            sample.get("task") or "",
            sample.get("ai_activity") or "",
            sample.get("human_reason") or "",
            sample.get("ai_reason") or "",
        ]
    )


def _query_text(task: str, ai_activity: str, human_reason: str = "", ai_reason: str = "") -> str:
    return " ".join([task or "", ai_activity or "", human_reason or "", ai_reason or ""])


def score_pair(
    query: dict,
    candidate: dict,
    *,
    text_weight: float = 0.55,
    image_weight: float = 0.45,
) -> float:
    t = text_similarity(_sample_text(query), _sample_text(candidate))
    i = hash_similarity(query.get("image_hash") or "", candidate.get("image_hash") or "")
    return text_weight * t + image_weight * i


def retrieve_similar(
    store: BenchStore,
    *,
    mode: str,
    task: str = "",
    ai_activity: str = "",
    ai_reason: str = "",
    human_reason: str = "",
    image_path: Optional[Union[str, Path]] = None,
    image_hash: Optional[str] = None,
    k: int = 3,
    exclude_id: Optional[str] = None,
    text_weight: float = 0.55,
    image_weight: float = 0.45,
    min_score: Optional[float] = None,
) -> list[dict]:
    """Retrieve Top-K train samples. Never searches test."""
    mode = (mode or "").strip().lower()
    task_norm = (task or "").strip().casefold()
    if image_hash is None and image_path:
        try:
            image_hash = average_hash_hex(image_path)
        except Exception:
            image_hash = ""

    query = {
        "task": task if mode == "session" else "",
        "ai_activity": ai_activity or "",
        "human_reason": human_reason or "",
        "ai_reason": ai_reason or "",
        "image_hash": image_hash or "",
    }
    image_only = not tokenize(_sample_text(query))
    if image_only:
        text_weight, image_weight = 0.0, 1.0
    if min_score is None:
        min_score = 0.6 if image_only else 0.32

    corpus = [
        s
        for s in store.list_samples("train")
        if s.get("mode") == mode and s.get("id") != exclude_id
    ]
    if not corpus:
        return []

    same_task: list[dict] = []
    other: list[dict] = []
    for sample in corpus:
        if mode == "session" and task_norm:
            if (sample.get("task") or "").strip().casefold() == task_norm:
                same_task.append(sample)
            else:
                other.append(sample)
        else:
            same_task.append(sample)

    def rank(pool: list[dict]) -> list[tuple[float, dict]]:
        ranked = []
        for sample in pool:
            ranked.append((score_pair(query, sample, text_weight=text_weight, image_weight=image_weight), sample))
        ranked.sort(key=lambda x: x[0], reverse=True)
        return ranked

    picked: list[dict] = []
    for index, (score, sample) in enumerate(rank(same_task)):
        # Session same-task examples are user calibration for this task.
        # Judge-time queries have no activity text, so Jaccard against the
        # sample's long reason is weak; always keep the best same-task hit.
        floor = min_score
        if mode == "session" and task_norm and index == 0:
            floor = 0.0
        if score < floor:
            continue
        item = dict(sample)
        item["retrieval_score"] = round(score, 4)
        item["retrieval_bucket"] = "same_task" if mode == "session" and task_norm else "mode"
        picked.append(item)
        if len(picked) >= k:
            return picked

    if mode == "session" and other:
        for score, sample in rank(other):
            if score < min_score:
                continue
            item = dict(sample)
            item["retrieval_score"] = round(score, 4)
            item["retrieval_bucket"] = "other_task"
            picked.append(item)
            if len(picked) >= k:
                break

    return picked
