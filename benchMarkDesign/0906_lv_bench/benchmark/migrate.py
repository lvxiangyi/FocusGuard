from __future__ import annotations

import json
from pathlib import Path

from .store import BenchmarkStore


def import_legacy_data(store: BenchmarkStore, legacy_roots: list[Path]) -> dict:
    """Copy valid 0825 samples once. Existing IDs and missing images are skipped."""
    existing_ids = {sample["id"] for sample in store.list_samples()}
    imported = 0
    skipped = 0
    for root in legacy_roots:
        root = Path(root)
        for split in ("train", "test"):
            index = root / split / "samples.jsonl"
            if not index.is_file():
                continue
            for line in index.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    sample_id = row.get("id")
                    image = root / split / (row.get("screenshot_relpath") or f"screenshots/{sample_id}.jpg")
                    if not sample_id or sample_id in existing_ids or not image.is_file():
                        skipped += 1
                        continue
                    store.add_sample(
                        source_image=image,
                        mode=row.get("mode") or "guardian",
                        human_label=row.get("human_label") or "ambiguous",
                        split=split,
                        task=row.get("task") or "",
                        supervision_level=row.get("supervision_level"),
                        human_reason=row.get("human_reason") or "",
                        activity=row.get("activity") or row.get("ai_activity") or "",
                        window_title=row.get("window_title") or "",
                        ai_label=row.get("ai_label") or "",
                        ai_reason=row.get("ai_reason") or "",
                        ai_model=row.get("ai_model") or row.get("model") or "",
                        ai_confidence=row.get("ai_confidence") or row.get("confidence"),
                        judgement_status=row.get("judgement_status") or "",
                        trigger_category=row.get("trigger_category") or "",
                        prompt_version=row.get("prompt_version") or "",
                        retriever_version=row.get("retriever_version") or "",
                        source_screenshot_path=str(image),
                        captured_at=row.get("captured_at"),
                        source=f"legacy:{root.name}",
                        source_type=row.get("source_type") or "manual_seed",
                        review_status=row.get("review_status") or (
                            "pending" if row.get("human_label") == "ambiguous" else "reviewed"
                        ),
                        sample_id=sample_id,
                    )
                    existing_ids.add(sample_id)
                    imported += 1
                except Exception:
                    skipped += 1
    return {"imported": imported, "skipped": skipped}
