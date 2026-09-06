# FocusGuard Agent — 项目指南（面向 AI Agent）

> 本文件是后续修改本仓库代码的 AI agent 的第一手参考。开始任何代码修改前请通读本文件，
> 尤其是「目录结构」一节；修改完成后必须按下方的**维护规则**更新本文件。

## 1. 维护规则（修改代码后必须执行）

本文件中的「目录结构」由项目代码的演化驱动，要求保持与真实代码一致。规则如下：

1. **每次修改、新增或删除代码文件后**，检查受影响文件是否在下方「目录结构」中有条目：
   - 职责/行为发生变化 → 更新对应条目的一句话描述；
   - 新增文件/目录 → 添加条目（一句话说明它做什么）；
   - 删除/重命名文件 → 删除或改写对应条目；
   - 结构层面的大改动（新子系统、跨目录重构）→ 同步更新「核心流程」与「数据文件」小节。
2. 同时在文末「最近代码变更」按时间顺序**追加一行**记录本次改动（日期 + 一句话摘要 + 涉及文件）。
3. 不要为 `node_modules/`、`.venv/`、`dist/`、`release/`、`__pycache__/` 等依赖/构建产物维护条目；
   `data/` 是运行时数据，只维护目录层面的描述，不逐个文件记录。
4. 描述保持精炼（一句话），不要粘贴大段实现细节——本文件的目的是让后续 agent 快速定位，而非替代代码。

## 2. 项目简介

**FocusGuard Agent**（旧代号 AIMonitor）是一个 **Windows 专用的 AI 专注力监控桌面应用**：

- 周期性截取当前屏幕，由视觉 LLM 判断用户是否在专注（`on_task` / `off_task` 或 guardian 的 `allow` / `interrupt`）；
- 判定分心且连续命中阈值后，弹出**系统级全屏拦截窗口**（tkinter），用户必须作答（答题或**英→日翻译挑战**，strict 模式需答对 3 题）才能继续；
- 用户可对判定提出异议（dispute），被接受的异议会记入记忆并影响后续判定；
- 提供 **Guardian 常驻模式**：无专注 Session 时也在后台监控，拦截明显的娱乐/成人/小说/漫画内容，娱乐有时间额度与休息配额；
- 有日程（Schedule）自动开始 Session、休息/暂停/恢复的 Flow、每日报告、数据分析；
- **Dataset 采集**：把真实判定截图 + 用户标注存成数据集；
- **Personal Bench（本分支的重点）**：把用户标注样本作为「个人校准库」，判断时从 train 集检索相似历史案例注入 prompt（few-shot RAG），并可用 test 集评测准确率。

### 技术栈与分层（三层本地应用，均为本地进程、无云服务）

| 目录 | 角色 | 技术 |
|---|---|---|
| `backend/` | 全部核心逻辑：监控、判定、拦截、数据 | Python + FastAPI + uvicorn；tkinter（拦截窗口，独立线程）；mss/Pillow（截图）；openai SDK（OpenAI 兼容 API） |
| `frontend/` | 控制面板 SPA | React 18 + Vite（纯静态，构建后由 Electron `loadFile` 加载） |
| `electron/` | 桌面壳：拉起后端、加载前端、注册全局快捷键 | Electron 主进程（`main.js`） |

UI 文案中英日混用（控件标题多为英文，业务提示有中文、翻译题目标语言为日语），修改文案时保持这一习惯。

## 3. 常用命令

```bat
:: 首次安装（创建 backend\.venv、frontend node_modules、构建前端）
setup_windows.bat

:: 开发模式：后端 uvicorn :8000（--reload，AIMONITOR_DATA_ENV=dev）+ 前端 vite :3000
start_dev.bat
:: 同时打开 Electron（dev，复用 :8000 后端）：
start_dev.bat electron

:: 稳定运行（AIMONITOR_DATA_ENV=prod）：Electron 拉起后端(8899起)并加载 frontend/dist
start_stable.bat

:: 仅重新构建前端
build_frontend.bat

:: 打包发布（PyInstaller 后端 + electron-builder），产物在 electron/release/
powershell -ExecutionPolicy Bypass -File package_release.ps1
```

