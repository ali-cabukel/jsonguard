"""High-level entry point: turn a raw LLM response into validated data."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, List, Optional

from .extract import extract_json_str
from .repair import repair_json
from .schema import validate as validate_schema


@dataclass
class ParseResult:
    """Outcome of parsing (and optionally validating) an LLM response.

    Attributes:
        data: The parsed Python object (dict/list/etc), or None if parsing failed.
        ok: True if parsing succeeded AND schema validation (if any) passed.
        parsed: True if JSON parsing succeeded, regardless of schema validity.
        repaired: True if the raw text needed fixing before it would parse.
        raw_text: The original input string.
        cleaned_text: The text that actually parsed, after extraction/repair.
        parse_error: Error message if parsing failed entirely.
        validation_errors: List of schema validation errors (empty if valid
            or no schema was given).
    """

    data: Any
    ok: bool
    parsed: bool
    repaired: bool
    raw_text: str
    cleaned_text: Optional[str] = None
    parse_error: Optional[str] = None
    validation_errors: List[str] = field(default_factory=list)

    def __repr__(self) -> str:
        status = "ok" if self.ok else ("parsed-but-invalid" if self.parsed else "failed")
        return f"<ParseResult {status} repaired={self.repaired}>"

    def unwrap(self) -> Any:
        """Return ``data``, raising ValueError with details if parsing/validation failed.

        Convenient for call sites that want exceptions instead of checking
        ``.ok`` themselves.
        """
        if not self.parsed:
            raise ValueError(f"Could not parse JSON from response: {self.parse_error}")
        if self.validation_errors:
            raise ValueError(f"JSON parsed but failed schema validation: {self.validation_errors}")
        return self.data


def parse_json(text: str, schema: Any = None, repair: bool = True) -> ParseResult:
    """Parse ``text`` (a raw LLM response) into a validated Python object.

    Tries, in order:
    1. Direct ``json.loads`` on the raw text.
    2. Extracting a JSON substring (stripping markdown fences / surrounding prose).
    3. If ``repair=True``, applying syntax repairs (trailing commas, single
       quotes, unquoted keys, Python literals, truncated JSON) to whichever
       candidate text didn't parse.

    If ``schema`` is given (a JSON-schema-subset dict or a pydantic model),
    the parsed data is validated and any errors are recorded in
    ``validation_errors``; ``ok`` is only True when parsing AND validation
    both succeed.
    """
    raw = text

    # 1. Direct parse.
    try:
        data = json.loads(raw)
        return _finish(data, schema, repaired=False, raw=raw, cleaned=raw)
    except json.JSONDecodeError:
        pass

    # 2. Extract a JSON-looking substring.
    candidate = extract_json_str(raw)
    try:
        data = json.loads(candidate)
        return _finish(data, schema, repaired=(candidate != raw), raw=raw, cleaned=candidate)
    except json.JSONDecodeError:
        pass

    # 3. Repair syntax issues, if allowed.
    if repair:
        fixed, changed = repair_json(candidate)
        if fixed is not None:
            try:
                data = json.loads(fixed)
                return _finish(data, schema, repaired=True, raw=raw, cleaned=fixed)
            except json.JSONDecodeError as exc:
                return ParseResult(
                    data=None, ok=False, parsed=False, repaired=changed,
                    raw_text=raw, cleaned_text=fixed, parse_error=str(exc),
                )

    return ParseResult(
        data=None, ok=False, parsed=False, repaired=False,
        raw_text=raw, cleaned_text=candidate,
        parse_error="No combination of extraction/repair produced valid JSON.",
    )


def _finish(data: Any, schema: Any, repaired: bool, raw: str, cleaned: str) -> ParseResult:
    validation_errors = validate_schema(data, schema) if schema is not None else []
    return ParseResult(
        data=data,
        ok=not validation_errors,
        parsed=True,
        repaired=repaired,
        raw_text=raw,
        cleaned_text=cleaned,
        validation_errors=validation_errors,
    )
