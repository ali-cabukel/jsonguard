"""Self-healing loop: if the model's output doesn't parse/validate, ask it to fix it.

This is the "structured output that repairs itself" story — rather than
only fixing syntax locally, ``coerce`` can go back to the model with the
specific error and a fresh chance to produce valid output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, List

from .core import ParseResult, parse_json

LLMFn = Callable[[str], str]


@dataclass
class CoerceResult:
    """Outcome of a (possibly multi-attempt) coerce() call."""

    final: ParseResult
    attempts: List[ParseResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.final.ok

    @property
    def data(self) -> Any:
        return self.final.data

    @property
    def n_attempts(self) -> int:
        return len(self.attempts)

    def unwrap(self) -> Any:
        return self.final.unwrap()


def _default_repair_prompt(original_prompt: str, last_output: str, result: ParseResult) -> str:
    if not result.parsed:
        problem = f"the output could not be parsed as JSON: {result.parse_error}"
    else:
        problem = f"the JSON was valid but did not match the required schema: {result.validation_errors}"

    return (
        f"{original_prompt}\n\n"
        "Your previous response did not meet the requirements.\n"
        f"Previous response:\n{last_output}\n\n"
        f"Problem: {problem}\n\n"
        "Please respond again with ONLY valid JSON that fixes this problem. "
        "Do not include any explanation, markdown formatting, or text outside the JSON."
    )


def coerce(
    fn: LLMFn,
    prompt: str,
    schema: Any = None,
    max_retries: int = 2,
    repair: bool = True,
    build_repair_prompt: Callable[[str, str, ParseResult], str] = _default_repair_prompt,
) -> CoerceResult:
    """Call ``fn(prompt)``, parse/validate the result, and retry on failure.

    On each failed attempt (parse failure or schema validation failure),
    a follow-up prompt is built via ``build_repair_prompt`` — by default,
    it includes the previous output and the specific error — and sent to
    ``fn`` again. Stops as soon as an attempt succeeds or ``max_retries``
    is exhausted.

    Args:
        fn: Callable that sends a prompt to your LLM and returns its text
            response. jsonguard never calls a model itself.
        prompt: The initial prompt.
        schema: Optional JSON-schema-subset dict or pydantic model to
            validate against.
        max_retries: Number of additional attempts after the first
            (so `max_retries=2` means up to 3 total calls to `fn`).
        repair: Whether local syntax repair is attempted before giving up
            on an attempt and asking the model to retry.
        build_repair_prompt: Customize the follow-up prompt sent to the
            model after a failed attempt.
    """
    attempts: List[ParseResult] = []
    current_prompt = prompt
    last_output = ""

    for attempt_index in range(max_retries + 1):
        last_output = fn(current_prompt)
        result = parse_json(last_output, schema=schema, repair=repair)
        attempts.append(result)

        if result.ok:
            return CoerceResult(final=result, attempts=attempts)

        if attempt_index < max_retries:
            current_prompt = build_repair_prompt(prompt, last_output, result)

    return CoerceResult(final=attempts[-1], attempts=attempts)
