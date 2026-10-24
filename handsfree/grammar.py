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
    "discord": "Discord",
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

# Apps whose Cmd+K quick switcher opens a conversation by typing a person's name.
CHAT_APPS = {"Slack", "Discord"}
DEFAULT_CHAT_APP = "Slack"


@dataclass(frozen=True)
class Intent:
    kind: str  # wake | type | send | open_app | open_site | tab | chat | confirm | undo | unknown
    arg: str = ""
    # open_site: browser to use; "@last" means the app just opened ("in it").
    # chat: the app to find the person (arg) in.
    target: str = ""


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


_APP_WORDS = re.compile(r"\s+(?:app|application)$", re.IGNORECASE)


def resolve_app_name(spoken: str, fuzzy: bool = True) -> str | None:
    """Like resolve_app, but also accepts "Slack app"."""
    return resolve_app(_APP_WORDS.sub("", spoken.strip().rstrip(".!?")), fuzzy)


def resolve_site(spoken: str) -> str:
    target = spoken.strip().rstrip(".!").lower().replace(" dot ", ".")
    if target in SITES:
        return SITES[target]
    if "." in target and " " not in target:
        return target if target.startswith("http") else f"https://{target}"
    return "https://www.google.com/search?q=" + "+".join(target.split())


_IN_APP = re.compile(r"^(.*)\s(?:in|on|with|using)\s+(.+)$", re.IGNORECASE)
_PAGE_WORDS = re.compile(r"\s+(?:url|website|web site|site|page|link)$", re.IGNORECASE)
_HEAD_AND_REST = re.compile(r"^(.+?)(?:\s*,\s*|\s+and\s+|\s+then\s+)(.+)$", re.IGNORECASE)


def parse_open(target: str) -> list[Intent]:
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
        app = resolve_app_name(target)
        if app:
            return [Intent("open_app", app)]
        # "open Slack app and tell Super hi": the rest wasn't a command we know. Flag it rather
        # than searching the web for the whole sentence.
        match = _HEAD_AND_REST.match(target)
        app = match and resolve_app_name(match[1], fuzzy=False)
        if app:
            return [Intent("open_app", app), Intent("unknown", match[2])]
    return [Intent("open_site", resolve_site(target), browser)]


# Whisper often ends each spoken command with a full stop, so sentence ends separate steps too.
_SEP = r"(?:\s*[,.!?]\s*(?:and\s+)?(?:then\s+)?|\s+and\s+then\s+|\s+then\s+|\s+and\s+)"
# A new step starts at a separator followed by a command keyword. "send it" only counts at the
# end of the utterance, so "type ... and send it tomorrow" stays text.
_SPLIT = re.compile(
    _SEP + r"(?=(?:type\b|open\b|send it[.!]?$|send\s.+\sto\s|message\s|text\s|new chat\b|new tab\b|close this\b"
    r"|scratch that[.!]?$))",
    re.IGNORECASE,
)
_SPLIT_SEND_IT = re.compile(r"send it[.!]?$", re.IGNORECASE)
_OPEN_TARGET = re.compile(r"open\s+(.+?)(?:\s*[,.!?]|\s+and\b|\s+then\b|$)", re.IGNORECASE)


def split_steps(utterance: str) -> list[str]:
    text = utterance.strip()
    steps, start = [], 0
    for match in _SPLIT.finditer(text):
        current, rest = text[start:match.start()], text[match.end():]
        # While dictating, "open" only starts a new step before an installed app, so
        # "type please open the door" stays one piece of text.
        dictating = current.strip().lower().startswith("type ")
        if dictating and rest.lower().startswith("open"):
            target = _OPEN_TARGET.match(rest)
            if not (target and resolve_app(target[1], fuzzy=False)):
                continue
        # Nor does dictation ever start a message to someone: "type I'll check and send the
        # notes to Priya" is text.
        if dictating and re.match(r"(?:send|message|text)\s", rest, re.IGNORECASE) and not _SPLIT_SEND_IT.match(rest):
            continue
        steps.append(current)
        start = match.end()
    steps.append(text[start:])
    return [step.strip() for step in steps if step.strip()]


# "send hi to Priya", "send hi to Priya in Slack" (the last "to" names the person) and
# "message Priya saying hi".
_SEND_TO = re.compile(r"^send\s+(.+)\s+to\s+(.+?)(?:\s+(?:in|on)\s+(.+))?$", re.IGNORECASE)
_MESSAGE = re.compile(r"^(?:message|text)\s+(.+?)\s+(?:saying|that)\s+(.+?)(?:\s+(?:in|on)\s+(.+))?$", re.IGNORECASE)


def parse_message(text: str) -> list[Intent] | None:
    """A message to a person: open their chat, type it, send it. None if it isn't one."""
    text = text.rstrip(".!?")
    if match := _SEND_TO.match(text):
        message, person, where = match[1], match[2], match[3]
    elif match := _MESSAGE.match(text):
        person, message, where = match[1], match[2], match[3]
    else:
        return None
    if message.lower() in {"it", "this", "that"}:
        return [Intent("unknown", text)]  # forwarding something isn't supported
    app = ""
    if where:
        app = resolve_app_name(where)
        if app not in CHAT_APPS:
            return [Intent("unknown", text)]
    return [Intent("chat", person.strip(), app), Intent("type", message.strip()), Intent("send")]


def parse_step(step: str) -> list[Intent]:
    text = step.strip()
    lowered = text.lower().rstrip(".!? ")
    if lowered.startswith("type "):
        return [Intent("type", text[5:].strip())]
    if lowered == "send it":
        return [Intent("send")]
    if lowered in {"confirm", "yes send it", "yes, send it"}:
        return [Intent("confirm")]
    if lowered in {"scratch that", "undo that"}:
        return [Intent("undo")]
    if lowered in TAB_COMMANDS:
        return [Intent("tab", lowered)]
    if lowered.startswith("open "):
        return parse_open(text[5:])
    return parse_message(text) or [Intent("unknown", text)]


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
    for step in split_steps(text):
        for intent in parse_step(step):
            if intent.kind == "chat":
                # The chat app: named in the step, else the one this utterance opened, else Slack.
                opened = [i.arg for i in intents if i.kind == "open_app"]
                app = intent.target or (opened[-1] if opened and opened[-1] in CHAT_APPS else DEFAULT_CHAT_APP)
                if intents[-1:] != [Intent("open_app", app)]:
                    intents.append(Intent("open_app", app))
                intent = Intent("chat", intent.arg, app)
            intents.append(intent)
    return intents
