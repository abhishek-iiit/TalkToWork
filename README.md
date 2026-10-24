# handsfree

A reimplementation of [Infina](https://www.infina.so/)'s hands-free voice-command engine, built
from its public behavior, with one added feature: **compound commands with a send-safety
guard**. The research notes are in [docs/REVERSE_ENGINEERING.md](docs/REVERSE_ENGINEERING.md).

You can speak to it (on-device Whisper) or type sentences for testing.

## Speak to it
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m handsfree --listen             # dry run: prints what it would do
.venv/bin/python -m handsfree --listen --execute   # really opens apps, types and sends
```
- The first run downloads the Whisper `base.en` model (~140 MB) and asks for Microphone access
  for your terminal. `--execute` also needs Accessibility access (System Settings → Privacy &
  Security).
- Stay quiet for the 1-second noise check, then speak one command and pause. A sentence ends
  after 1 s of silence; use `--silence 1.5` if you pause mid-thought.
- Options: `--model small.en` (more accurate, slower), `tiny.en` (faster); `--mic N` picks
  an input device.
- Audio never leaves the machine and is discarded after transcription. Speech that isn't
  a command is ignored.

## Commands
- **No wake word needed:** `type …`, `send it` and `open <app>`. Any installed app works,
  and misheard names are matched to the closest app.
- **Start with "Hi Abhishek"** (also accepted: "Hey Abhishek" or just "Abhishek"):
  - opening websites: `Hi Abhishek, open youtube.com`
  - tabs and chats: `new tab`, `new chat`, `close this`
  - `confirm` and `scratch that`

  After you say it, it stays awake for 8 seconds. Change the phrase with `--wake-word "..."`.
- **Chains:** `Open Firefox and open YouTube in it`, `open Slack, type hi team and send it`.
  Once the first step runs, the rest of the sentence doesn't need the wake word.

## Type to it

```
$ python3 -m handsfree --app Notes
> open slack, type um can we move the call to 3pm no wait 4pm and send it
  [done] open_app(Slack)
  [done] type(...) - can we move the call to 4pm
  [done] send - sent
> open notes
> send it
  [needs_confirm] send - nothing typed since the last send; say "Hi Abhishek, confirm" to send anyway
```

`--execute` drives the real Mac desktop through `open` and AppleScript. The terminal running
it needs Accessibility permission.

| Module | Role |
|---|---|
| `handsfree/grammar.py` | Wake word, `type` / `send it` / `open` / tab commands, compound-step splitting |
| `handsfree/formatting.py` | Fillers, self-corrections, spoken `at`/`dot`/`slash`, punctuation |
| `handsfree/session.py` | Stay-awake window, send-once, send guard, confirm, `scratch that` |
| `handsfree/executor.py` | Dry-run recorder and macOS executor |
| `handsfree/listener.py` | Mic capture, end-of-speech detection, Whisper transcription |

Tests: `python3 -m unittest discover -s tests -t .`
