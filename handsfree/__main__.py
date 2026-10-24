"""Runs utterances through a hands-free session.

    python -m handsfree                      # type utterances, dry run
    python -m handsfree --execute            # typed utterances drive the real Mac
    python -m handsfree --listen             # speak into the mic, dry run
    python -m handsfree --listen --execute   # speak, and it really happens
"""

import argparse
import sys
from typing import Iterator

from .executor import MacExecutor, RecordingExecutor
from .grammar import DEFAULT_WAKE_WORD, register_installed_apps
from .session import Session


def typed_lines(session: Session) -> Iterator[str]:
    interactive = sys.stdin.isatty()
    while True:
        if interactive:
            print("awake> " if session.awake else "> ", end="", flush=True)
        line = sys.stdin.readline()
        if not line:
            return
        if line.strip():
            yield line


def main() -> None:
    parser = argparse.ArgumentParser(prog="handsfree")
    parser.add_argument("--execute", action="store_true", help="drive the real Mac desktop")
    parser.add_argument("--listen", action="store_true", help="take commands from the microphone")
    parser.add_argument("--model", default="base.en", help="Whisper model: tiny.en, base.en, small.en")
    parser.add_argument("--mic", default=None, help="input device index or name (default: system mic)")
    parser.add_argument("--silence", type=float, default=1.0, help="seconds of quiet that end a sentence")
    parser.add_argument("--wake-word", default=DEFAULT_WAKE_WORD, help='phrase that wakes it (default "%(default)s")')
    parser.add_argument("--stay-awake", type=float, default=8.0, help="seconds awake after a command")
    parser.add_argument("--app", default="Notes", help="frontmost app to assume in dry-run mode")
    args = parser.parse_args()

    executor = MacExecutor() if args.execute else RecordingExecutor(frontmost=args.app)
    register_installed_apps()
    session = Session(executor, wake_word=args.wake_word, stay_awake=args.stay_awake)

    if args.listen:
        try:
            from .listener import Listener  # needs the optional audio dependencies
        except ImportError as error:
            sys.exit(
                f"--listen needs the audio packages ({error.name} is missing in {sys.executable}).\n"
                "Run it with the project environment:  .venv/bin/python -m handsfree --listen\n"
                "or install them:  python3 -m pip install -r requirements.txt"
            )

        mic = int(args.mic) if args.mic and args.mic.isdigit() else args.mic
        utterances = Listener(args.model, device=mic, silence=args.silence, wake_word=args.wake_word).utterances()
    else:
        utterances = typed_lines(session)

    try:
        for line in utterances:
            if args.listen:
                print(f'heard: "{line}"')
            seen = len(getattr(executor, "calls", []))
            for result in session.handle(line):
                arg = f"({result.intent.arg})" if result.intent.arg else ""
                detail = f" - {result.detail}" if result.detail else ""
                print(f"  [{result.status}] {result.intent.kind}{arg}{detail}", flush=True)
            for call, value in getattr(executor, "calls", [])[seen:]:
                print(f"    -> {call}" + ("" if value is None else f" {value!r}"), flush=True)
    except KeyboardInterrupt:
        print()


if __name__ == "__main__":
    main()
