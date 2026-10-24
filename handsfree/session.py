"""Hands-free session state machine.

Base behavior (from Infina's public docs):
  * "type", "send it" and "open <app>" work without the wake word.
  * Everything else needs the wake word (Infina uses "Infina"; ours defaults to "Hi Abhishek").
    Saying it keeps the session awake for `stay_awake` seconds, and every accepted command
    restarts that window.
  * Unknown commands are dropped, never typed.
  * "send it" presses Enter exactly once.

Enhancement — send-safety guard:
  * "send it" fires only if a "type" landed in the same frontmost app within
    `send_window` seconds and hasn't been sent. Otherwise it is held until "confirm".
  * "scratch that" deletes the last unsent typed chunk.

Enhancement — chains: once a step in an utterance has run, the steps after it don't need the
wake word ("open Firefox and open YouTube in it"); the chain itself shows intent.
"""

import time
from dataclasses import dataclass, field
from typing import Callable

from .executor import Executor, ExecutorError
from .formatting import format_dictation
from .grammar import DEFAULT_WAKE_WORD, Intent, parse_utterance

NEEDS_WAKE = {"open_site", "tab", "confirm", "undo"}


@dataclass
class Result:
    status: str  # done | ignored | needs_confirm | duplicate | failed
    intent: Intent
    detail: str = ""


@dataclass
class _Typed:
    text: str
    app: str | None
    at: float
    sent: bool = False


@dataclass
class Session:
    executor: Executor
    wake_word: str = DEFAULT_WAKE_WORD
    stay_awake: float = 8.0
    send_window: float = 60.0
    confirm_window: float = 10.0
    duplicate_window: float = 2.0
    clock: Callable[[], float] = time.monotonic
    awake_until: float = field(default=float("-inf"), init=False)
    _last_typed: _Typed | None = field(default=None, init=False)
    _last_send_at: float = field(default=float("-inf"), init=False)
    _held_send_at: float | None = field(default=None, init=False)
    _last_opened_app: str | None = field(default=None, init=False)

    @property
    def awake(self) -> bool:
        return self.clock() < self.awake_until

    def handle(self, utterance: str) -> list[Result]:
        intents = parse_utterance(utterance, self.wake_word)
        # Anything not understood cancels the whole chain: running half of a misheard
        # instruction is worse than running none of it.
        unknown = [i for i in intents if i.kind == "unknown"]
        if unknown:
            return [Result("ignored", i, "not a command; nothing typed") for i in intents]

        results = []
        chained = False  # an earlier step of this utterance already ran
        for intent in intents:
            if intent.kind in NEEDS_WAKE and not (self.awake or chained):
                results.append(Result("ignored", intent, f'say "{self.wake_word}" first'))
                continue
            try:
                result = self._run(intent)
            except ExecutorError as error:
                # Stop the chain: after a failed "open Slack", typing would land in whatever
                # app happens to be in front.
                results.append(Result("failed", intent, str(error)))
                break
            if result.status in {"done", "needs_confirm"} and (self.awake or intent.kind == "wake"):
                self.awake_until = self.clock() + self.stay_awake
            results.append(result)
            chained = chained or result.status == "done"
            if result.status == "needs_confirm":
                break  # Steps after a held send would act on the wrong state.
        return results

    def _focus(self) -> str | None:
        return self.executor.frontmost_app()

    def _run(self, intent: Intent) -> Result:
        now = self.clock()
        ex = self.executor
        if intent.kind == "wake":
            return Result("done", intent, "awake")
        if intent.kind == "open_app":
            ex.open_app(intent.arg)
            self._last_opened_app = intent.arg
            return Result("done", intent)
        if intent.kind == "open_site":
            browser = self._last_opened_app if intent.target == "@last" else intent.target
            ex.open_url(intent.arg, browser or None)
            return Result("done", intent, f"in {browser}" if browser else "")
        if intent.kind == "tab":
            ex.tab_command(intent.arg)
            return Result("done", intent)
        if intent.kind == "type":
            text = format_dictation(intent.arg)
            if not text:
                return Result("ignored", intent, "nothing to type")
            # Successive "type" steps before a send are one message: join with a space.
            if self._last_typed and not self._last_typed.sent and self._last_typed.app == self._focus():
                text = " " + text
                self._last_typed.text += text
                self._last_typed.at = now
            else:
                self._last_typed = _Typed(text, self._focus(), now)
            ex.type_text(text)
            return Result("done", intent, text.strip())
        if intent.kind == "send":
            return self._send(intent, now)
        if intent.kind == "confirm":
            if self._held_send_at is None or now - self._held_send_at > self.confirm_window:
                return Result("ignored", intent, "no send waiting for confirmation")
            self._held_send_at = None
            return self._press_enter(intent, now)
        if intent.kind == "undo":
            typed = self._last_typed
            if not typed or typed.sent or typed.app != self._focus():
                return Result("ignored", intent, "nothing unsent to remove here")
            ex.delete_chars(len(typed.text))
            self._last_typed = None
            return Result("done", intent, f"removed {len(typed.text)} characters")
        return Result("ignored", intent)

    def _send(self, intent: Intent, now: float) -> Result:
        typed = self._last_typed
        if typed and typed.sent and now - self._last_send_at <= self.duplicate_window:
            return Result("duplicate", intent, "already sent")
        if typed is None or typed.sent:
            reason = "nothing typed since the last send"
        elif typed.app != self._focus():
            reason = f"text was typed in {typed.app}, but {self._focus()} is in front"
        elif now - typed.at > self.send_window:
            reason = f"last text was typed {now - typed.at:.0f}s ago"
        else:
            return self._press_enter(intent, now)
        self._held_send_at = now
        return Result("needs_confirm", intent, reason + f'; say "{self.wake_word}, confirm" to send anyway')

    def _press_enter(self, intent: Intent, now: float) -> Result:
        self.executor.press_enter()
        if self._last_typed:
            self._last_typed.sent = True
        self._last_send_at = now
        return Result("done", intent, "sent")
