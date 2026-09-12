from pathlib import Path

import pytest

from core.swagger import (
    CIRCULAR_KEY,
    Endpoint,
    SpecError,
    load_spec,
    parse_file,
    parse_spec,
    resolve_refs,
)

SPEC = Path(__file__).parent / "fixtures" / "mini_spec.yaml"


@pytest.fixture(scope="module")
def endpoints() -> list[Endpoint]:
    return parse_file(SPEC)


def test_all_operations_found(endpoints):
    assert [e.key for e in endpoints] == [
        "GET /pets",
        "POST /pets",
        "GET /pets/{petId}",
    ]


def test_path_level_params_merge_into_operation(endpoints):
    get_pets = next(e for e in endpoints if e.key == "GET /pets")
    assert {p["name"] for p in get_pets.query_params} == {"tenant", "limit"}
    assert get_pets.path_params == []


def test_path_params_captured(endpoints):
    get_pet = next(e for e in endpoints if e.key == "GET /pets/{petId}")
    assert [p["name"] for p in get_pet.path_params] == ["petId"]


def test_documented_codes_drop_non_numeric(endpoints):
    get_pets = next(e for e in endpoints if e.key == "GET /pets")
    assert get_pets.documented_codes == [200, 400]  # 'default' dropped


def test_request_schema_is_resolved(endpoints):
    post = next(e for e in endpoints if e.key == "POST /pets")
    assert post.request_schema["required"] == ["name"]
    # $ref to Category was inlined, not left as a pointer.
    assert "$ref" not in post.request_schema["properties"]["category"]


def test_circular_ref_is_marked_not_followed(endpoints):
    post = next(e for e in endpoints if e.key == "POST /pets")
    back_ref = post.request_schema["properties"]["category"]["properties"]["pets"]["items"]
    assert back_ref == {CIRCULAR_KEY: "#/components/schemas/Pet"}


def test_sibling_keys_beside_ref_win():
    root = {"components": {"schemas": {"S": {"type": "string", "maxLength": 5}}}}
    node = {"$ref": "#/components/schemas/S", "maxLength": 10}
    assert resolve_refs(node, root) == {"type": "string", "maxLength": 10}


def test_missing_file_raises():
    with pytest.raises(SpecError, match="not found"):
        load_spec("nope.yaml")


def test_swagger_2_rejected(tmp_path):
    f = tmp_path / "s2.yaml"
    f.write_text("swagger: '2.0'\npaths: {}\n", encoding="utf-8")
    with pytest.raises(SpecError, match="Swagger 2.0"):
        load_spec(f)


def test_bad_ref_raises():
    with pytest.raises(SpecError, match="not found"):
        resolve_refs({"$ref": "#/components/schemas/Ghost"}, {"components": {"schemas": {}}})


def test_external_ref_rejected():
    with pytest.raises(SpecError, match="External"):
        resolve_refs({"$ref": "other.yaml#/Pet"}, {})


def test_operation_without_responses_is_still_an_endpoint():
    spec = {"openapi": "3.0.0", "paths": {"/x": {"get": {}}}}
    (ep,) = parse_spec(spec)
    assert ep.key == "GET /x"
    assert ep.documented_codes == []
    assert ep.request_schema is None
