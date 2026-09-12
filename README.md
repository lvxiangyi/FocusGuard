# FocusGuard

*Watches your screen during a focus session so you can stay on the task.*  
*Screenshots and labels stay on your machine.*

**[Releases](https://github.com/lvxiangyi/FocusGuard/releases)**

<details>
<summary>Table of Contents</summary>

- [About](#about)
- [Installation & Usage](#installation--usage)
- [API keys](#api-keys)
- [Is this yet another site blocker?](#is-this-yet-another-site-blocker)
- [About this repository](#about-this-repository)
- [Contributing](#contributing)

</details>

## About

The goal of FocusGuard is simple: *Keep you on a declared task without sending screenshots to a third-party dashboard.*

A timed session captures the screen, a vision model judges it against the task you named, and an overlay appears when you drift.

- **Timed session + screenshot check** — 25 / 45 / 60 minutes; the monitor under the cursor is captured on each check
- **Interrupt when off-task** — the timer freezes until you recover
- **A way back** — quick return, write the next step, or a short translation exercise

## Installation & Usage

Downloads: [FocusGuard-MVP-v0.1.0.zip](https://github.com/lvxiangyi/FocusGuard/releases/download/mvp-app-v0.1.0/FocusGuard-MVP-v0.1.0.zip) from the [v0.1.0 release](https://github.com/lvxiangyi/FocusGuard/releases/tag/mvp-app-v0.1.0). Use that zip, not GitHub's Source code archive.

After you unpack it, copy `.env.example` to `.env` next to `FocusGuard Agent.exe` and paste one key. See [API keys](#api-keys).

From source, put that same `.env` in the repo root, then:

```bat
setup_windows.bat
start_stable.bat
```

## API keys

Step-by-step: [How to add an API key](docs/api-keys.md).

Most bundled models use `OPENROUTER_API_KEY`. Official GPT uses `OPENAI_API_KEY`. Official Claude uses `ANTHROPIC_API_KEY`. You only need the line that matches the model in Preferences.

## Is this yet another site blocker?

Yes — and no. Most blockers hide a list of sites. FocusGuard looks at the actual screen and asks whether it matches *this* task.

**Common dealbreakers:**

- Cloud dashboards that see your activity
- Block-lists that miss “YouTube, but it is the tutorial”
- Time trackers that record everything and interrupt nothing
- Tools that give you no way to correct a bad call

**To sum it up:**

- Site blockers are blunt. Time trackers are passive. FocusGuard judges the current screen against a task you set, locally.

### Feature comparison

| | User owns data | Judges the screen | Interrupts | Correctable examples | Windows |
| --- | :---: | :---: | :---: | :---: | :---: |
| **FocusGuard** | ✅ | ✅ | ✅ | ✅ | ✅ |
| [Cold Turkey](https://getcoldturkey.com/) | ✅ | ❌ | ✅ | ❌ | ✅ |
| [Freedom](https://freedom.to/) | ❌ | ❌ | ✅ | ❌ | ✅ |
| [RescueTime](https://www.rescuetime.com/) | ❌ | ❌ | Limited | ❌ | ✅ |

## About this repository

```text
backend/    FastAPI, vision judge, overlay host
frontend/    React UI (Electron loads frontend/dist)
electron/    Desktop shell
docs/        Design and MVP notes
```

Local runtime data lives in `data/` (gitignored).

## Contributing

Open an [issue](https://github.com/lvxiangyi/FocusGuard/issues) or a pull request against `main`.

### Branches

| Branch | What it is |
| --- | --- |
| `main` | Current product. Session-focused MVP, docs, and API-key setup. Send pull requests here. |
| `dev` | The previous default branch: the packaged 0.1.0 app, before this cut became `main`. |
| `mvp-cut` | Old name for the current `main` line. Use `main` for new work. |
| `dataset-calibration` | Dataset and bench labeling. Not the desktop app default. |

## Questions and support

Same place: [GitHub Issues](https://github.com/lvxiangyi/FocusGuard/issues).
