"""Pairwise CLIP image cosine + pHash on bench train screenshots.

Uses OpenAI CLIP ViT-B/32. Does not change the live judge or bench server.
Run with the isolated .venv_clip, not the FastAPI venv.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from benchmark.store import BenchmarkStore
from import_history import hash_similarity

ROOT = Path(__file__).resolve().parent
DEFAULT_DATA_ROOT = ROOT / "data"
DEFAULT_OUT_DIR = ROOT / "logs" / "clip_pairwise"
CLIP_MODEL_ID = "openai/clip-vit-base-patch32"


def short_id(sample_id: str) -> str:
    return (sample_id or "")[:8]


def load_split_samples(store: BenchmarkStore, split: str) -> list[dict]:
    samples = []
    for sample in store.list_samples(split):
        path = store.screenshot_path(sample)
        if not path.is_file():
            raise FileNotFoundError(f"Missing screenshot for {sample.get('id')}: {path}")
        samples.append(sample)
    samples.sort(key=lambda item: item.get("id") or "")
    return samples


def phash_matrix(samples: list[dict]) -> list[list[float]]:
    hashes = [str(sample.get("image_hash") or "") for sample in samples]
    size = len(samples)
    matrix = [[0.0] * size for _ in range(size)]
    for i in range(size):
        matrix[i][i] = 1.0
        for j in range(i + 1, size):
            score = hash_similarity(hashes[i], hashes[j])
            matrix[i][j] = score
            matrix[j][i] = score
    return matrix


def clip_matrix(image_paths: list[Path], device: str, batch_size: int) -> list[list[float]]:
    import torch
    from PIL import Image
    from transformers import CLIPModel, CLIPProcessor

    model = CLIPModel.from_pretrained(CLIP_MODEL_ID)
    processor = CLIPProcessor.from_pretrained(CLIP_MODEL_ID)
    model.to(device)
    model.eval()

    vectors = []
    with torch.no_grad():
        for start in range(0, len(image_paths), batch_size):
            chunk = []
            for path in image_paths[start : start + batch_size]:
                with Image.open(path) as image:
                    chunk.append(image.convert("RGB"))
            inputs = processor(images=chunk, return_tensors="pt")
            inputs = {key: value.to(device) for key, value in inputs.items()}
            features = model.get_image_features(**inputs)
            features = features / features.norm(dim=-1, keepdim=True)
            vectors.append(features.cpu())
    stacked = torch.cat(vectors, dim=0)
    similarity = stacked @ stacked.T
    return [[float(value) for value in row] for row in similarity.tolist()]


def build_pair_rows(
    samples: list[dict],
    clip_scores: list[list[float]],
    phash_scores: list[list[float]],
) -> list[dict]:
    rows = []
    for i in range(len(samples)):
        left = samples[i]
        for j in range(i + 1, len(samples)):
            right = samples[j]
            clip_score = clip_scores[i][j]
            phash_score = phash_scores[i][j]
            label_left = left.get("human_label") or ""
            label_right = right.get("human_label") or ""
            rows.append(
                {
                    "id_a": left.get("id") or "",
                    "id_b": right.get("id") or "",
                    "short_a": short_id(left.get("id") or ""),
                    "short_b": short_id(right.get("id") or ""),
                    "label_a": label_left,
                    "label_b": label_right,
                    "same_label": int(label_left == label_right and bool(label_left)),
                    "mode_a": left.get("mode") or "",
                    "mode_b": right.get("mode") or "",
                    "activity_a": (left.get("activity") or "")[:120],
                    "activity_b": (right.get("activity") or "")[:120],
                    "clip_cosine": round(clip_score, 6),
                    "phash_sim": round(phash_score, 6),
                    "clip_minus_phash": round(clip_score - phash_score, 6),
                }
            )
    rows.sort(key=lambda row: (-row["clip_cosine"], -row["phash_sim"], row["id_a"], row["id_b"]))
    return rows


def write_matrix_csv(path: Path, samples: list[dict], matrix: list[list[float]]) -> None:
    headers = ["id"] + [sample["id"] for sample in samples]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for sample, row in zip(samples, matrix):
            writer.writerow([sample["id"]] + [f"{value:.6f}" for value in row])


def write_pairs_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def summarize(samples: list[dict], rows: list[dict]) -> dict:
    same = [row for row in rows if row["same_label"]]
    diff = [row for row in rows if not row["same_label"]]

    def _mean(items: list[dict], key: str) -> float:
        if not items:
            return 0.0
        return sum(item[key] for item in items) / len(items)

    return {
        "model": CLIP_MODEL_ID,
        "n_images": len(samples),
        "n_pairs": len(rows),
        "clip_mean_same_label": round(_mean(same, "clip_cosine"), 6),
        "clip_mean_diff_label": round(_mean(diff, "clip_cosine"), 6),
        "phash_mean_same_label": round(_mean(same, "phash_sim"), 6),
        "phash_mean_diff_label": round(_mean(diff, "phash_sim"), 6),
        "top5_clip": [
            {
                "a": row["short_a"],
                "b": row["short_b"],
                "clip": row["clip_cosine"],
                "phash": row["phash_sim"],
                "same_label": row["same_label"],
                "label_a": row["label_a"],
                "label_b": row["label_b"],
            }
            for row in rows[:5]
        ],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    parser.add_argument("--split", default="train")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--batch-size", type=int, default=4)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    store = BenchmarkStore(args.data_root)
    samples = load_split_samples(store, args.split)
    if not samples:
        raise SystemExit(f"No samples in split={args.split}")

    image_paths = [store.screenshot_path(sample) for sample in samples]
    clip_scores = clip_matrix(image_paths, device=args.device, batch_size=args.batch_size)
    phash_scores = phash_matrix(samples)
    rows = build_pair_rows(samples, clip_scores, phash_scores)

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    write_pairs_csv(out_dir / "pairs.csv", rows)
    write_matrix_csv(out_dir / "matrix_clip.csv", samples, clip_scores)
    write_matrix_csv(out_dir / "matrix_phash.csv", samples, phash_scores)
    summary = summarize(samples, rows)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"wrote {out_dir / 'pairs.csv'}")


if __name__ == "__main__":
    main()
