"""Import historical AIMonitor screenshots and their log context into this benchmark."""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from pathlib import Path

from benchmark.store import BenchmarkStore, average_hash_hex

ROOT = Path(__file__).resolve().parent


def _default_history_root() -> Path:
    nested = ROOT.parents[1] / "data" / "prod"
    sibling = ROOT.parents[1] / "AIMonitor" / "data" / "prod"
    if nested.is_dir():
        return nested
    return sibling


DEFAULT_DATA_ROOT = _default_history_root()
DEFAULT_BENCH_ROOT = ROOT / "data"


def _read_jsonl(path: Path) -> list[dict]:
    rows = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _resolve_image(data_root: Path, mode: str, raw_path: str) -> Path | None:
    if not raw_path:
        return None
    raw = Path(raw_path)
    candidates = [raw] if raw.is_absolute() else []
    if mode == "guardian":
        candidates.extend([data_root / "guardian" / raw, data_root / raw])
    else:
        candidates.extend([data_root / raw, data_root / "screenshots" / raw.name])
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate.resolve()
        except OSError:
            pass
    return None


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hamming_bits(value: int) -> int:
    # Python 3.9 has no int.bit_count(); keep one implementation for all versions.
    return bin(value).count("1")


def hash_similarity(left: str, right: str) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    bits = len(left) * 4
    xor = int(left, 16) ^ int(right, 16)
    return 1.0 - _hamming_bits(xor) / bits


_SCENE_RULES = (
    ("adult", ("adult", "nsfw", "porn", "age verification")),
    ("manga", ("manga", "comic")),
    ("novel", ("novel", "webnovel", "web novel", "reading a novel")),
    ("game", ("playing a", "video game", "game stream", "kart racing", "baldur", "expedition 33", "gameplay")),
    ("youtube", ("youtube", "watching a video", "watching a youtube")),
    ("spotify", ("spotify", "listening to music")),
    ("zoom", ("zoom",)),
    ("ide", ("cursor", "vs code", "vscode", "code editor", "ide", "terminal logs", "development environment")),
    ("satellite", ("satellite", "remote sensing", "disaster", "hurricane", "tornado", "volcano", "sar ")),
    ("email", ("gmail", "email", "inbox")),
    ("desktop", ("desktop", "wallpaper")),
    ("chatgpt", ("chatgpt",)),
    ("openrouter", ("openrouter", "api key", "api keys")),
    ("social", ("social media", "twitter", "weibo")),
    ("shopping", ("shopping", "amazon")),
    ("maps", ("map", "openstreetmap")),
    ("slides", ("presentation", "slide", "ppt")),
    ("files", ("file explorer", "file manager", "zip files")),
    ("search", ("google search", "searching google", "google homepage", "search page", "searching for")),
    ("blocker", ("focusguard", "distraction detected", "strict mode", "focus mode")),
    ("docs", ("google docs", "document titled", "worksheet", "reading a document", "reading document", "technical document", "technical documentation")),
    ("github", ("github",)),
    ("leetcode", ("leetcode",)),
    ("news", ("news.qq", "article about", "zenn.dev")),
    ("translation", ("translation", "japanese text")),
    ("notion", ("notion",)),
    ("overleaf", ("overleaf", "resume")),
    ("music_score", ("sheet music",)),
    ("coding", ("coding", "writing code", "reviewing code", "running script")),
)


def scene_bucket(item: dict) -> str:
    trigger = (item.get("trigger_category") or "").strip().casefold()
    if trigger and trigger not in {"none"}:
        return f"trigger:{trigger}"
    text = " ".join(
        str(item.get(key) or "")
        for key in ("activity", "task", "ai_reason")
    ).casefold()
    for name, needles in _SCENE_RULES:
        if any(needle in text for needle in needles):
            return name
    tokens = [token for token in (item.get("activity") or "").casefold().split() if len(token) > 3][:3]
    return "other:" + " ".join(tokens) if tokens else "other"