测试（pytest，在 `backend/` 目录下运行）：

```bat
cd backend
.venv\Scripts\python.exe -m pytest tests -q
```

单测文件命名 `tests/test_<module>.py`，模块间通信（如重启后恢复拦截窗口）用注入假对象的方式测试。

## 4. 目录结构

### 数据流向速览

```
后端由谁驱动?
  - 会话判定循环: SessionManager._monitor_loop()   → screenshot → vision_judge → 分心拦截
  - 常驻守护循环: GuardianManager._loop()          → 同上(guardian 判定) → 娱乐/休息额度管理
  - 日程: auto_scheduler → session_manager.start_session
拦截弹出: blocker_window.py 的 tkinter 线程(队列驱动) ← session/guardian/flow 共用
AI 判定:  llm_client(供应商/模型) → vision_judge(prompt) ← personal_bench.retrieve(注入个人案例)
```

### `backend/` — FastAPI 后端（工作目录即 backend，模块顶层 import 平铺）

API 一律挂在 `main.py`，按用途前缀：`/session`、`/guardian`、`/flow`、`/schedule`、`/settings`、
`/ai/status`、`/personal-bench`、`/dataset`、`/quiz`、`/strict/translation`、`/practice`、`/report`、
`/analytics/summary`（内联读取 session_logs 聚合，无独立模块）。

| 文件 | 职责（一句话） |
|---|---|
| `data_paths.py` | 数据根目录唯一权威：`PROJECT_ROOT`、`DATA_DIR`（`data/{dev,prod}` 由 `AIMONITOR_DATA_ENV` 决定）、logs/screenshots/dataset/guardian/practice/personal_bench 等路径，import 时自动建目录。改路径先改这里 |
| `run_backend.py` | 打包后入口：为 PyInstaller 冻结 exe 配置 Tcl/Tk 库路径，再 `uvicorn main:app`，端口读 `FOCUSGUARD_PORT`（默认 8899） |
| `main.py` | FastAPI app + 全部路由；startup 时启动 auto_scheduler 与 guardian_manager，并重放上次未展示的 flow prompt |
| `session_manager.py` | `SessionManager` 单例：Session 生命周期；`_monitor_loop()` 定时截图→屏幕未变则复用上次判定→否则 `judge_screenshot`→off-task 连续命中 `trigger_threshold` 则 `blocker.show`→逐条写 `session_logs.jsonl`；dispute/恢复/休息暂停/超时结束 |
| `guardian_manager.py` | `GuardianManager` 常驻模式：无 Session 时周期性 guardian 判定；拦截后进入 break/娱乐流程，管理每日娱乐额度（分钟制，`guardian_state.json`）、休息配额、block 冷却；写 `guardian_logs.jsonl` |
| `vision_judge.py` | 视觉判定核心：session/guardian/dispute 三套 prompt 模板 + LLM JSON 解析重试；**判定前检索个人案例**（`_retrieve_personal_hits` → `inject`）并注入 prompt；hard category（adult/novel/manga/game）强制打断逻辑、白名单、记忆上下文；mock 模式；API 错误分类降级 |
| `llm_client.py` | 模型名 → 供应商(OpenRouter/DeepSeek/MiniMax)与 base_url/API key 解析；为廉价思考型模型禁用 thinking；`message_text` 兼容返回 content 为空的思考模型 |
| `screenshot.py` | mss 截取鼠标所在显示器（`AIMONITOR_SCREENSHOT_MODE=full` 时全虚拟屏）并缩图；64×36 灰度小图逐像素 diff，`should_reuse_previous` 判定屏幕几乎未变则跳过 AI 调用 |
| `blocker_window.py` | **tkinter 全屏拦截窗口**（2k+ 行，独立常驻线程 + 队列驱动，避免 Tcl 崩溃）；复用同一 window 显隐；拦截页(答题/翻译挑战 3 题)/提示消息(5 分钟倒计时提醒)/flow 提示/恢复提示；经 Windows API 定位鼠标所在显示器、置顶；`BACKEND_URL` 读 `FOCUSGUARD_PORT` |
| `flow_manager.py` | Session 间的「Flow」编排：继续工作/主动休息/停止休息/暂停当天，维护 pending 状态与定时任务；结束或重启后靠 `flow_prompt_store` 恢复提示 |
| `flow_prompt_store.py` | 把待展示的 flow 提示持久化到 `pending_flow_prompt.json`，重启后补展示 |
| `schedule_manager.py` | 日程 CRUD（`schedules.json`）、时间窗解析 |
| `auto_scheduler.py` | 后台循环：到点的日程自动开 Session，结束记 block |
| `report_manager.py` | 以「block 记录」聚合每日报告（`daily_reports.json`）+ 每日笔记 |
| `settings_manager.py` | `settings.json` 读写/校验/默认值；模型列表、白名单行为、supervision 等级规则文本、guardian 各项配额读取、strict 锁定状态 |
| `ai_status_manager.py` | 最近一次 AI 调用成功/失败/所用模型的内存态 + mock 开关；`/ai/status` |
| `time_warning.py` | 倒计时拆分（剩 5 分钟经 blocker 弹提醒）等时间工具 |
| `quiz_generator.py` | 答题/翻译挑战生成与判分：session 内 quiz、**strict 翻译题**（来源可自定义练习文件）、纠错记录、练习进度与 attempts 落盘、LLM 判分 + 兜底题库 |
| `dataset_store.py` | 数据集采集：sqlite(`dataset.db`) + 截图文件；label ∈ {on_task, off_task, ambiguous, unlabeled}；CRUD/评审/导出 JSONL/打开目录 |
| `personal_bench/` | **个人 few-shot 基准（RAG 管线）**，见下 |
| `tests/` | pytest：按模块一个文件，`test_vision_judge_parse.py`、`test_personal_bench_retrieve.py`、`test_guardian_rest.py` 等 |
| `requirements.txt` | fastapi/uvicorn/mss/Pillow/python-dotenv/openai/pydantic/requests |

