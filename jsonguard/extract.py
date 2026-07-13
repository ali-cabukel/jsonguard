"""Pull the JSON candidate out of a raw LLM response.

LLMs routinely wrap JSON in markdown fences, prepend "Here's the JSON:",
or append a trailing sentence. This module isolates the likely JSON
substring before ``repair.py`` fixes syntax problems within it.
"""

from __future__ import annotations

import re

_FENCE_RE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)


def extract_json_str(text: str) -> str:
    """Return the most likely JSON substring within ``text``.

    Strategy, in order:
    1. If there's a fenced code block (```json ... ```` or plain ``` ... ```),
       use its contents.
    2. Otherwise, find the first opening bracket ('{' or '[') and the
       matching closing bracket by counting depth, ignoring brackets
       inside string literals.
    3. If no brackets are found at all, return the text unchanged (nothing
       to extract; repair/parsing will report the failure).
    """
    fence_match = _FENCE_RE.search(text)
    if fence_match:
        candidate = fence_match.group(1).strip()
        if candidate:
            text = candidate

    start = _find_first_bracket(text)
    if start is None:
        return text.strip()

    end = _find_matching_close(text, start)
    if end is None:
        # Truncated JSON: no matching close found. Return from the opening
        # bracket to the end of the text; repair.py will try to close it.
        return text[start:].strip()

    return text[start : end + 1].strip()


def _find_first_bracket(text: str):
    for i, ch in enumerate(text):
        if ch in "{[":
            return i
    return None


def _find_matching_close(text: str, start: int):
    """Find the index of the bracket that closes the one at ``start``.

    Walks the string tracking nesting depth, correctly skipping over
    bracket characters that appear inside quoted strings.
    """
    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        ch = text[i]
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
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                return i
    return None
