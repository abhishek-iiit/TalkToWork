"""Parses a spoken utterance into an ordered list of intents.

Infina's base grammar handles one intent per utterance. Here one utterance can also carry a
chain such as "open Slack, type hi team and send it" or "open Firefox and open YouTube in it".
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

DEFAULT_WAKE_WORD = "Hi Abhishek"
# Whisper hears the same greeting several ways.
GREETINGS = {"hi": "hi", "hey": "hi", "hello": "hi", "hai": "hi"}

# Spoken name -> app name passed to the OS. Seeded from Infina's published integrations.
APPS = {
    "claude": "Claude",
    "claude code": "Terminal",
    "codex": "Codex",
    "cursor": "Cursor",
    "chatgpt": "ChatGPT",
    "chat gpt": "ChatGPT",
    "terminal": "Terminal",
    "vs code": "Visual Studio Code",
    "vscode": "Visual Studio Code",
    "xcode": "Xcode",
    "slack": "Slack",
    "gmail": "Mail",
    "mail": "Mail",
    "notion": "Notion",
    "linear": "Linear",
    "notes": "Notes",
    "safari": "Safari",
    "chrome": "Google Chrome",
    "firefox": "Firefox",
}

BROWSERS = {"Safari", "Google Chrome", "Firefox", "Arc", "Brave Browser", "Microsoft Edge"}
APP_FOLDERS = ["/Applications", "/System/Applications", "/System/Applications/Utilities",
               str(Path.home() / "Applications")]

SITES = {
    "gemini": "https://gemini.google.com",
    "perplexity": "https://www.perplexity.ai",
    "youtube": "https://www.youtube.com",
    "chatgpt": "https://chatgpt.com",
}

TAB_COMMANDS = {"new chat", "new tab", "close this"}


@dataclass(frozen=True)
class Intent:
    kind: str  # wake | type | send | open_app | open_site | tab | confirm | undo | unknown
    arg: str = ""
    target: str = ""  # open_site: browser to use; "@last" means the app just opened ("in it")


def register_installed_apps(folders: list[str] = APP_FOLDERS) -> None:
    """Makes every installed app openable by name ("open whatever you have installed")."""
    for folder in folders:
        for bundle in Path(folder).glob("*.app"):
            APPS.setdefault(bundle.stem.lower(), bundle.stem)


def resolve_app(spoken: str, fuzzy: bool = True) -> str | None:
    name = spoken.strip().lower().rstrip(".!?")
    if name in APPS:
        return APPS[name]
    if not fuzzy or name in SITES:
        return None
    # Speech recognition often garbles app names ("Cusser" for Cursor, "nodes" for Notes).
    score, best = max((SequenceMatcher(None, name, known).ratio(), known) for known in APPS)
    return APPS[best] if score >= 0.6 else None


def resolve_site(spoken: str) -> str:
    target = spoken.strip().rstrip(".!").lower().replace(" dot ", ".")
    if target in SITES:
        return SITES[target]
    if "." in target and " " not in target:
        return target if target.startswith("http") else f"https://{target}"
    return "https://www.google.com/search?q=" + "+".join(target.split())


_IN_APP = re.compile(r"^(.*)\s(?:in|on|with|using)\s+(.+)$", re.IGNORECASE)
_PAGE_WORDS = re.compile(r"\s+(?:url|website|web site|site|page|link)$", re.IGNORECASE)


def parse_open(target: str) -> Intent:
    """"Firefox" -> open_app; "YouTube URL in it" / "youtube in Safari" -> open_site in a browser."""
    target = target.strip().rstrip(".!?")
    browser = ""
    match = _IN_APP.match(target)  # greedy, so the last "in" wins: "news in new york in Safari"
    if match:
        where = match[2].strip().lower()
        if where in {"it", "there", "that", "this", "the browser"}:
            browser = "@last"
        elif resolve_app(where) in BROWSERS:
            browser = resolve_app(where)
        if browser:
            target = match[1]
    target = _PAGE_WORDS.sub("", target.strip())
    if not browser:
        app = resolve_app(target)
        if app:
            return Intent("open_app", app)
    return Intent("open_site", resolve_site(target), browser)


# Whisper often ends each spoken command with a full stop, so sentence ends separate steps too.
_SEP = r"(?:\s*[,.!?]\s*(?:and\s+)?(?:then\s+)?|\s+and\s+then\s+|\s+then\s+|\s+and\s+)"
# A new step starts at a separator followed by a command keyword. "send it" only counts at the
# end of the utterance, so "type ... and send it tomorrow" stays text.
_SPLIT = re.compile(
    _SEP + r"(?=(?:type\b|open\b|send it[.!]?$|new chat\b|new tab\b|close this\b|scratch that[.!]?$))",
    re.IGNORECASE,
)
_OPEN_TARGET = re.compile(r"open\s+(.+?)(?:\s*[,.!?]|\s+and\b|\s+then\b|$)", re.IGNORECASE)


def split_steps(utterance: str) -> list[str]:
    text = utterance.strip()
    steps, start = [], 0
    for match in _SPLIT.finditer(text):
        current, rest = text[start:match.start()], text[match.end():]
        # While dictating, "open" only starts a new step before an installed app, so
        # "type please open the door" stays one piece of text.
        if current.strip().lower().startswith("type ") and rest.lower().startswith("open"):
            target = _OPEN_TARGET.match(rest)
            if not (target and resolve_app(target[1], fuzzy=False)):
                continue
        steps.append(current)
        start = match.end()
    steps.append(text[start:])
    return [step.strip() for step in steps if step.strip()]


def parse_step(step: str) -> Intent:
    text = step.strip()
    lowered = text.lower().rstrip(".!? ")
    if lowered.startswith("type "):
        return Intent("type", text[5:].strip())
    if lowered == "send it":
        return Intent("send")
    if lowered in {"confirm", "yes send it", "yes, send it"}:
        return Intent("confirm")
    if lowered in {"scratch that", "undo that"}:
        return Intent("undo")
    if lowered in TAB_COMMANDS:
        return Intent("tab", lowered)
    if lowered.startswith("open "):
        return parse_open(text[5:])
    return Intent("unknown", text)


def _normalize(word: str) -> str:
    word = word.lower()
    return GREETINGS.get(word, word)


def strip_wake_word(text: str, wake_word: str) -> str | None:
    """Returns what follows the wake word, or None if the utterance doesn't start with it.

    Matching is fuzzy because Whisper spells names inconsistently ("Hey, Abishek."), and the
    name alone also counts when the wake word starts with a greeting.
    """
    phrase = [_normalize(w) for w in wake_word.split()]
    candidates = [phrase]
    if len(phrase) > 1 and phrase[0] in GREETINGS.values():
        candidates.append(phrase[1:])
    tokens = list(re.finditer(r"[^\s,.!?]+", text))
    for candidate in candidates:
        n = len(candidate)
        if len(tokens) < n:
            continue
        heard = " ".join(_normalize(t[0]) for t in tokens[:n])
        if SequenceMatcher(None, heard, " ".join(candidate)).ratio() >= 0.75:
            return text[tokens[n - 1].end():].lstrip(" ,.!?")
    return None


def parse_utterance(utterance: str, wake_word: str = DEFAULT_WAKE_WORD) -> list[Intent]:
    text = utterance.strip()
    intents = []
    rest = strip_wake_word(text, wake_word)
    if rest is not None:
        intents.append(Intent("wake"))
        text = rest
    intents.extend(parse_step(step) for step in split_steps(text))
    return intents