#### `personal_bench/` — 个人样本库 + 检索注入（本分支核心）

```
data/personal_bench/
├── train/samples.jsonl + screenshots/   模式=guardian 或 session 的人工标注案例
├── test/samples.jsonl + screenshots/    评测集（只在评测/人工移动时使用）
├── capture_context.json                 采集表单默认值
└── pending/capture.jpg + capture.json   快捷键先截图、稍后补上下文的「待提交」状态
```

| 文件 | 职责（一句话） |
|---|---|
| `schema.py` | 模式/分割/标签常量：guardian → {allow, interrupt, ambiguous}；session → {on_task, off_task, ambiguous}；标签归一化与比对 |
| `store.py` | `BenchStore`：train/test 两个 split 的 JSONL + 截图文件管理；新增样本复制截图并记 image_hash；删除/跨 split 移动 |
| `image_hash.py` | 感知平均哈希（aHash）相似度，用于样本间/查询-样本的图像比对 |
| `retrieve.py` | **检索器**：查询与 train 样本按文本（token 交集 Jaccard：task/activity/reason）+ 图像哈希加权打分；session 模式优先同任务桶、且同任务最佳命中不设下限；**永不检索 test** |
| `inject.py` | 把命中案例格式化为英文 prompt 段落（说明这些只是个人校准先例，不是白名单豁免），或注入到既有 prompt 尾部 |
| `evaluate.py` | 评测：每个 test 样本 → 从 train 检索 Top-K → 注入 → 调 `judge_fn` → 与 human_label 比对出准确率（ambiguous 不计入） |
| `recent.py` | 合并 guardian/session 的判定日志，提供「最近判定」列表（含截图路径/建议标签），供用户评审后补标为样本 |
| `capture_context.py` | 热键「先截图后补 context」流程：pending 截图、对/错 verdict、commit 到 BenchStore；表单默认值持久化 |

