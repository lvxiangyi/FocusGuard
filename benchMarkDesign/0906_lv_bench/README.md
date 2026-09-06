# FocusGuard Screenshot Benchmark 0906

第一阶段目标：在独立 View 窗口中浏览 benchmark 截图及完整 context，并通过截图实时加入 train/test。

## 启动

双击 `start.bat`。程序会启动本地服务并打开：

```text
http://127.0.0.1:8765/#view
```

如果 `8765` 已被旧版本占用，启动器会自动使用后续可用端口并打开正确的新页面。

也可以手动运行：

```powershell
cd D:\02_PersonalProj\AImonitor\AIMonitor\benchMarkDesign\0906_lv_bench
..\..\backend\.venv\Scripts\python.exe run.py
```

若未安装依赖：

```powershell
python -m pip install -r requirements.txt
```

## 使用流程

1. 启动后默认进入 `View`，浏览已有截图及完整 Context，并可直接修改和保存当前样本。
2. 切换到 `Capture`，填写 mode、task、监管档位、activity 和人工理由。
3. 选择 `train`（未来用于 RAG）或 `test`（只用于 benchmark）。
4. 点击“3 秒后截图”，立即切回目标窗口。倒计时结束时截取鼠标所在显示器。
5. 检查截图和自动读取的前台窗口标题，然后保存。
6. 保存后程序自动回到 `View` 并选中新样本。

页面每 3 秒自动刷新样本列表。Context 表单会保存到 `data/capture_context.json`，下次启动继续使用。

## 0825 兼容迁移

点击“导入 0825”会从以下位置复制有效数据，不会删除或修改旧目录：

```text
../0825_bench/data
../0825_bench/dataTab/data
```

当前两个 0825 数据目录没有实际样本，因此第一次导入通常显示新增 0。

## 导入 AIMonitor 历史截图

从 Guardian/Session 日志中配对截图和原始 AI context，去重后导入最近 50 张：

```powershell
..\..\AIMonitor\backend\.venv\Scripts\python.exe import_history.py --limit 50
```

历史 AI 标签不能作为人工真值，因此导入项默认放入 `test`、人工标签设为 `ambiguous`，等待在 View 中复核。

用粗场景桶 + 视觉哈希重新生成历史样本：

```powershell
..\..\AIMonitor\backend\.venv\Scripts\python.exe import_history.py --limit 50 --interrupt-quota 12 --replace-imported
```

`--replace-imported` 先选好新样本，再只替换 `source_type=history_import` 的项目，不会删除手工标注或 AI 纠错数据。同一场景（Zoom / IDE / 卫星图 / YouTube 等）默认最多 3 张，并尽量保留 Session 与打断样本。

## 数据分层

不要维护三个互斥的物理目录。使用两个正交字段：

- `dataset_role`：由 split 决定；`calibration/train` 可供 RAG 使用，`test` 只用于评测。
- `source_type`：`manual_seed`（用户主动标注）、`ai_correction`（AI 判错后纠正）、`history_import`（历史候选）。
- `review_status`：默认 `reviewed`；只有还没看过或拿不准时才标 `pending`。
- `human_label`：唯一活动标签，`ontask` / `process` / `entertainment` / `not_entertainment_but_notFocus`。`supervision_level` 与它同步，不再单独标注。

默认 `human_label` 等于映射后的 AI 标签。旧值：`allow`/`on_task`→`ontask`，`interrupt`/`off_task`→`entertainment`。

派生打断：Guardian 只打断 `entertainment`；Session 打断 `entertainment` 和 `not_entertainment_but_notFocus`。

## 数据结构

每个 split 使用：

```text
data/<split>/samples.jsonl
data/<split>/screenshots/<id>.jpg
```

样本包括截图、mode、task、监管档位、人工标签/理由、窗口标题、AI 原判断、模型、Prompt/检索器版本、时间和来源。`retrieval_history` 已预留，后续用于记录样本是否被 RAG 检索。

## 测试

```powershell
..\..\AIMonitor\backend\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