def load_candidates(data_root: Path) -> list[dict]:
    candidates = []
    sources = [
        ("guardian", data_root / "guardian" / "guardian_logs.jsonl"),
        ("session", data_root / "logs" / "session_logs.jsonl"),
    ]
    for mode, log_path in sources:
        for row in _read_jsonl(log_path):
            if row.get("judgement_status") == "api_error":
                continue
            activity = row.get("current_activity") or ""
            if any(marker in activity for marker in ("取得できません", "unlock screen")):
                continue
            image = _resolve_image(data_root, mode, row.get("screenshot_path") or "")
            if not image:
                continue
            if mode == "guardian":
                ai_label = "interrupt" if row.get("should_interrupt") else "allow"
                captured_at = row.get("checked_at") or row.get("timestamp") or ""
            else:
                ai_label = "on_task" if row.get("on_task") else "off_task"
                captured_at = row.get("timestamp") or ""
            candidates.append(
                {
                    "mode": mode,
                    "image": image,
                    "captured_at": captured_at,
                    "task": row.get("task") or "",
                    "supervision_level": row.get("supervision_level"),
                    "activity": row.get("current_activity") or "",
                    "ai_label": ai_label,
                    "ai_reason": row.get("reason") or "",
                    "ai_model": row.get("model") or "",
                    "ai_confidence": row.get("confidence"),
                    "judgement_status": row.get("judgement_status") or "ok",
                    "trigger_category": row.get("trigger_category") or "",
                    "raw_path": row.get("screenshot_path") or "",
                }
            )
    candidates.sort(key=lambda item: item["captured_at"], reverse=True)
    return candidates


def _time_spread(items: list[dict], count: int) -> list[dict]:
    if count <= 0 or not items:
        return []
    if len(items) <= count:
        return list(items)
    if count == 1:
        return [items[0]]
    step = (len(items) - 1) / (count - 1)
    chosen = []
    seen_indexes = set()
    for index in range(count):
        position = round(index * step)
        if position in seen_indexes:
            continue
        seen_indexes.add(position)
        chosen.append(items[position])
    return chosen


def select_candidates(
    candidates: list[dict],
    limit: int,
    interrupt_quota: int,
    checksum_of=None,
    hash_of=None,
    per_bucket: int = 3,
    min_session: int = 12,
) -> list[dict]:
    checksum_of = checksum_of or (lambda item: _file_sha256(item["image"]))
    hash_of = hash_of or (lambda item: average_hash_hex(item["image"]))

    selected: list[dict] = []
    seen_content: set[str] = set()
    selected_hashes: list[str] = []
    bucket_counts: dict[str, int] = {}

    def accept(item: dict, max_similarity: float, bucket_limit: int) -> bool:
        bucket = scene_bucket(item)
        if bucket_counts.get(bucket, 0) >= bucket_limit:
            return False
        checksum = checksum_of(item)
        if checksum in seen_content:
            return False
        image_hash = hash_of(item)
        if selected_hashes and max(hash_similarity(image_hash, old) for old in selected_hashes) > max_similarity:
            return False
        seen_content.add(checksum)
        selected_hashes.append(image_hash)
        selected.append(item)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
        return True

    def take(pool: list[dict], count: int, bucket_limit: int) -> None:
        groups: dict[str, list[dict]] = {}
        for item in pool:
            groups.setdefault(scene_bucket(item), []).append(item)
        reduced = {
            bucket: _time_spread(items, 16)
            for bucket, items in groups.items()
        }
        for max_similarity in (0.78, 0.86, 0.93, 1.01):
            progressed = True
            while count > 0 and progressed:
                progressed = False
                for bucket in sorted(reduced, key=lambda name: (bucket_counts.get(name, 0), name)):
                    if count <= 0:
                        break
                    for item in reduced[bucket]:
                        if item in selected:
                            continue
                        if accept(item, max_similarity, bucket_limit):
                            count -= 1
                            progressed = True
                            break

    interruptions = [item for item in candidates if item["ai_label"] in {"interrupt", "off_task"}]
    allowed = [item for item in candidates if item["ai_label"] in {"allow", "on_task"}]
    session_pool = [item for item in candidates if item["mode"] == "session"]
    take(interruptions, min(interrupt_quota, limit), per_bucket)
    session_so_far = sum(1 for item in selected if item["mode"] == "session")
    session_needed = max(0, min(min_session, limit) - session_so_far)
    allow_slots = max(0, limit - len(selected) - session_needed)
    take(allowed, allow_slots, per_bucket)
    take(session_pool, min(session_needed, limit - len(selected)), per_bucket)
    if len(selected) < limit:
        take(candidates, limit - len(selected), per_bucket + 1)
    selected.sort(key=lambda item: item["captured_at"], reverse=True)
    return selected[:limit]


