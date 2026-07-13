"""jsonguard: validators and repair tools for LLM JSON responses.

Quick start:
    >>> from jsonguard import parse_json

    >>> raw = '''Here's the JSON you asked for:
    ... ```json
    ... {"name": "Priya", "age": 30,}
    ... ```
    ... '''
    >>> result = parse_json(raw)
    >>> result.ok, result.data
    (True, {'name': 'Priya', 'age': 30})

With a schema:
    >>> schema = {
    ...     "type": "object",
    ...     "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
    ...     "required": ["name", "age"],
    ... }
    >>> parse_json(raw, schema=schema).ok
    True

Self-healing against a live model:
    >>> from jsonguard import coerce
    >>> result = coerce(call_my_llm, prompt, schema=schema, max_retries=2)
    >>> result.ok
"""

from .core import ParseResult, parse_json
from .extract import extract_json_str
from .repair import repair_json
from .retry import CoerceResult, coerce
from .schema import validate

__version__ = "0.1.0"
__all__ = [
    "parse_json",
    "ParseResult",
    "extract_json_str",
    "repair_json",
    "validate",
    "coerce",
    "CoerceResult",
]
