import json

import pytest

from jsonguard import coerce, parse_json, repair_json, validate
from jsonguard.extract import extract_json_str


# ---- extract_json_str ----

def test_extract_from_markdown_fence():
    text = 'Here you go:\n```json\n{"a": 1}\n```\nHope that helps!'
    assert extract_json_str(text) == '{"a": 1}'


def test_extract_from_plain_fence_no_lang_tag():
    text = '```\n{"a": 1}\n```'
    assert extract_json_str(text) == '{"a": 1}'


def test_extract_from_surrounding_prose():
    text = 'Sure, here is the result: {"a": 1, "b": [1, 2, 3]} let me know if you need more.'
    assert extract_json_str(text) == '{"a": 1, "b": [1, 2, 3]}'


def test_extract_ignores_brackets_inside_strings():
    text = 'prefix {"a": "text with } and { inside"} suffix'
    extracted = extract_json_str(text)
    assert json.loads(extracted) == {"a": "text with } and { inside"}


def test_extract_no_brackets_returns_stripped_text():
    assert extract_json_str("  just some text  ") == "just some text"


# ---- repair_json ----

def test_repair_noop_on_valid_json():
    fixed, changed = repair_json('{"a": 1}')
    assert fixed == '{"a": 1}'
    assert changed is False


def test_repair_trailing_comma():
    fixed, changed = repair_json('{"a": 1, "b": 2,}')
    assert json.loads(fixed) == {"a": 1, "b": 2}
    assert changed is True


def test_repair_unquoted_keys():
    fixed, _ = repair_json('{name: "Sam", age: 30}')
    assert json.loads(fixed) == {"name": "Sam", "age": 30}


def test_repair_single_quoted_strings():
    fixed, _ = repair_json("{'name': 'Sam'}")
    assert json.loads(fixed) == {"name": "Sam"}


def test_repair_python_literals():
    fixed, _ = repair_json('{"active": True, "deleted": False, "meta": None}')
    assert json.loads(fixed) == {"active": True, "deleted": False, "meta": None}


def test_repair_smart_quotes():
    fixed, _ = repair_json('{\u201cname\u201d: \u201cSam\u201d}')
    assert json.loads(fixed) == {"name": "Sam"}


def test_repair_truncated_object():
    fixed, _ = repair_json('{"name": "Sam", "tags": ["a", "b"')
    data = json.loads(fixed)
    assert data["name"] == "Sam"
    assert data["tags"] == ["a", "b"]


def test_repair_truncated_mid_string():
    fixed, _ = repair_json('{"name": "Sam", "bio": "loves hiking and')
    data = json.loads(fixed)
    assert data["name"] == "Sam"


def test_repair_unrepairable_returns_none():
    fixed, _ = repair_json("not json at all, just prose")
    assert fixed is None


# ---- schema validation ----

def test_validate_simple_object_ok():
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        "required": ["name", "age"],
    }
    assert validate({"name": "Sam", "age": 30}, schema) == []


def test_validate_missing_required():
    schema = {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}
    errors = validate({}, schema)
    assert any("name" in e for e in errors)


def test_validate_wrong_type():
    schema = {"type": "object", "properties": {"age": {"type": "integer"}}}
    errors = validate({"age": "thirty"}, schema)
    assert any("age" in e and "integer" in e for e in errors)


def test_validate_bool_not_accepted_as_integer():
    schema = {"type": "object", "properties": {"age": {"type": "integer"}}}
    errors = validate({"age": True}, schema)
    assert any("boolean" in e for e in errors)


def test_validate_enum():
    schema = {"type": "object", "properties": {"status": {"enum": ["active", "inactive"]}}}
    assert validate({"status": "active"}, schema) == []
    assert validate({"status": "pending"}, schema) != []


def test_validate_nested_array_items():
    schema = {
        "type": "object",
        "properties": {"tags": {"type": "array", "items": {"type": "string"}}},
    }
    assert validate({"tags": ["a", "b"]}, schema) == []
    errors = validate({"tags": ["a", 2]}, schema)
    assert any("tags[1]" in e for e in errors)


def test_validate_min_max():
    schema = {"type": "object", "properties": {"age": {"type": "integer", "minimum": 0, "maximum": 120}}}
    assert validate({"age": 200}, schema) != []
    assert validate({"age": 30}, schema) == []


def test_validate_with_pydantic_model():
    pydantic = pytest.importorskip("pydantic")

    class Person(pydantic.BaseModel):
        name: str
        age: int

    assert validate({"name": "Sam", "age": 30}, Person) == []
    errors = validate({"name": "Sam"}, Person)
    assert len(errors) > 0


# ---- parse_json (end to end) ----

def test_parse_json_direct_valid():
    result = parse_json('{"a": 1}')
    assert result.ok
    assert result.parsed
    assert not result.repaired
    assert result.data == {"a": 1}


def test_parse_json_needs_extraction_and_repair():
    raw = 'Sure! ```json\n{name: \'Sam\', "age": 30,}\n```'
    result = parse_json(raw)
    assert result.ok
    assert result.repaired
    assert result.data == {"name": "Sam", "age": 30}


def test_parse_json_with_schema_validation_failure():
    schema = {"type": "object", "properties": {"age": {"type": "integer"}}, "required": ["age"]}
    result = parse_json('{"name": "Sam"}', schema=schema)
    assert result.parsed
    assert not result.ok
    assert any("age" in e for e in result.validation_errors)


def test_parse_json_total_failure():
    result = parse_json("this is not json in any way shape or form")
    assert not result.parsed
    assert not result.ok
    assert result.parse_error is not None


def test_parse_json_unwrap_raises_on_failure():
    result = parse_json("nope")
    with pytest.raises(ValueError):
        result.unwrap()


def test_parse_json_unwrap_returns_data_on_success():
    result = parse_json('{"a": 1}')
    assert result.unwrap() == {"a": 1}


# ---- coerce (self-healing retry) ----

def test_coerce_succeeds_first_try():
    def fn(prompt):
        return '{"name": "Sam", "age": 30}'

    schema = {"type": "object", "required": ["name", "age"]}
    result = coerce(fn, "give me a person", schema=schema)
    assert result.ok
    assert result.n_attempts == 1


def test_coerce_retries_and_succeeds():
    responses = iter(['{"name": "Sam"}', '{"name": "Sam", "age": 30}'])

    def fn(prompt):
        return next(responses)

    schema = {"type": "object", "required": ["name", "age"]}
    result = coerce(fn, "give me a person", schema=schema, max_retries=2)
    assert result.ok
    assert result.n_attempts == 2
    assert result.data == {"name": "Sam", "age": 30}


def test_coerce_exhausts_retries_and_fails():
    def fn(prompt):
        return "still not json"

    result = coerce(fn, "give me a person", max_retries=2)
    assert not result.ok
    assert result.n_attempts == 3  # initial + 2 retries


def test_coerce_repair_prompt_includes_error():
    seen_prompts = []

    def fn(prompt):
        seen_prompts.append(prompt)
        return "not json" if len(seen_prompts) == 1 else '{"a": 1}'

    coerce(fn, "original prompt", max_retries=1)
    assert "original prompt" in seen_prompts[0]
    assert "original prompt" in seen_prompts[1]
    assert "not json" in seen_prompts[1]