def import_history(
    data_root: Path,
    bench_root: Path,
    limit: int,
    interrupt_quota: int,
    replace_imported: bool = False,
) -> dict:
    store = BenchmarkStore(bench_root)
    # Finish all expensive reads and diversity selection before replacing data,
    # so a selection failure cannot leave the benchmark half-migrated.
    selected = select_candidates(load_candidates(data_root), limit, interrupt_quota)
    removed = 0
    if replace_imported:
        imported_ids = [
            sample["id"] for sample in store.list_samples()
            if sample.get("source_type") == "history_import" or sample.get("source") == "aimonitor_history"
        ]
        for sample_id in imported_ids:
            if store.delete(sample_id):
                removed += 1
    existing_ids = {sample["id"] for sample in store.list_samples()}
    imported = 0
    skipped = 0
    labels: dict[str, int] = {}
    for item in selected:
        stable_key = f"{item['mode']}|{item['captured_at']}|{item['raw_path']}"
        sample_id = str(uuid.uuid5(uuid.NAMESPACE_URL, stable_key))
        if sample_id in existing_ids:
            skipped += 1
            continue
        store.add_sample(
            source_image=item["image"],
            mode=item["mode"],
            human_label=item["ai_label"],
            split="test",
            task=item["task"],
            supervision_level=None,
            human_reason="",
            activity=item["activity"],
            ai_label=item["ai_label"],
            ai_reason=item["ai_reason"],
            ai_model=item["ai_model"],
            ai_confidence=item["ai_confidence"],
            judgement_status=item["judgement_status"],
            trigger_category=item["trigger_category"],
            captured_at=item["captured_at"],
            source="aimonitor_history",
            source_type="history_import",
            review_status="reviewed",
            source_screenshot_path=item["raw_path"],
            sample_id=sample_id,
        )
        existing_ids.add(sample_id)
        imported += 1
        labels[item["ai_label"]] = labels.get(item["ai_label"], 0) + 1
    scenes: dict[str, int] = {}
    modes: dict[str, int] = {}
    for item in selected:
        bucket = scene_bucket(item)
        scenes[bucket] = scenes.get(bucket, 0) + 1
        modes[item["mode"]] = modes.get(item["mode"], 0) + 1
    return {
        "requested": limit,
        "selected": len(selected),
        "removed_previous_imports": removed,
        "imported": imported,
        "skipped": skipped,
        "ai_labels": labels,
        "modes": modes,
        "scenes": dict(sorted(scenes.items(), key=lambda item: (-item[1], item[0]))),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--interrupt-quota", type=int, default=12)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--bench-root", type=Path, default=DEFAULT_BENCH_ROOT)
    parser.add_argument("--replace-imported", action="store_true")
    args = parser.parse_args()
    result = import_history(
        args.data_root.resolve(),
        args.bench_root.resolve(),
        args.limit,
        args.interrupt_quota,
        replace_imported=args.replace_imported,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
