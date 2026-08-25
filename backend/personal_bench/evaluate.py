from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from personal_bench.inject import format_precedents_block
from personal_bench.retrieve import retrieve_similar
from personal_bench.schema import labels_match
from personal_bench.store import BenchStore


JudgeFn = Callable[[dict, str], str]
"""(test_sample, precedents_block) -> predicted label string."""


@dataclass
class EvalResult:
    total: int
    scored: int
    correct: int
    accuracy: float
    skipped_ambiguous: int
    details: list[dict]


def evaluate_test_set(
    store: BenchStore,
    judge_fn: JudgeFn,
    *,
    k: int = 3,
    mode: Optional[str] = None,
) -> EvalResult:
    """
    For each test sample: retrieve from TRAIN only, inject precedents, call judge_fn.
    Accuracy ignores human_label == ambiguous.
    """
    tests = store.list_samples("test")
    if mode:
        tests = [t for t in tests if t.get("mode") == mode]

    details = []
    correct = 0
    scored = 0
    skipped = 0

    for sample in tests:
        human = (sample.get("human_label") or "").strip().lower()
        if human == "ambiguous":
            skipped += 1
            details.append({"id": sample["id"], "skipped": True, "reason": "ambiguous"})
            continue

        hits = retrieve_similar(
            store,
            mode=sample.get("mode") or "session",
            task=sample.get("task") or "",
            ai_activity=sample.get("ai_activity") or "",
            ai_reason=sample.get("ai_reason") or "",
            image_hash=sample.get("image_hash"),
            k=k,
            exclude_id=sample.get("id"),
        )
        block = format_precedents_block(hits, max_items=k)
        predicted = (judge_fn(sample, block) or "").strip().lower()
        ok = labels_match(human, predicted)
        scored += 1
        if ok:
            correct += 1
        details.append(
            {
                "id": sample["id"],
                "mode": sample.get("mode"),
                "human_label": human,
                "predicted": predicted,
                "correct": ok,
                "retrieved_ids": [h.get("id") for h in hits],
            }
        )

    accuracy = (correct / scored) if scored else 0.0
    return EvalResult(
        total=len(tests),
        scored=scored,
        correct=correct,
        accuracy=accuracy,
        skipped_ambiguous=skipped,
        details=details,
    )
