"""tool_schema: self-contained JSON schemas for tool input (blueprint Day 6, step 3)."""

import json

import pytest
from pydantic import BaseModel, Field

from src.schema_utils import tool_schema
from src.schemas import Category, Classification, Resolution, RiskFlag, Severity


def test_classification_schema_has_no_refs_defs_or_titles():
    text = json.dumps(tool_schema(Classification))
    assert "$ref" not in text and "$defs" not in text and '"title"' not in text


def test_enum_values_are_inlined():
    props = tool_schema(Classification)["properties"]
    assert set(props["category"]["enum"]) == {c.value for c in Category}
    assert set(props["severity"]["enum"]) == {s.value for s in Severity}
    assert set(props["risk_flags"]["items"]["enum"]) == {f.value for f in RiskFlag}


def test_constraints_and_descriptions_survive():
    props = tool_schema(Classification)["properties"]
    assert props["confidence"]["minimum"] == 0.0 and props["confidence"]["maximum"] == 1.0
    assert props["summary"]["maxLength"] == 300
    assert props["confidence"]["description"].startswith("Your confidence")
    assert props["category"]["type"] == "string"


def test_top_level_shape():
    schema = tool_schema(Classification)
    assert schema["type"] == "object"
    assert set(schema["required"]) == {
        "category",
        "severity",
        "confidence",
        "affected_system",
        "summary",
    }


def test_optional_fields_are_not_required():
    assert "risk_flags" not in tool_schema(Classification)["required"]


def test_works_for_the_resolver_model_too():
    schema = tool_schema(Resolution)
    assert "$ref" not in json.dumps(schema)
    assert "proposed_outcome" in schema["properties"]


def test_a_field_called_title_is_not_removed():
    class WithTitle(BaseModel):
        title: str = Field(description="a title")

    schema = tool_schema(WithTitle)
    assert "title" in schema["properties"] and "title" in schema["required"]


def test_ref_with_sibling_description_merges_both():
    class Inner(BaseModel):
        x: int

    class Outer(BaseModel):
        inner: Inner = Field(description="the inner thing")

    inner = tool_schema(Outer)["properties"]["inner"]
    assert inner["description"] == "the inner thing"
    assert inner["properties"]["x"]["type"] == "integer"


def test_recursive_models_are_rejected():
    class Node(BaseModel):
        child: "Node | None" = None

    Node.model_rebuild()
    with pytest.raises(ValueError, match="recursive"):
        tool_schema(Node)


def test_the_validator_accepts_what_the_schema_describes():
    good = {
        "category": "vpn_network",
        "severity": "P3",
        "confidence": 0.9,
        "affected_system": "VPN",
        "summary": "VPN fails.",
    }
    assert Classification.model_validate(good).category is Category.VPN_NETWORK
