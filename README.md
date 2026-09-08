# FocusGuard Agent

Windows desktop app that watches the screen during a timed focus session, flags distraction, and helps you get back to the task. The interface defaults to **English**. You can switch it to Chinese, Japanese, Korean, French, or Portuguese in Preferences.

The official UI has four pages: **Focus**, **Recent judgments**, **My examples**, and **Preferences**. Guardian, scheduler, and Flow stay in the codebase but do not start with the app.

## Requirements

- Windows 10 or 11
- Python 3.9+ (the repo uses a backend virtualenv)
- Node.js 18+ (frontend and Electron)
- An [OpenRouter](https://openrouter.ai/) API key (or another provider you put in `.env`)

## First-time setup

From the repo root (`AIMonitor/`):

```bat
setup_windows.bat
```

This creates `backend/.venv`, installs Python and npm dependencies, and builds `frontend/dist`. Electron reads that production build, not the Vite dev server.

Create `.env` in the repo root (never commit this file):

```env
OPENROUTER_API_KEY=sk-or-your-real-key
```

Optional: to start FocusGuard when Windows signs in, put a shortcut to `start_stable.bat` in `shell:startup`.

## Daily use

```bat
start_stable.bat
```

This sets `AIMONITOR_DATA_ENV=prod` and opens Electron. Close any older FocusGuard window first so ports and the overlay do not collide.

### Focus

1. Type the task you intend to do (for example `write the report`).
2. Pick 25, 45, or 60 minutes.
3. Start the session. The app screenshots the monitor under the mouse on each check (default every 5 minutes).
4. If the model thinks you left the task, a system overlay appears and the timer freezes until you recover.
5. You can end the session yourself. There is no separate rest / work / stop wizard in this MVP.

Session supervision is `task_related`: entertainment and “not entertainment but not focus” both interrupt.

### When the overlay appears

Recovery mode is set in Preferences:

| Mode | What you do |
| --- | --- |
| **Quick return** (default) | Confirm once and continue. |
| **Next step** | Write the next concrete action, then continue. |
| **Translation practice** | Translate a bank sentence into the target language. The model must accept the answer. Viewing the hint counts as a skip; you get a new sentence. |

Without a valid API key, translation practice does not unlock. A failed or malformed model reply also does not unlock.

### Recent judgments

Browse real screenshots and the model’s verdict. Mark what you were actually doing (**on task** / **off task**) and optionally write a reason, then save. That label is your ground truth, not a vote on whether you “agree with the AI.”

Hotkeys (when the session is running, not while the overlay is up):

- `Ctrl+Alt+1` — capture as on task
- `Ctrl+Alt+2` — capture as off task

Then finish the task name and reason on this page. During an overlay, use the overlay’s correction path so you do not screenshot the blocker itself.

### My examples

Session training examples used as retrieval hints for later judgments. Saving an example does **not** dismiss the current overlay and is not the same as winning a dispute.

The test split is not shown here and is never retrieved.

### Preferences

- **Interface language**: Chinese, English (default for new installs), Japanese, Korean, French, Portuguese. Model reasons and translation feedback follow this language. Your task text and old labels stay as you wrote them.
- **Recovery method**: quick return, next step, or translation. The translation target language appears only for translation practice. It is independent of the interface language.
- **Advanced** (collapsed): check interval, consecutive-hit threshold, vision model.

Existing installs that already saved `ui_language` in `settings.json` keep that value. Change it here if you still see Chinese after this update.

## Configuration and data

| Item | Location |
| --- | --- |
| API keys | `.env` in the repo root |
| User settings | `data/prod/settings.json` (stable) or `data/dev/settings.json` (dev) |
| Screenshots and logs | `data/prod/` or `data/dev/` |
| Personal examples | under that data env, or a folder you set as the personal bench root |

`data/`, `.env`, and `*.jpg` are gitignored except the 0906 bench dataset under `benchMarkDesign/`.

Screenshot mode: the cursor’s monitor by default. Set `AIMONITOR_SCREENSHOT_MODE=full` for the full virtual desktop.

### Personal bench (optional)

You can point Preferences at a labeled screenshot bench so retrieval can use your own examples. The independent 0906 workbench lives at `benchMarkDesign/0906_lv_bench/`. Start it with `start.bat` there (browser UI on `http://127.0.0.1:8765/#view`). That tool is separate from the Electron app: it does not start Guardian or Session.

Train examples may be retrieved. Test examples are evaluation-only.

## Development

```bat
start_dev.bat
```

- Frontend: `http://127.0.0.1:3000`
- Backend: `http://127.0.0.1:8000` (`AIMONITOR_DATA_ENV=dev`)

To also open Electron against those servers:

```bat
start_dev.bat electron
```

After React changes, Electron’s stable start still needs a production build:

```bat
cd frontend
npm run build
```

Backend tests:

```bat
cd backend
.venv\Scripts\python.exe -m unittest discover -s tests
```

## Release build

```powershell
powershell -ExecutionPolicy Bypass -File package_release.ps1
```

Output:

```text
electron/release/FocusGuard-Agent-<version>-<YYYY-MM-DD>-win-unpacked/
electron/release/FocusGuard-Agent-<version>-<YYYY-MM-DD>-win-unpacked.zip
```

The unpacked folder is the supported Windows distribution. A single-file portable build is not used (NSIS download during packaging).

## Troubleshooting

- **Window looks like the old UI** — `frontend/dist` is stale. Run `npm run build` in `frontend/`, then restart `start_stable.bat`.
- **No overlay / no judgments** — check `.env`, the selected model, and the backend console. API errors pause that judgment instead of inventing a pass.
- **Every session screenshot looks the same in history** — older session logs may point at `screenshots/latest.jpg`. Guardian already writes unique files.
- **Port in use** — close the previous FocusGuard or bench window.
- **Interface still in Chinese** — open Preferences and set Interface language to English, or delete `ui_language` from `data/prod/settings.json` so the new default applies.

## Repository notes

- Application git root is `AIMonitor/`.
- Push personal data and the latest calibration bench to the **private** remote only, not the public `origin`.
