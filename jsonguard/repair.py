"""Fix common syntax problems in near-JSON text produced by LLMs.

Each ``_fix_*`` function is a pure text transformation. ``repair_json``
applies them cumulatively and re-attempts ``json.loads`` after each one,
returning as soon as something parses. This keeps repairs minimal: if
fixing trailing commas alone is enough, quote-style fixes never run.
"""

from __future__ import annotations

import json
import re
from typing import Optional, Tuple

_SMART_QUOTES = {
    "\u201c": '"',
    "\u201d": '"',
    "\u2018": "'",
    "\u2019": "'",
}

_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")
_UNQUOTED_KEY_RE = re.compile(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)(\s*:)')
_PYTHON_LITERAL_RE = re.compile(r"\b(True|False|None)\b")
_SINGLE_QUOTED_STRING_RE = re.compile(r"'((?:[^'\\]|\\.)*)'")


def _fix_smart_quotes(text: str) -> str:
    for smart, straight in _SMART_QUOTES.items():
        text = text.replace(smart, straight)
    return text


def _fix_python_literals(text: str) -> str:
    return _PYTHON_LITERAL_RE.sub(lambda m: {"True": "true", "False": "false", "None": "null"}[m.group(1)], text)


def _fix_trailing_commas(text: str) -> str:
    return _TRAILING_COMMA_RE.sub(r"\1", text)


def _fix_unquoted_keys(text: str) -> str:
    return _UNQUOTED_KEY_RE.sub(r'\1"\2"\3', text)


def _fix_single_quoted_strings(text: str) -> str:
    """Convert 'single quoted' strings to "double quoted", escaping inner quotes.

    Skipped if the text has no single-quoted-looking strings, to avoid
    corrupting apostrophes inside otherwise-valid double-quoted strings.
    """

    def _convert(match: re.Match) -> str:
        inner = match.group(1)
        inner = inner.replace('"', '\\"')
        return f'"{inner}"'

    return _SINGLE_QUOTED_STRING_RE.sub(_convert, text)


def _fix_truncated_json(text: str) -> str:
    """Best-effort close-off for JSON cut short by a token limit.

    Walks the text tracking open brackets/braces and open strings, then
    appends whatever closing characters are needed, trimming a trailing
    incomplete fragment (e.g. a dangling comma) so the result is valid.
    """
    stack = []
    in_string = False
    escape = False

    for ch in text:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack:
                stack.pop()

    if in_string:
        text = text + '"'

    trimmed = text.rstrip()
    trimmed = re.sub(r",\s*$", "", trimmed)
    trimmed = re.sub(r':\s*$', ': null', trimmed)

    closing = ""
    for opener in reversed(stack):
        closing += "}" if opener == "{" else "]"

    return trimmed + closing


# Order matters: cheaper/safer fixes first, structural repair (truncation) last.
_REPAIR_STEPS = [
    _fix_smart_quotes,
    _fix_python_literals,
    _fix_trailing_commas,
    _fix_unquoted_keys,
    _fix_single_quoted_strings,
    _fix_truncated_json,
]


def repair_json(text: str) -> Tuple[Optional[str], bool]:
    """Attempt to turn near-JSON ``text`` into parseable JSON.

    Returns a tuple ``(fixed_text_or_none, changed)``:
    - ``fixed_text_or_none``: text that successfully parses with
      ``json.loads``, or ``None`` if no combination of fixes worked.
    - ``changed``: whether any transformation was actually needed (False if
      the original text already parsed as-is).
    """
    try:
        json.loads(text)
        return text, False
    except json.JSONDecodeError:
        pass

    current = text
    for step in _REPAIR_STEPS:
        current = step(current)
        try:
            json.loads(current)
            return current, True
        except json.JSONDecodeError:
            continue

    return None, True
