"""Turns raw dictation transcripts into the text that should land at the cursor.

Mirrors Infina's public formatting behavior: filler removal, self-corrections,
spoken symbols ("at", "dot", "slash") and spoken punctuation.
"""

import re

FILLERS = re.compile(r"\b(?:um+|uh+|erm+|hmm+)\b[,]?\s*", re.IGNORECASE)
CORRECTION = re.compile(r"[,\s]*\b(?:no wait|scratch that)\b[,]?\s*", re.IGNORECASE)

# "dot" only becomes "." before something that looks like a domain or file extension,
# so "a dot on the map" stays as typed.
SUFFIXES = {
    "com", "org", "net", "io", "ai", "so", "dev", "app", "co", "edu", "gov", "uk",
    "py", "js", "ts", "tsx", "jsx", "md", "json", "yaml", "yml", "txt", "html", "css", "sh",
}

PUNCTUATION = [
    (r"\s*\bnew paragraph\b\s*", "\n\n"),
    (r"\s*\bnew line\b\s*", "\n"),
    (r"\s*\bquestion mark\b", "?"),
    (r"\s*\bexclamation (?:mark|point)\b", "!"),
    (r"\s*\b(?:full stop|period)\b", "."),
    (r"\s*\bcomma\b", ","),
    (r"\s*\bcolon\b", ":"),
]


def apply_corrections(text: str) -> str:
    """'move it to 3pm no wait 4pm' -> 'move it to 4pm'.

    The words after the correction marker replace the same number of words just before it,
    which matches how people usually correct themselves mid-sentence.
    """
    parts = CORRECTION.split(text)
    result = parts[0].split()
    for replacement in parts[1:]:
        words = replacement.split()
        # Only the phrase up to the next clause boundary counts as the replacement.
        clause = re.split(r"(?<=[,.;!?])\s", replacement, maxsplit=1)[0].split()
        drop = min(len(clause), len(result))
        result = result[: len(result) - drop] + words
    return " ".join(result)


def apply_symbols(text: str) -> str:
    # Email: "jane at acme dot com" -> "jane@acme.com"
    text = re.sub(
        r"\b([\w.]+) at ([\w-]+) dot (\w+)\b",
        lambda m: f"{m[1]}@{m[2]}.{m[3]}" if m[3].lower() in SUFFIXES else m[0],
        text,
        flags=re.IGNORECASE,
    )
    # Whisper often writes the domain itself: "jane at acme.com"
    text = re.sub(
        r"\b([\w.]+) at ([\w-]+)\.(\w+)\b",
        lambda m: f"{m[1]}@{m[2]}.{m[3]}" if m[3].lower() in SUFFIXES else m[0],
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\bat sign\s+", "@", text, flags=re.IGNORECASE)
    text = re.sub(
        r"(\S) dot (\w+)\b",
        lambda m: f"{m[1]}.{m[2]}" if m[2].lower() in SUFFIXES else m[0],
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\s*\bslash\b\s*", "/", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*\bdash dash\s+", " --", text, flags=re.IGNORECASE)
    return text


def apply_punctuation(text: str) -> str:
    for pattern, replacement in PUNCTUATION:
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def format_dictation(text: str) -> str:
    text = FILLERS.sub("", text)
    text = apply_corrections(text)
    text = apply_symbols(text)
    text = apply_punctuation(text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip(" \t")
