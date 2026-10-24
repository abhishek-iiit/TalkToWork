"""Executors carry out intents. RecordingExecutor is used for dry runs and tests;
MacExecutor drives the real desktop through `open` and AppleScript."""

import subprocess
import time
from typing import Protocol


class ExecutorError(Exception):
    """An action could not be carried out (app not installed, permission missing, ...)."""


class Executor(Protocol):
    def open_app(self, app: str) -> None: ...
    def open_url(self, url: str, app: str | None = None) -> None: ...
    def type_text(self, text: str) -> None: ...
    def press_enter(self) -> None: ...
    def delete_chars(self, count: int) -> None: ...
    def tab_command(self, command: str) -> None: ...
    def open_chat(self, app: str, person: str) -> None: ...
    def frontmost_app(self) -> str | None: ...


class RecordingExecutor:
    def __init__(self, frontmost: str | None = None):
        self.calls: list[tuple[str, object]] = []
        self.frontmost = frontmost

    def open_app(self, app):
        self.calls.append(("open_app", app))
        self.frontmost = app

    def open_url(self, url, app=None):
        self.calls.append(("open_url", f"{url} in {app}" if app else url))

    def type_text(self, text):
        self.calls.append(("type_text", text))

    def press_enter(self):
        self.calls.append(("press_enter", None))

    def delete_chars(self, count):
        self.calls.append(("delete_chars", count))

    def tab_command(self, command):
        self.calls.append(("tab_command", command))

    def open_chat(self, app, person):
        self.calls.append(("open_chat", f"{person} in {app}"))

    def frontmost_app(self):
        return self.frontmost


TAB_KEYSTROKES = {"new tab": "t", "new chat": "n", "close this": "w"}


def _run(args: list[str], input: str | None = None) -> str:
    result = subprocess.run(args, input=input, capture_output=True, text=True)
    if result.returncode != 0:
        raise ExecutorError(result.stderr.strip() or f"{args[0]} exited with {result.returncode}")
    return result.stdout.strip()


def _osascript(script: str) -> str:
    return _run(["osascript", "-e", script])


class MacExecutor:
    """Needs Accessibility permission for the terminal running it (System Events keystrokes)."""

    def open_app(self, app):
        before = self.frontmost_app()
        _run(["open", "-a", app])
        # `open` returns before the app is in front; typing straight away would land in the
        # previous app. Process names can differ from app names ("Code" for VS Code), so wait
        # for focus to move rather than for an exact name.
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            front = self.frontmost_app()
            if front == app or (front != before and before != app):
                break
            time.sleep(0.1)
        time.sleep(0.3)  # let the app focus its text field

    def open_url(self, url, app=None):
        _run(["open", *(["-a", app] if app else []), url])

    def type_text(self, text):
        # Paste rather than keystroke so non-ASCII text and long dictation land intact.
        _run(["pbcopy"], input=text)
        _osascript('tell application "System Events" to keystroke "v" using command down')

    def press_enter(self):
        _osascript('tell application "System Events" to key code 36')

    def delete_chars(self, count):
        _osascript(f'tell application "System Events" to repeat {count} times\nkey code 51\nend repeat')

    def tab_command(self, command):
        key = TAB_KEYSTROKES[command]
        _osascript(f'tell application "System Events" to keystroke "{key}" using command down')

    def open_chat(self, app, person):
        # Slack and Discord both jump to a conversation from the Cmd+K quick switcher, which
        # picks its top match for the name.
        _osascript('tell application "System Events" to keystroke "k" using command down')
        time.sleep(0.5)
        self.type_text(person)
        time.sleep(1.2)  # let the switcher search
        self.press_enter()
        time.sleep(1.0)  # let the conversation load and focus its message box

    def frontmost_app(self):
        return _osascript(
            'tell application "System Events" to get name of first application process whose frontmost is true'
        )
