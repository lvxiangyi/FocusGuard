# FocusGuard

*Watches your screen during a focus session so you can stay on the task.*  
*Screenshots and labels stay on your machine.*

**[Releases](https://github.com/lvxiangyi/FocusGuard/releases)**

<details>
<summary>Table of Contents</summary>

- [About](#about)
- [Installation & Usage](#installation--usage)
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

Downloads: [releases](https://github.com/lvxiangyi/FocusGuard/releases) (`mvp-app-v0.1.0`).

From source:

```bat
setup_windows.bat
```

Put an API key in `.env` at the repo root (`OPENROUTER_API_KEY=...`). Then:

```bat
start_stable.bat
```

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

Open an [issue](https://github.com/lvxiangyi/FocusGuard/issues) or a pull request.

## Questions and support

Same place: [GitHub Issues](https://github.com/lvxiangyi/FocusGuard/issues).
