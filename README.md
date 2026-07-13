# jsonguard

Validators and repair tools for LLM JSON responses. LLMs wrap JSON in
markdown fences, add trailing commas, use Python's `True`/`None`, get cut
off mid-object by a token limit — `jsonguard` extracts, repairs, and
validates the result, and can even ask the model to fix it itself.

```bash
pip install jsonguard
```

## Quick start

```python
from jsonguard import parse_json

raw = '''Here's the JSON you asked for:
```json
{"name": "Priya", "age": 30,}
```
'''

result = parse_json(raw)
result.ok           # True
result.data         # {'name': 'Priya', 'age': 30}
result.repaired     # True (had to strip fences + drop trailing comma)
```

## Validate against a schema

```python
schema = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "age": {"type": "integer", "minimum": 0},
    },
    "required": ["name", "age"],
}

result = parse_json(raw, schema=schema)
result.ok                    # True — parsed AND matches schema
result.validation_errors     # [] when valid, else a list of readable messages
```

Or pass a pydantic model directly instead of a schema dict:

```python
from pydantic import BaseModel

class Person(BaseModel):
    name: str
    age: int

result = parse_json(raw, schema=Person)
```

## Self-healing: ask the model to fix its own mistake

```python
from jsonguard import coerce

def call_llm(prompt: str) -> str:
    return my_client.generate(prompt)  # your own LLM wrapper

result = coerce(call_llm, prompt="Return a JSON object with name and age for Priya, 30.",
                schema=schema, max_retries=2)

result.ok           # True if any attempt succeeded
result.data         # the parsed, validated dict
result.n_attempts   # how many calls to call_llm it took
```

On each failed attempt, `coerce` sends the model its own broken output plus
the specific parse or validation error, and asks it to correct just that.

## What gets repaired

- Markdown code fences (` ```json ... ``` `) and surrounding prose
- Trailing commas before `}` / `]`
- Unquoted object keys (`{name: "Sam"}`)
- Single-quoted strings (`{'name': 'Sam'}`)
- Python literals (`True` / `False` / `None` → `true` / `false` / `null`)
- Smart/curly quotes (`“ ” ‘ ’` → `" '`)
- JSON truncated mid-object by a token limit (auto-closes open brackets/strings)

Repairs are tried cheapest-first and stop as soon as something parses, so
`result.cleaned_text` shows you exactly what was needed — useful for
noticing if your prompt keeps needing the same fix (a sign to fix the
prompt instead).

## Design

- **No required dependencies.** The schema validator is a small JSON-schema
  subset (`type`, `required`, `properties`, `items`, `enum`, min/max,
  string length) implemented from scratch — no `jsonschema` package needed.
  Pydantic is optional, only imported if you pass a pydantic model as the schema.
- **Model-agnostic.** `coerce`'s `fn` is just `str -> str`; jsonguard never
  calls an LLM itself.
- **Repairs are inspectable, not silent.** Every `ParseResult` tells you
  whether repair was needed and exactly what text ended up parsing.

## API reference

| Function | Purpose |
|---|---|
| `parse_json(text, schema=None, repair=True)` | Extract + repair + validate in one call → `ParseResult` |
| `extract_json_str(text)` | Pull the JSON substring out of surrounding text/fences |
| `repair_json(text)` | Apply syntax fixes directly, returns `(fixed_text_or_none, changed)` |
| `validate(data, schema)` | Validate already-parsed data against a schema or pydantic model |
| `coerce(fn, prompt, schema=None, max_retries=2)` | Call an LLM function repeatedly until output parses & validates |

## Roadmap

- [ ] `argparse`-style CLI: `jsonguard check response.txt --schema schema.json`
- [ ] Streaming support (repair partial JSON as tokens arrive)
- [ ] JSON Schema `$ref`/`anyOf`/`oneOf` support in the built-in validator

## License

MIT