`personal_bench` 在运行期的接线点都在 `vision_judge.py`（session 与 guardian 判定前检索注入）；
另注意 `vision_judge` 对娱乐类 hard category 的强制打断允许「非常相似的人工 allow 案例」覆盖（阈值 `PERSONAL_ALLOW_OVERRIDE_SCORE`）。

### `frontend/` — React SPA（控制面板）

| 文件 | 职责 |
|---|---|
| `index.html` + `vite.config.js` | Vite 入口/配置（dev :3000） |
| `src/main.jsx` | React 挂载 |
| `src/App.jsx` | 单文件大组件（~1700 行）：tab 导航 **Session / Schedule / Report / Dataset / Settings**；各 tab 内联子组件渲染；轮询 `/session/status`；监听 `aimonitor-pending-capture` 自定义事件（Electron 热键截图后广播）刷新 Dataset 待提交区；Dataset tab 内含 Personal Bench 采集/样本浏览（recent → 补标入 train、pending 提交、train/test 样本移动/删除） |
| `src/api.js` | 全部后端调用的 fetch 封装；base 默认 `http://127.0.0.1:8000`，支持 `?apiBase=` 查询参数（Electron 加载时注入实际端口） |
| `src/styles.css` | 深色主题样式 |

### `electron/` — 桌面壳

| 文件 | 职责 |
|---|---|
| `main.js` | 主进程：优先 spawn `backend\.venv\Scripts\python -m uvicorn main:app`（打包后运行 `aimonitor-backend.exe`）；从 8899 起找空闲端口，健康检查后创建窗口（dev 走 `AIMONITOR_ELECTRON_DEV=1` 指向 vite，否则 `loadFile(frontend/dist)` 并带 `apiBase`）；写 `data/<env>/logs/app.log`；注册全局热键 **Ctrl+Alt+1/2**：截图判对/错 → 通知 + 广播到前端 Dataset 页；退出时 taskkill 后端 |
| `package.json` | electron + electron-builder 打包配置（productName "FocusGuard Agent"，额外资源带 frontend/dist 与冻结后的 backend） |

### `data/` — 运行时数据（gitignore，按 `AIMONITOR_DATA_ENV` 分 `dev/` 与 `prod/` 两套）

| 子目录/文件 | 内容 |
|---|---|
| `logs/session_logs.jsonl` | 每次专注检查一条：on_task、activity、confidence、截图路径、model 等（analytics 与 recent.py 都读它） |
| `logs/guardian/…` | 见下 `guardian/` |
| `logs/schedules.json`、`daily_reports.json`、`wrong_answers.json`、`dispute_memory.json` | 日程 / 每日报告 / 错题 / 被接受的异议记忆 |
| `logs/app.log` | Electron 写的主进程日志 |
| `screenshots/` | session 判定截图，**每次检查一个独立文件**（按 `<日期>/<时间>-<uuid>.jpg` 分目录存放，供历史记录回看；根下的 `latest.jpg` 是历史遗留默认路径，不再被运行期使用） |
| `dataset/` | 数据集 sqlite + screenshots/ + exports/（Dataset 采集） |
| `guardian/` | guardian_state.json（娱乐/休息额度）、guardian_logs.jsonl、screenshots/ |
| `practice/` | practice_state.json（练习进度）、practice_attempts.jsonl |
| `personal_bench/` | 个人样本库（train/test/pending），见 `personal_bench/` 一节 |
| `settings.json` | 用户设置（模型、strict 开关、guardian 配额、练习源文件等） |

### `docs/demos/mvp-v1/` — MVP 界面交互演示（独立 HTML，不接正式后端）

| 文件 | 用途 |
|---|---|
| `index.html` | 专注主页、独立最近判定页、拦截答题、个人案例和偏好设置的页面及弹窗入口。 |
| `styles.css` | 固定桌面导航和顶底栏、独立工作区滚动、自适应计时环及响应式和键盘焦点样式。 |
| `app.js` | 六种界面/翻译目标语言独立切换、句子翻译与解析、模拟计时和拦截、保留任务归属的案例管理（保存不解锁）。 |
| `README.md` | 演示范围、使用方式、模拟行为限制和 `mvp-demo-v1.2.0` 版本回溯、桌面布局及行为核对说明。 |

