"""Tests for the uniform primitive-extension-schema registry (O3-P6).

Covers the registry module itself (discovery, lookup, validation, the
open-by-default contract, broken-schema handling) and the one wired hook:
``enqueue_work_item`` validating a custom ``kind``'s payload.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration import extension_schemas as ext  # noqa: E402
from cognitive_firm.orchestration.extension_schemas import (  # noqa: E402
    extension_schema_path,
    list_extension_schemas,
    load_extension_schema,
    register_extension_schema,
    validate_payload,
)
from cognitive_firm.orchestration.operating_units import define_operating_unit  # noqa: E402
from cognitive_firm.orchestration.work_items import enqueue_work_item  # noqa: E402


REFUND_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "refund_request work item payload",
    "type": "object",
    "required": ["amount_usd", "reason"],
    "properties": {
        "amount_usd": {"type": "number", "minimum": 0},
        "reason": {"type": "string", "minLength": 1},
    },
    "additionalProperties": False,
}


@pytest.fixture(autouse=True)
def _clear_schema_cache():
    """The schema parser is mtime-cached; clear it between tests for isolation."""
    ext._load_schema_cached.cache_clear()
    yield
    ext._load_schema_cached.cache_clear()


# ---------------------------------------------------------------------------
# registry module
# ---------------------------------------------------------------------------


def test_no_schema_registered_validates_as_open(tmp_path: Path):
    """Open by default: an unregistered (primitive, type) accepts any payload."""
    assert validate_payload("work_item", "anything", {"x": 1}, schemas_root=tmp_path) == []
    assert validate_payload("work_item", "anything", None, schemas_root=tmp_path) == []
    assert load_extension_schema("work_item", "anything", schemas_root=tmp_path) is None


def test_register_and_load_round_trip(tmp_path: Path):
    path = register_extension_schema(
        "work_item", "refund_request", REFUND_SCHEMA, schemas_root=tmp_path
    )
    assert path == extension_schema_path(
        "work_item", "refund_request", schemas_root=tmp_path
    )
    assert path.is_file()
    loaded = load_extension_schema("work_item", "refund_request", schemas_root=tmp_path)
    assert loaded == REFUND_SCHEMA


def test_register_refuses_silent_clobber(tmp_path: Path):
    register_extension_schema(
        "work_item", "refund_request", REFUND_SCHEMA, schemas_root=tmp_path
    )
    with pytest.raises(FileExistsError):
        register_extension_schema(
            "work_item", "refund_request", REFUND_SCHEMA, schemas_root=tmp_path
        )
    # overwrite=True is allowed.
    register_extension_schema(
        "work_item", "refund_request", REFUND_SCHEMA, schemas_root=tmp_path, overwrite=True
    )


def test_validate_payload_passes_and_fails(tmp_path: Path):
    register_extension_schema(
        "work_item", "refund_request", REFUND_SCHEMA, schemas_root=tmp_path
    )
    assert (
        validate_payload(
            "work_item",
            "refund_request",
            {"amount_usd": 12.5, "reason": "duplicate charge"},
            schemas_root=tmp_path,
        )
        == []
    )
    # Missing required field.
    errors = validate_payload(
        "work_item", "refund_request", {"amount_usd": 12.5}, schemas_root=tmp_path
    )
    assert errors and "reason" in errors[0]
    # Wrong type + extra field both surface.
    errors = validate_payload(
        "work_item",
        "refund_request",
        {"amount_usd": "lots", "reason": "x", "bogus": 1},
        schemas_root=tmp_path,
    )
    assert len(errors) >= 2


def test_validate_payload_uniform_across_primitives(tmp_path: Path):
    """The same mechanism serves every primitive — not only work_item."""
    unit_schema = {
        "type": "object",
        "required": ["region"],
        "properties": {"region": {"type": "string"}},
    }
    register_extension_schema(
        "operating_unit", "support_desk", unit_schema, schemas_root=tmp_path
    )
    assert (
        validate_payload(
            "operating_unit", "support_desk", {"region": "eu"}, schemas_root=tmp_path
        )
        == []
    )
    assert validate_payload(
        "operating_unit", "support_desk", {}, schemas_root=tmp_path
    )


def test_broken_schema_fails_loudly(tmp_path: Path):
    """A registry file that is not valid JSON Schema must not wave payloads through."""
    path = extension_schema_path("work_item", "broken", schemas_root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type": "not-a-real-type"}), encoding="utf-8")
    errors = validate_payload("work_item", "broken", {"a": 1}, schemas_root=tmp_path)
    assert errors and "not a valid JSON Schema" in errors[0]


def test_unparseable_schema_file_fails_loudly(tmp_path: Path):
    path = extension_schema_path("work_item", "garbage", schemas_root=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ this is not json", encoding="utf-8")
    errors = validate_payload("work_item", "garbage", {}, schemas_root=tmp_path)
    assert errors and "could not be read" in errors[0]


def test_invalid_type_key_rejected(tmp_path: Path):
    errors = validate_payload(
        "work_item", "bad/key", {}, schemas_root=tmp_path
    )
    assert errors and "lookup failed" in errors[0]


def test_list_extension_schemas_discovers_registry(tmp_path: Path):
    register_extension_schema(
        "work_item", "refund_request", REFUND_SCHEMA, schemas_root=tmp_path
    )
    register_extension_schema(
        "work_item", "escalation", {"type": "object"}, schemas_root=tmp_path
    )
    register_extension_schema(
        "operating_unit", "support_desk", {"type": "object"}, schemas_root=tmp_path
    )
    assert list_extension_schemas(schemas_root=tmp_path) == {
        "operating_unit": ["support_desk"],
        "work_item": ["escalation", "refund_request"],
    }
    assert list_extension_schemas("work_item", schemas_root=tmp_path) == {
        "work_item": ["escalation", "refund_request"]
    }
    assert list_extension_schemas(schemas_root=tmp_path / "empty") == {}


def test_schema_edit_busts_cache(tmp_path: Path):
    register_extension_schema(
        "work_item", "refund_request", REFUND_SCHEMA, schemas_root=tmp_path
    )
    assert load_extension_schema(
        "work_item", "refund_request", schemas_root=tmp_path
    ) == REFUND_SCHEMA
    relaxed = {"type": "object"}
    register_extension_schema(
        "work_item", "refund_request", relaxed, schemas_root=tmp_path, overwrite=True
    )
    assert (
        load_extension_schema("work_item", "refund_request", schemas_root=tmp_path)
        == relaxed
    )


# ---------------------------------------------------------------------------
# the wired hook: enqueue_work_item
# ---------------------------------------------------------------------------


@pytest.fixture()
def unit_log(tmp_path: Path) -> Path:
    units = tmp_path / "operating_units.jsonl"
    define_operating_unit(
        unit_id="refund_desk",
        unit_kind="support_lane",
        display_name="Refund Desk",
        owner_role="role.refund_manager",
        allowed_work_kinds=["refund_request", "note"],
        allowed_exits=["refunded", "denied"],
        log_path=units,
    )
    return units


def _enqueue(tmp_path: Path, unit_log: Path, *, kind: str, payload: dict):
    return enqueue_work_item(
        unit_id="refund_desk",
        kind=kind,
        payload=payload,
        log_path=tmp_path / "work_items.jsonl",
        operating_units_log=unit_log,
        kernel_events_log=tmp_path / "kernel_events.jsonl",
        extension_schemas_root=tmp_path / "schemas",
    )


def test_enqueue_unregistered_kind_stays_open(tmp_path: Path, unit_log: Path):
    """A custom kind with no schema is enqueued with any payload — unchanged behavior."""
    item = _enqueue(tmp_path, unit_log, kind="note", payload={"whatever": [1, 2, 3]})
    assert item.kind == "note"
    assert item.payload == {"whatever": [1, 2, 3]}


def test_enqueue_validates_payload_when_schema_registered(tmp_path: Path, unit_log: Path):
    register_extension_schema(
        "work_item", "refund_request", REFUND_SCHEMA, schemas_root=tmp_path / "schemas"
    )
    # Valid payload passes.
    item = _enqueue(
        tmp_path,
        unit_log,
        kind="refund_request",
        payload={"amount_usd": 20, "reason": "wrong item"},
    )
    assert item.kind == "refund_request"
    # Invalid payload is rejected at enqueue.
    with pytest.raises(ValueError, match="fails the extension schema"):
        _enqueue(
            tmp_path,
            unit_log,
            kind="refund_request",
            payload={"amount_usd": -5},
        )


def test_enqueue_rejection_writes_nothing(tmp_path: Path, unit_log: Path):
    """A schema-failing enqueue must not persist a work item."""
    register_extension_schema(
        "work_item", "refund_request", REFUND_SCHEMA, schemas_root=tmp_path / "schemas"
    )
    work_log = tmp_path / "work_items.jsonl"
    with pytest.raises(ValueError):
        _enqueue(tmp_path, unit_log, kind="refund_request", payload={})
    assert not work_log.exists() or work_log.read_text() == ""
