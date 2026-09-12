# How to add an API key

FocusGuard needs at least one vision-model key. Screenshots stay on this computer; the key is what pays for the judgment call.

You only need **one** key: the one that matches the model in Preferences.

## 1. Copy the template

Do not type a new file from memory. Copy `.env.example` and rename the copy to `.env`.

| How you run the app | Put `.env` here |
| --- | --- |
| Unpacked release (folder next to the `.exe`) | Same folder as `FocusGuard Agent.exe` |
| Installed app, if there is no `.env` next to the `.exe` | `%APPDATA%\FocusGuard Agent\.env` |
| From source | Repository root (next to `README.md`) |

On Windows:

1. In File Explorer, open **View → Show** and turn on **File name extensions**.
2. Copy `.env.example` → `.env`.
3. If Explorer asks for a file extension, keep the name exactly `.env`. A file named `.env.txt` will be ignored.

Open `.env` with Notepad. When you save: **Save as type = All files**, encoding **UTF-8**. Do not use Unicode / UTF-16.

## 2. Which key to fill

Paste the key on the matching line. Leave the other lines empty.

| Preferences model | Line to fill | Where to get it |
| --- | --- | --- |
| Qwen / GLM / MiniMax / Gemini / GPT or Claude labeled **(OpenRouter)** | `OPENROUTER_API_KEY` | [OpenRouter keys](https://openrouter.ai/keys) |
| GPT-4o mini **(OpenAI official)** | `OPENAI_API_KEY` | [OpenAI API keys](https://platform.openai.com/api-keys) |
| Claude Sonnet 4.5 **(Anthropic official)** | `ANTHROPIC_API_KEY` | [Anthropic console](https://console.anthropic.com/) |
| DeepSeek V4 Flash Vision **(official API)** | `DEEPSEEK_API_KEY` | [DeepSeek platform](https://platform.deepseek.com) |

If you already have an OpenRouter key, start there. That one key can call the OpenRouter GPT and Claude rows; you do not need official OpenAI or Claude accounts for those rows.

`CLAUDE_API_KEY` is an optional alias for `ANTHROPIC_API_KEY`. Prefer the Anthropic name in the template.

## 3. Paste without breaking the file

Correct:

```env
OPENROUTER_API_KEY=sk-or-v1-your-real-key
OPENAI_API_KEY=
```

Wrong (these fail to parse or are ignored):

```env
OPENROUTER_API_KEY = sk-or-v1-your-real-key
OPENROUTER_API_KEY="sk-or-v1-your-real-key"
OPENROUTER_API_KEY=sk-or-v1-your-real-key  # my key
OPENROUTER_API_KEY=your_api_key_here
```

Also avoid:

- spaces or a newline before/after the key
- Chinese quotation marks `“ ”`
- wrapping the whole line in `export`
- putting two keys on one line

Save the file, then fully quit FocusGuard and start it again. The app reads `.env` at startup.

## 4. Check that it worked

1. Open FocusGuard.
2. In Preferences, pick a model that matches the key you filled.
3. Start a short session and wait for the first screenshot check.

If the key is missing or still a placeholder, the app tells you which env name to write. If the check runs and returns on-task / off-task, the file was read.

No OpenAI or Claude account: fill only `OPENROUTER_API_KEY`, pick an **(OpenRouter)** model, and use that path.

## 5. Keep the key off GitHub

`.env` is gitignored. Never paste a live key into an issue, README, or commit. If a key leaked, revoke it on the provider site and create a new one.