### 根目录脚本 / 配置文件

| 文件 | 用途 |
|---|---|
| `setup_windows.bat` / `start_dev.bat` / `start_stable.bat` / `build_frontend.bat` | 安装 / dev(8000+3000) / prod 启动 / 前端构建 |
| `package_release.ps1` | 发布打包：后端 PyInstaller 冻结 + 前端 build + electron-builder，产物 `electron/release/FocusGuard-Agent-<version>-<date>-win-unpacked(.zip)` |
| `.env` | API key（`OPENROUTER_API_KEY` / `DEEPSEEK_API_KEY` / `MINIMAX_API_KEY`），gitignore |
| `.gitignore` | 忽略 `.env`、`data/`、`.venv/`、`node_modules/`、`dist/`、`release/`、`*.jpg`、`package-lock.json` 等 |

## 5. 关键约定

- **数据环境**：dev/prod 由 `AIMONITOR_DATA_ENV` 切换，所有路径经 `data_paths.py` 引用——新数据文件一律在 `data_paths.py` 定义路径并 import，不要硬编码。
- **进程模型**：拦截窗口必须常驻显隐、不可反复 create/destroy（Tcl 崩溃问题）；backend 与 blocker 之间经 HTTP(`127.0.0.1:FOCUSGUARD_PORT`)通信。
- **AI 供应商**：设置里的模型 id → `llm_client.MODEL_PROVIDER` 决定走哪家；无 key/失败降级为显式 API 错误结果（**不是**随机 mock）；`AIMONITOR_ENABLE_MOCK_AI=1` 才启用 mock 判定。
- **判定复用**：屏幕几乎未变时复用上次判定结果并跳过 LLM 调用（省钱/省时）；API 错误不参与 off-task 计数。
- **标签语义**：personal_bench 中 `ambiguous` 不算命中，session 样本必须有 task，guardian 样本 task 恒为空；test 集只用于评测，检索永远只查 train。
- **文案语言**：UI 标题英文为主、提示可中文、翻译目标语言日语；prompt 模板英文为主。
- **健康检查改动点**：改 AI 判定 prompt → `vision_judge.py` 模板（含 `{precedents}` 注入位）；加设置项 → `settings_manager.py` 默认值 + `main.py` 的 SettingsRequest + `App.jsx` 设置表单三处联动；改数据目录 → `data_paths.py`。

## 6. 最近代码变更

> 每次修改代码后在此追加一行（本文件即 git 历史之外的“活文档”，靠这条日志保持诚实）。

- 2026-09-06 创建本文件，梳理整体目录结构（backend 监控/拦截/采集三块、personal_bench RAG 管线、frontend/electron 壳、data 布局）。
- 2026-09-06 修复「检查记录图片全是最后一次检查」bug：session 每次检查改为独立时间戳截图文件（screenshot.py 新增 `timestamped_screenshot_path`，session/guardian 共用）；历史指向 `latest.jpg` 的日志行在 recent.py 中标记为无图（原文件已被覆盖）。涉及 backend/screenshot.py、session_manager.py、guardian_manager.py、personal_bench/recent.py。
- 2026-09-06 新增收紧功能边界的 MVP HTML 交互演示，包含六语界面/答题、专注状态、拦截和个人案例纠正，版本 `mvp-demo-v1.0.0`；涉及 docs/demos/mvp-v1/index.html、styles.css、app.js、README.md。

- 2026-09-06 修订 MVP demo 为句子翻译，纠正案例保存即解锁、历史任务归属、普通纠错暂停及模拟引用数量问题；保留旧标签，新增 `mvp-demo-v1.1.0`，涉及 docs/demos/mvp-v1/index.html、app.js、README.md。

- 2026-09-06 将 MVP 最近判定迁移至独立页面并收紧主页为桌面工作区，新增版本 mvp-demo-v1.2.0；涉及 docs/demos/mvp-v1/index.html、styles.css、README.md。
