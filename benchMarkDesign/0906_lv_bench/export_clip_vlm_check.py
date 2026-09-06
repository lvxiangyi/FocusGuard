"""Build a side-by-side gallery: CLIP similar, human labels differ, VLM split them."""

from __future__ import annotations

import html
import json
from collections import Counter
from pathlib import Path

from benchmark.store import BenchmarkStore

ROOT = Path(__file__).resolve().parent
REPORT = ROOT / "logs" / "clip_pairwise" / "clip_high_diff_label.json"
OUT_DIR = ROOT / "logs" / "clip_pairwise" / "check_clip_close_vlm_split"


def _esc(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def main() -> None:
    payload = json.loads(REPORT.read_text(encoding="utf-8"))
    store = BenchmarkStore(ROOT / "data")
    by_id = {sample["id"]: sample for sample in store.list_samples("train")}
    pairs = [
        item
        for item in payload["high_pairs"]
        if item["vlm_verdict"] == "distinguished_correct"
    ]
    pairs.sort(key=lambda item: -item["clip_cosine"])

    ids = []
    for item in pairs:
        ids.extend([item["id_a"], item["id_b"]])
    hub = Counter(ids)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cards = []
    for index, item in enumerate(pairs, start=1):
        left = by_id[item["id_a"]]
        right = by_id[item["id_b"]]
        src_a = store.screenshot_path(left)
        src_b = store.screenshot_path(right)
        rel_a = Path("..") / ".." / ".." / "data" / "train" / left["screenshot_relpath"]
        rel_b = Path("..") / ".." / ".." / "data" / "train" / right["screenshot_relpath"]
        if not src_a.is_file() or not src_b.is_file():
            raise FileNotFoundError(f"missing {src_a} or {src_b}")
        cards.append(
            f"""
<section class="pair">
  <header>
    <strong>#{index}</strong>
    CLIP {item['clip_cosine']:.3f} · pHash {item['phash_sim']:.3f}
    · { _esc(item['short_a']) } / { _esc(item['short_b']) }
  </header>
  <div class="grid">
    <figure>
      <img src="{_esc(rel_a.as_posix())}" alt="{_esc(item['short_a'])}">
      <figcaption>
        <div><code>{_esc(item['short_a'])}</code> · { _esc(item['mode_a']) }</div>
        <div>人工 <b>{_esc(item['human_a'])}</b> · VLM <b>{_esc(item['ai_a'])}</b></div>
        <div>{_esc(item['activity_a'])}</div>
      </figcaption>
    </figure>
    <figure>
      <img src="{_esc(rel_b.as_posix())}" alt="{_esc(item['short_b'])}">
      <figcaption>
        <div><code>{_esc(item['short_b'])}</code> · { _esc(item['mode_b']) }</div>
        <div>人工 <b>{_esc(item['human_b'])}</b> · VLM <b>{_esc(item['ai_b'])}</b></div>
        <div>{_esc(item['activity_b'])}</div>
      </figcaption>
    </figure>
  </div>
</section>
"""
        )

    page = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>CLIP close / VLM split</title>
  <style>
    body {{ font-family: sans-serif; margin: 24px; background: #111; color: #eee; }}
    h1 {{ font-size: 22px; margin: 0 0 8px; }}
    .meta {{ color: #aaa; max-width: 900px; line-height: 1.5; }}
    .pair {{ margin: 28px 0; padding: 16px; background: #1b1b1b; }}
    .pair header {{ margin-bottom: 12px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    img {{ width: 100%; height: auto; background: #000; }}
    figcaption {{ font-size: 13px; color: #ccc; margin-top: 8px; line-height: 1.45; }}
    code {{ color: #9cf; }}
    @media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <h1>CLIP 分不开、VLM 分开了</h1>
  <p class="meta">
    37 张 train 两两组合是 666 对，不是 37 对。CLIP≥0.75 且人工标签不同有 57 对，
    其中 VLM 标签不同且两侧都对上人工的是 {len(pairs)} 对，只涉及 {len(hub)} 张不重复的图。
    高频重复：{', '.join(f'{sid[:8]}×{count}' for sid, count in hub.most_common(6))}。
    打开本页即可左右对照，图仍在 data/train/screenshots，没有再拷一份。
  </p>
  {''.join(cards)}
</body>
</html>
"""
    out = OUT_DIR / "index.html"
    out.write_text(page, encoding="utf-8")
    summary = {
        "n_pairs": len(pairs),
        "n_unique_images": len(hub),
        "hub_images": hub.most_common(),
        "html": str(out),
    }
    (OUT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
