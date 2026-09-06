from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
import threading
from functools import wraps
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from personal_bench.image_hash import average_hash_hex
from personal_bench.schema import VALID_SPLITS, normalize_label_for_mode


_STORE_LOCK = threading.RLock()

def _locked(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        with _STORE_LOCK:
            return fn(*args, **kwargs)
    return wrapped


def default_bench_root() -> Path:
    env = os.getenv("PERSONAL_BENCH_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    try:
        from data_paths import PERSONAL_BENCH_DIR
        return Path(PERSONAL_BENCH_DIR)
    except Exception:
        return Path(__file__).resolve().parent.parent.parent / "data" / "dev" / "personal_bench"


def _now() -> str:
    return datetime.now().astimezone().isoformat()


class BenchStore:
    """JSONL + screenshot files under data/{train,test}/."""

    @_locked
    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root else default_bench_root()
        for split in VALID_SPLITS:
            (self.root / split / "screenshots").mkdir(parents=True, exist_ok=True)
            samples = self._samples_path(split)
            if not samples.exists():
                samples.write_text("", encoding="utf-8")

    def _split_dir(self, split: str) -> Path:
        if split not in VALID_SPLITS:
            raise ValueError(f"Invalid split: {split}")
        return self.root / split

    def _samples_path(self, split: str) -> Path:
        return self._split_dir(split) / "samples.jsonl"

    @_locked
    def list_samples(self, split: Optional[str] = None) -> list[dict]:
        splits = [split] if split else sorted(VALID_SPLITS)
        out: list[dict] = []
        for s in splits:
            path = self._samples_path(s)
            if not path.exists():
                continue
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    item["split"] = s
                    out.append(item)
        out.sort(key=lambda x: x.get("added_at") or x.get("captured_at") or "", reverse=True)
        return out

    def get(self, sample_id: str) -> Optional[dict]:
        for item in self.list_samples():
            if item.get("id") == sample_id:
                return item
        return None

    def screenshot_path(self, sample: dict) -> Path:
        split = sample["split"]
        rel = sample.get("screenshot_relpath") or f"screenshots/{sample['id']}.jpg"
        return (self._split_dir(split) / rel).resolve()

    @_locked
    def add_sample(
        self,
        *,
        mode: str,
        human_label: str,
        source_image: Path,
        split: str = "train",
        task: str = "",
        supervision_level: Optional[str] = None,
        human_reason: str = "",
        ai_activity: str = "",
        ai_reason: str = "",
        ai_label: str = "",
        captured_at: Optional[str] = None,
        source: str = "manual",
        sample_id: Optional[str] = None,
    ) -> dict:
        split = (split or "train").strip().lower()
        if split not in VALID_SPLITS:
            raise ValueError(f"Invalid split: {split}")
        mode = (mode or "").strip().lower()
        human_label = normalize_label_for_mode(mode, human_label)
        if mode == "guardian":
            task = ""
        else:
            task = (task or "").strip()
            if not task:
                raise ValueError("Session samples require a non-empty task.")

        source_image = Path(source_image)
        if not source_image.exists():
            raise FileNotFoundError(f"Screenshot not found: {source_image}")

        sample_id = sample_id or str(uuid.uuid4())
        rel = f"screenshots/{sample_id}.jpg"
        dest = self._split_dir(split) / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_image, dest)

        try:
            image_hash = average_hash_hex(dest)
        except Exception:
            image_hash = hashlib.md5(dest.read_bytes()).hexdigest()[:16]

        sample = {
            "id": sample_id,
            "split": split,
            "mode": mode,
            "task": task,
            "supervision_level": supervision_level,
            "human_label": human_label,
            "human_reason": (human_reason or "").strip(),
            "ai_activity": (ai_activity or "").strip(),
            "ai_reason": (ai_reason or "").strip(),
            "ai_label": (ai_label or "").strip(),
            "captured_at": captured_at or _now(),
            "added_at": _now(),
            "screenshot_relpath": rel.replace("\\", "/"),
            "source": source,
            "image_hash": image_hash,
        }
        with open(self._samples_path(split), "a", encoding="utf-8") as f:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
        return sample

    @_locked
    def delete_sample(self, sample_id: str, delete_image: bool = True) -> bool:
        found = None
        for split in VALID_SPLITS:
            items = self.list_samples(split)
            keep = []
            for item in items:
                if item.get("id") == sample_id:
                    found = item
                else:
                    keep.append(item)
            if found and found.get("split") == split:
                self._rewrite(split, keep)
                if delete_image:
                    path = self.screenshot_path(found)
                    if path.exists():
                        path.unlink()
                return True
        return False

    @_locked
    def move_split(self, sample_id: str, new_split: str) -> dict:
        new_split = (new_split or "").strip().lower()
        if new_split not in VALID_SPLITS:
            raise ValueError(f"Invalid split: {new_split}")
        sample = self.get(sample_id)
        if not sample:
            raise KeyError(sample_id)
        if sample["split"] == new_split:
            return sample

        old_image = self.screenshot_path(sample)
        old_split = sample["split"]
        rel = sample.get("screenshot_relpath") or f"screenshots/{sample_id}.jpg"
        dest = self._split_dir(new_split) / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if old_image.exists():
            shutil.copy2(old_image, dest)
        elif not dest.exists():
            raise FileNotFoundError(f"Screenshot not found: {old_image}")

        moved = dict(sample)
        moved["split"] = new_split
        moved["added_at"] = _now()
        with open(self._samples_path(new_split), "a", encoding="utf-8") as f:
            f.write(json.dumps(moved, ensure_ascii=False) + "\n")
        remaining = [s for s in self.list_samples(old_split) if s.get("id") != sample_id]
        self._rewrite(old_split, remaining)
        if old_image.exists() and dest.exists() and old_image.resolve() != dest.resolve():
            try:
                old_image.unlink()
            except OSError:
                pass
        return moved

    def _rewrite(self, split: str, samples: Iterable[dict]) -> None:
        path = self._samples_path(split)
        tmp = path.with_suffix(".jsonl.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for item in samples:
                row = dict(item)
                row["split"] = split
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
