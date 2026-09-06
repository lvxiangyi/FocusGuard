from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from PIL import Image

from .schema import (
    VALID_SPLITS,
    canonicalize_label,
    coerce_human_label,
    normalize_review_status,
    normalize_source_type,
    normalize_split,
    should_interrupt,
)


def _now() -> str:
    return datetime.now().astimezone().isoformat()


def average_hash_hex(image_path: Path, hash_size: int = 8) -> str:
    with Image.open(image_path) as image:
        pixels = list(
            image.convert("L")
            .resize((hash_size, hash_size), Image.Resampling.LANCZOS)
            .getdata()
        )
    average = sum(pixels) / len(pixels)
    bits = 0
    for index, value in enumerate(pixels):
        if value >= average:
            bits |= 1 << index
    width = (hash_size * hash_size + 3) // 4
    return f"{bits:0{width}x}"


class BenchmarkStore:
    """JSONL metadata plus copied JPEG screenshots under data/train and data/test."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        for split in VALID_SPLITS:
            (self.root / split / "screenshots").mkdir(parents=True, exist_ok=True)
            path = self._samples_path(split)
            if not path.exists():
                path.write_text("", encoding="utf-8")
        self._upgrade_legacy_fields()

    def _samples_path(self, split: str) -> Path:
        return self.root / normalize_split(split) / "samples.jsonl"

    def list_samples(self, split: Optional[str] = None) -> list[dict]:
        splits = [normalize_split(split)] if split else sorted(VALID_SPLITS)
        result: list[dict] = []
        for current_split in splits:
            path = self._samples_path(current_split)
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    sample = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(sample, dict) or not sample.get("id"):
                    continue
                sample["split"] = current_split
                sample["dataset_role"] = "calibration" if current_split == "train" else "test"
                if not sample.get("source_type"):
                    source = sample.get("source") or ""
                    sample["source_type"] = "history_import" if "history" in source else "manual_seed"
                if not sample.get("review_status"):
                    sample["review_status"] = "reviewed"
                try:
                    sample["human_label"] = canonicalize_label(
                        sample.get("human_label") or sample.get("ai_label") or ""
                    )
                    if sample.get("ai_label"):
                        sample["ai_label"] = canonicalize_label(sample.get("ai_label") or "")
                except ValueError:
                    pass
                if sample.get("human_label") and sample["human_label"] != "ambiguous":
                    sample["supervision_level"] = sample["human_label"]
                sample["should_interrupt"] = should_interrupt(
                    sample.get("mode") or "",
                    sample.get("human_label") or "",
                )
                result.append(sample)
        result.sort(
            key=lambda item: item.get("added_at") or item.get("captured_at") or "",
            reverse=True,
        )
        return result

    def get(self, sample_id: str) -> Optional[dict]:
        return next((s for s in self.list_samples() if s.get("id") == sample_id), None)

    def screenshot_path(self, sample: dict) -> Path:
        split = normalize_split(sample.get("split") or "")
        relative = sample.get("screenshot_relpath") or f"screenshots/{sample['id']}.jpg"
        path = (self.root / split / relative).resolve()
        split_root = (self.root / split).resolve()
        if split_root not in path.parents:
            raise ValueError("Screenshot path escapes its split directory")
        return path

    def add_sample(
        self,
        *,
        source_image: Path,
        mode: str,
        human_label: str,
        split: str = "train",
        task: str = "",
        supervision_level: Optional[str] = None,
        human_reason: str = "",
        activity: str = "",
        window_title: str = "",
        ai_label: str = "",
        ai_reason: str = "",
        ai_model: str = "",
        ai_confidence: Optional[float] = None,
        judgement_status: str = "",
        trigger_category: str = "",
        prompt_version: str = "",
        retriever_version: str = "",
        source_screenshot_path: str = "",
        source: str = "manual_capture",
        source_type: str = "manual_seed",
        review_status: str = "reviewed",
        captured_at: Optional[str] = None,
        sample_id: Optional[str] = None,
    ) -> dict:
        mode = (mode or "").strip().lower()
        split = normalize_split(split)
        human_label = coerce_human_label(mode, ai_label, human_label)
        ai_label = canonicalize_label(ai_label) if (ai_label or "").strip() else ""
        source_type = normalize_source_type(source_type)
        review_status = normalize_review_status(review_status)
        supervision_level = None if human_label == "ambiguous" else human_label
        task = (task or "").strip()
        if mode == "guardian":
            task = ""
        elif not task:
            raise ValueError("Session samples require a task")

        source_image = Path(source_image)
        if not source_image.is_file():
            raise FileNotFoundError(f"Screenshot not found: {source_image}")

        sample_id = sample_id or str(uuid.uuid4())
        relative = f"screenshots/{sample_id}.jpg"
        destination = self.root / split / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_image, destination)

        sample = {
            "schema_version": 1,
            "id": sample_id,
            "split": split,
            "dataset_role": "calibration" if split == "train" else "test",
            "source_type": source_type,
            "review_status": review_status,
            "mode": mode,
            "task": task,
            "supervision_level": supervision_level,
            "human_label": human_label,
            "human_reason": (human_reason or "").strip(),
            "activity": (activity or "").strip(),
            "window_title": (window_title or "").strip(),
            "ai_label": (ai_label or "").strip(),
            "ai_reason": (ai_reason or "").strip(),
            "ai_model": (ai_model or "").strip(),
            "ai_confidence": ai_confidence,
            "judgement_status": (judgement_status or "").strip(),
            "trigger_category": (trigger_category or "").strip(),
            "prompt_version": (prompt_version or "").strip(),
            "retriever_version": (retriever_version or "").strip(),
            "captured_at": captured_at or _now(),
            "added_at": _now(),
            "source": (source or "manual_capture").strip(),
            "source_screenshot_path": (source_screenshot_path or "").strip(),
            "screenshot_relpath": relative,
            "image_hash": average_hash_hex(destination),
            "retrieval_history": [],
            "should_interrupt": should_interrupt(mode, human_label),
        }
        with self._samples_path(split).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(sample, ensure_ascii=False) + "\n")
        return sample

    def update(self, sample_id: str, updates: dict) -> dict:
        sample = self.get(sample_id)
        if not sample:
            raise KeyError(sample_id)
        split = sample["split"]
        allowed = {
            "mode", "task", "supervision_level", "human_label", "human_reason",
            "activity", "window_title", "ai_label", "ai_reason", "ai_model",
            "ai_confidence", "judgement_status", "trigger_category",
            "prompt_version", "retriever_version", "source_type", "review_status",
        }
        merged = dict(sample)
        for key, value in updates.items():
            if key in allowed:
                merged[key] = value.strip() if isinstance(value, str) else value
        merged["mode"] = (merged.get("mode") or "").strip().lower()
        merged["human_label"] = coerce_human_label(
            merged["mode"],
            merged.get("ai_label") or "",
            merged.get("human_label") or "",
        )
        if merged.get("ai_label"):
            merged["ai_label"] = canonicalize_label(merged.get("ai_label") or "")
        merged["supervision_level"] = None if merged["human_label"] == "ambiguous" else merged["human_label"]
        merged["should_interrupt"] = should_interrupt(merged["mode"], merged["human_label"])
        merged["source_type"] = normalize_source_type(merged.get("source_type") or "")
        merged["review_status"] = normalize_review_status(merged.get("review_status") or "")
        if merged["mode"] == "guardian":
            merged["task"] = ""
        elif not (merged.get("task") or "").strip():
            raise ValueError("Session samples require a task")
        merged["updated_at"] = _now()
        items = [merged if item.get("id") == sample_id else item for item in self.list_samples(split)]
        self._rewrite(split, items)
        return merged

    def delete(self, sample_id: str) -> bool:
        sample = self.get(sample_id)
        if not sample:
            return False
        split = sample["split"]
        remaining = [s for s in self.list_samples(split) if s.get("id") != sample_id]
        self._rewrite(split, remaining)
        image = self.screenshot_path(sample)
        if image.exists():
            image.unlink()
        return True

    def move(self, sample_id: str, new_split: str) -> dict:
        new_split = normalize_split(new_split)
        sample = self.get(sample_id)
        if not sample:
            raise KeyError(sample_id)
        if sample["split"] == new_split:
            return sample

        old_split = sample["split"]
        old_image = self.screenshot_path(sample)
        new_image = self.root / new_split / "screenshots" / old_image.name
        if not old_image.is_file():
            raise FileNotFoundError(f"Screenshot not found: {old_image}")
        shutil.copy2(old_image, new_image)

        moved = dict(sample)
        moved["split"] = new_split
        moved["dataset_role"] = "calibration" if new_split == "train" else "test"
        moved["screenshot_relpath"] = f"screenshots/{new_image.name}"
        moved["added_at"] = _now()
        with self._samples_path(new_split).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(moved, ensure_ascii=False) + "\n")
        self._rewrite(old_split, [s for s in self.list_samples(old_split) if s["id"] != sample_id])
        old_image.unlink(missing_ok=True)
        return moved

    def _upgrade_legacy_fields(self) -> None:
        for split in VALID_SPLITS:
            path = self._samples_path(split)
            if not path.exists() or not path.read_text(encoding="utf-8").strip():
                continue
            samples = self.list_samples(split)
            changed = False
            upgraded = []
            for sample in samples:
                row = dict(sample)
                old_label = row.get("human_label")
                old_ai = row.get("ai_label")
                old_level = row.get("supervision_level")
                try:
                    incoming_label = (
                        ""
                        if old_label in {None, "", "ambiguous"}
                        else old_label
                    )
                    row["human_label"] = coerce_human_label(
                        row.get("mode") or "",
                        old_ai or "",
                        incoming_label or "",
                    )
                    if old_ai:
                        row["ai_label"] = canonicalize_label(old_ai)
                    row["supervision_level"] = (
                        None if row["human_label"] == "ambiguous" else row["human_label"]
                    )
                    row["should_interrupt"] = should_interrupt(
                        row.get("mode") or "",
                        row["human_label"],
                    )
                except ValueError:
                    upgraded.append(sample)
                    continue
                if (
                    row["human_label"] != old_label
                    or row.get("ai_label") != old_ai
                    or row.get("supervision_level") != old_level
                ):
                    changed = True
                upgraded.append(row)
            if changed:
                self._rewrite(split, upgraded)

    def _rewrite(self, split: str, samples: Iterable[dict]) -> None:
        path = self._samples_path(split)
        temporary = path.with_suffix(".jsonl.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            for sample in samples:
                row = dict(sample)
                row["split"] = split
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.replace(temporary, path)
