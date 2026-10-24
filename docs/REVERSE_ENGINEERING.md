# Infina — Observed Public Behavior

Source material: https://www.infina.so/ (home, `/docs`, `/docs/voice-commands`,
`/docs/hands-free-mode`, `/docs/how-infina-works`, `/changelog`), read 2026-10-24.
Only publicly stated behavior is recorded here; anything inferred is marked **(inferred)**.

## Product summary
Hands-free voice interface for Mac (Apple Silicon) and Windows 10/11. Three input modes:
typing, push-to-talk (hold `fn` on Mac / `Right Alt` on Windows), and hands-free.
Tagline: "Open. Type. Send it."

## Hands-free grammar
| Utterance | Needs "Infina"? | Effect |
|---|---|---|
| `type <text>` | No | Types `<text>` at the cursor |
| `send it` | No | Presses Enter **exactly once** (v1.40.55) |
| `open <app>` | No | Launches an installed app |
| `Infina, open <site>` | Yes | Opens a website in the browser |
| `Infina, new chat` / `new tab` / `close this` | Yes | Tab/chat control (Mac) |

- "Typing, sending and opening an app never need it. Everything else does."
- Saying "Infina" wakes the app. The logo turns green, and follow-up commands skip the prefix
  until the configurable **"Stay awake"** window runs out or there is silence.
- Unknown commands are **not** typed (v1.40.50, Sep 14).
- A spoken request is captured once; end-of-speech is detected automatically. Thinking pauses
  no longer end a sentence (v1.40.50). One hands-free capture can last up to **5 minutes**
  (it was 2 minutes before).

## Text formatting
- Self-corrections are cleaned up, and spoken "at", "dot" and "slash" become characters (v1.9.5).
- Real `@` mentions; terminal commands are formatted correctly (v1.40.37).
- The trailing words of a sentence are never cut off (v1.40.60).

## Robustness and privacy
- On-device wake listener; audio is discarded unless a wake word is heard.
- Privacy mode is on by default: no dictation or voice-action history is saved.
- Speech from conversations, TV, calls and other voices in the room is filtered out
  (v1.40.12–v1.40.50).
- Commands report success only once the action has actually finished (v1.11.2).

## Gaps / limits observed (the opportunity)
1. **One intent per utterance.** "open Slack", "type …" and "send it" are separate utterances,
   each with its own wake/capture cycle.
2. **"send it" is blind.** Nothing public says it checks whether text was just typed, or into
   which app. A stray "send it" overheard in the room could submit a half-written message
   **(inferred)**.
3. **No spoken undo** for a mistaken send/type is documented.

## Enhancement implemented in this repo
**Compound commands with a send-safety guard:**
- One utterance can hold an ordered plan:
  `"open Slack, type can we move the call to 3pm and send it"` →
  `OpenApp(Slack) → Type("can we move the call to 3pm") → Send`.
- `send it` runs only when a `type` landed in the **same focused app** within the stay-awake
  window, and has not already been sent. Otherwise it is held as `NeedsConfirm` until the user
  says `confirm`.
- A duplicate `send it` is dropped (Enter is pressed once).
- `scratch that` removes the last typed chunk if it hasn't been sent yet.
