# 0906_lv_bench progress

规则：每次改这个工作台，先在本文件追加一节，再动手。

## 2026-09-06

### 已落地

- 工作台保持独立浏览器（`start.bat` → `http://127.0.0.1:8765/#view`），不嵌进 FocusGuard 主程序。
- View 可边看边改：人工标签、理由、task、activity、窗口标题、AI 原判断、模型、Prompt/检索器版本、`dataset_role`、`source_type`、`review_status`。改 split 会走 move。
- 数据用两个正交字段，不是三个互斥目录：
  - `dataset_role`：`calibration/train` 可进 RAG，`test` 只评测。
  - `source_type`：`manual_seed` / `ai_correction` / `history_import`。
- 历史导入改为先选后删，避免选择失败时出现空集。
- `int.bit_count()` 已去掉，统一用 `bin(xor).count("1")`，兼容当前 3.9 venv。

### 卡住过

- 第一次 `--replace-imported` 在多样性计算里调用了 `bit_count()`，3.9 报错；当时已经删掉旧的 50 条 `history_import`。
- 随后用兼容实现补回 50 条，但仍按时间从新到旧取，结果被 Zoom / Cursor / 卫星研究页占满（47 guardian / 3 session，38 allow）。

### 这一刀

- `scene_bucket` 把近重复活动收成粗桶，每桶默认最多 3 张。
- 选择时按桶轮转，并给 interrupt/off_task 和 Session 留席位。
- 新增 `tests/test_import_history.py`。
- 规则写进仓库根 `MVPDevelopSkill.md` 第 8 节。

### 重采结果

`import_history.py --limit 50 --interrupt-quota 12 --replace-imported` 已跑通（先选后删，只动 `history_import`）。

- train / calibration：0
- test：50 张图 + 50 条 metadata，全部 `history_import` + `pending`
- 手工标注和 AI 纠错：0
- mode：guardian 38 / session 12
- AI 标签：allow 31 / on_task 6 / interrupt 7 / off_task 6
- 场景不再被 Zoom/IDE/卫星图占满：youtube 3、game 3、adult 3、spotify 3、search 3，zoom/satellite 各 1
- 已丢掉「AI 判定を取得できませんでした」和 unlock screen 这类低信息图

单测：`python -m unittest discover -s tests -v` → 8 passed。

### 下一刀

在独立浏览器 View 里人工复核这 50 条，尤其是 YouTube 教程 / 游戏直播。复核后把判错纠正的样本改成 `source_type=ai_correction` 并移到 `train`；test 留下不进 RAG 的评测集。

## 2026-09-06 · 默认 AI 标签 + 四档 supervision

- `human_label` 默认等于 `ai_label`，只在人工改错时覆盖；`ambiguous` 不再作为历史导入默认值。
- `supervision_level` 改为：`ontask` / `process`（用户工作流）/ `entertainment` / `not_entertainment_but_notFocus`。旧值 `task_related`→`ontask`，`not_entertainment`→`not_entertainment_but_notFocus`。
- 已有 50 条 pending 历史样本的 `human_label` 已从 `ambiguous` 改成对应 `ai_label`；`supervision_level` 仍为空，等人工选四档。
- 单测：10 passed。需要重启 `start.bat` 后再刷新 View。

## 2026-09-06 · review_status 默认 reviewed

- 导入和 View 默认 `reviewed`：默认采纳 AI 标签，未改即视为已复核。
- 现有 50 条 `history_import` 的 pending 一并改成 reviewed。

## 2026-09-06 · human_reason 默认空

- 导入和已有占位理由改成空字符串，只在你主动填写时才有 `human_reason`。

## 2026-09-06 · 四档活动合成唯一标签

- `human_label` = `supervision_level`，四档：`ontask` / `process` / `entertainment` / `not_entertainment_but_notFocus`。
- 派生打断：Guardian 只打断 `entertainment`；Session 打断后两档。
- 旧标签映射：`allow`/`on_task`→`ontask`，`interrupt`/`off_task`→`entertainment`。
- 默认 `human_label` = 映射后的 `ai_label`。View 去掉单独的 supervision 下拉。
- 现有 50 条已改写：ontask 37 / entertainment 13，human 与 AI 标签一致。`process` 和 `not_entertainment_but_notFocus` 需要你在 View 里改。
- 单测 10 passed。刷新 View；最好重启 `start.bat`。

## 2026-09-06 · 标注备份 + 40/10 划分

