"""Demo of jsonguard using fake 'LLM' outputs (no API key required).

Run with: python examples/demo.py
"""

from jsonguard import coerce, parse_json

SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "age": {"type": "integer", "minimum": 0},
    },
    "required": ["name", "age"],
}

print("=== 1. Messy but recoverable output ===")
messy = """Sure, here's the JSON you asked for:
```json
{name: 'Priya', "age": 30,}
```
Let me know if you need anything else!"""

result = parse_json(messy, schema=SCHEMA)
print("ok:", result.ok, "| repaired:", result.repaired, "| data:", result.data)

print("\n=== 2. Truncated output (simulated token cutoff) ===")
truncated = '{"name": "Priya", "age": 30, "bio": "loves hiking and'
result2 = parse_json(truncated, schema=SCHEMA)
print("ok:", result2.ok, "| data:", result2.data)
print("(schema doesn't require 'bio', so this still validates)")

print("\n=== 3. Self-healing retry loop ===")
# Simulated flaky LLM: first response is missing 'age', second is fixed.
responses = iter([
    '{"name": "Priya"}',
    '{"name": "Priya", "age": 30}',
])


def flaky_llm(prompt: str) -> str:
    return next(responses)


coerce_result = coerce(flaky_llm, "Return a person's name and age as JSON.", schema=SCHEMA, max_retries=2)
print("ok:", coerce_result.ok, "| attempts:", coerce_result.n_attempts, "| data:", coerce_result.data)
