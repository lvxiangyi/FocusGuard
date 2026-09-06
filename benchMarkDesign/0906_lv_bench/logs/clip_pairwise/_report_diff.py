import csv
import json
from pathlib import Path

from benchmark.schema import canonicalize_label
from benchmark.store import BenchmarkStore

ROOT = Path(__file__).resolve().parents[2]
PAIRS = Path(__file__).with_name("pairs.csv")
OUT = Path(__file__).with_name("clip_high_diff_label.csv")
JSON_OUT = Path(__file__).with_name("clip_high_diff_label.json")
CLIP_HIGH = 0.75


def canon(label: str) -> str:
    try:
        return canonicalize_label(label)
    except ValueError:
        return (label or "").strip() or "ambiguous"


def vlm_verdict(human_a: str, human_b: str, ai_a: str, ai_b: str) -> str:
    if ai_a == "ambiguous" or ai_b == "ambiguous":
        return "missing_ai"
    if ai_a == ai_b:
        return "collapsed"
    if ai_a == human_a and ai_b == human_b:
        return "distinguished_correct"
    return "distinguished_partial"


def main() -> None:
    store = BenchmarkStore(ROOT / "data")
    by_id = {sample["id"]: sample for sample in store.list_samples("train")}
    rows = list(csv.DictReader(PAIRS.open(encoding="utf-8")))
    report = []
    for row in rows:
        if row["same_label"] == "1":
            continue
        left = by_id[row["id_a"]]
        right = by_id[row["id_b"]]
        human_a = canon(left.get("human_label") or "")
        human_b = canon(right.get("human_label") or "")
        ai_a = canon(left.get("ai_label") or "")
        ai_b = canon(right.get("ai_label") or "")
        item = {
            "clip_cosine": float(row["clip_cosine"]),
            "phash_sim": float(row["phash_sim"]),
            "short_a": row["short_a"],
            "short_b": row["short_b"],
            "id_a": row["id_a"],
            "id_b": row["id_b"],
            "mode_a": left.get("mode") or "",
            "mode_b": right.get("mode") or "",
            "human_a": human_a,
            "human_b": human_b,
            "ai_a": ai_a,
            "ai_b": ai_b,
            "vlm_same_label": int(ai_a == ai_b),
            "vlm_verdict": vlm_verdict(human_a, human_b, ai_a, ai_b),
            "ai_model_a": left.get("ai_model") or "",
            "ai_model_b": right.get("ai_model") or "",
            "activity_a": (left.get("activity") or "")[:160],
            "activity_b": (right.get("activity") or "")[:160],
        }
        report.append(item)

    report.sort(key=lambda item: -item["clip_cosine"])
    high = [item for item in report if item["clip_cosine"] >= CLIP_HIGH]

    with OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(report[0].keys()))
        writer.writeheader()
        writer.writerows(report)

    counts = {}
    high_counts = {}
    for item in report:
        counts[item["vlm_verdict"]] = counts.get(item["vlm_verdict"], 0) + 1
    for item in high:
        high_counts[item["vlm_verdict"]] = high_counts.get(item["vlm_verdict"], 0) + 1

    payload = {
        "clip_high_threshold": CLIP_HIGH,
        "n_diff_label_pairs": len(report),
        "n_clip_high": len(high),
        "verdict_all": counts,
        "verdict_clip_high": high_counts,
        "high_pairs": high,
    }
    JSON_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: payload[k] for k in payload if k != "high_pairs"}, ensure_ascii=False, indent=2))
    print(f"wrote {OUT} ({len(report)} rows); high>={CLIP_HIGH}: {len(high)}")


if __name__ == "__main__":
    main()