- 当前工作台里是 47 条 reviewed（50 里有 3 条已被删）。已整包备份到 `0906dataBackUP`（47 图 + jsonl + manifest）。
- 工作副本按标签分层：train 37（ontask 29 / entertainment 7 / process 1），test 10（ontask 6 / entertainment 2 / process 1 / not_entertainment_but_notFocus 1）。

## 2026-09-06 · oneCaseTest YouTube 对

- 从现有 bench 里按 pHash 挑两张最像的 YouTube 图，复制到 `oneCaseTest`，用于单独验证 calibration。
- 选中：`821a192e`（train，ontask，Asmongold / Expedition 33）和 `cace9eff`（probe，ontask，同系列另一条）。pHash 相似度 0.73。原数据都在 train，未改动 37/10 划分。

## 2026-09-06 · CLIP/SigLIP 两两相似度（未开工）

方案已写，实现前等用户拍板：模型、图-图还是也算图-文、是否对照 pHash、输出形态、装进哪套环境。当前 train 实际是 37 张，不是 40。

## 2026-09-06 · CLIP 图-图两两分数（已跑）

用户拍板：只跑 OpenAI CLIP ViT-B/32，只算图-图 cosine，对照 pHash，输出 CSV。不装进 FastAPI venv，单独 `.venv_clip`，CPU。

- 37 张 train，666 对。结果在 `logs/clip_pairwise/`（`pairs.csv` / `matrix_clip.csv` / `matrix_phash.csv` / `summary.json`）。
- 同标签 CLIP 均值 0.701，跨标签 0.656；pHash 是 0.530 / 0.513。标签轴区分很弱，因为 29/37 都是 ontask、画面差很远。
- CLIP 更容易把「浏览器/文档网页」收成一簇（ChatGPT / Google / LeetCode / shopping 到 0.85–0.95），比 pHash 更不像像素哈希。
- oneCase YouTube 对 `821a192e`–`cace9eff`：CLIP 0.802，pHash 0.734。YouTube 播放 vs YouTube 搜游戏（entertainment）大约 0.64–0.71。

## 2026-09-06 · CLIP 高且标签不同 vs 当时 VLM

- 门槛：CLIP ≥ 0.75，人工标签不同。239 对里有 57 对。对照的是样本已写入的 `ai_label`，没有重跑 API。
- 结果：VLM 判成同一类 5；分开但不准 16；分开且准 36。
- 未分开的 5 对都绕着两张 VLM 已经判错的图：`f543a490` 购物（人工 ontask / AI entertainment）和 `ffc8db33` Google 搜索（人工 process / AI entertainment）。
- YouTube 播放 vs 游戏直播 CLIP 0.75–0.78，当时 VLM 写成 ontask / entertainment，能分开。
- 完整表：`logs/clip_pairwise/clip_high_diff_label.csv`。

## 2026-09-06 · CLIP 近、VLM 分开的并排页

- 57 对不是 57 张图：37 张的两两组合。CLIP≥0.75 且 VLM 分开且准的 36 对，只涉及 23 张不重复图。枢纽图：休息弹窗 `bb6bb333`×12，YouTube 搜 game `eaa1fff2`×11，漫画 `e3548dcc`×8。
- 并排页：`logs/clip_pairwise/check_clip_close_vlm_split/index.html`。规则已写入仓库根 `MVPDevelopSkill.md`：对数要同时报不重复图；对照看原图，不要只看 CSV。

## 2026-09-06 · 更正 bb6bb333 为 ontask

- 用户确认 `bb6bb333`（session / 冥想 / FocusGuard 休息结束弹窗）人工标签从 entertainment 改为 ontask。`ai_label` 仍是 entertainment。`should_interrupt=false`。
- 重算后：跨标签对 216，CLIP≥0.75 的 48（未分开 8 / 不准 16 / 分开且准 24）。并排页现在 24 对、21 张图，不再把这张当 entertainment 枢纽。

## 2026-09-06 · 重新检查标签（View 已改正）

用户在 View 里已把看游戏/YouTube 从抄来的 ontask 改成 entertainment：`821a192e`、`cace9eff`、`8d1602df`、`ea373ba7`。另有锁屏/Google 改成 process。当前 train：ontask 24 / entertainment 10 / process 3。人工≠AI 共 9 条。
- Expedition 33 对现在两边都是 entertainment，CLIP 0.80 是同场景近重复，不再是「都是 ontask」。
- 已重刷 `pairs.csv`、跨标签表、并排页（CLIP≥0.75 跨标签 64 对，VLM 分开且准 21 对）。`oneCaseTest` 元数据已跟上。
