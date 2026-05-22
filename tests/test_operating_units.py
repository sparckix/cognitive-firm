from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.operating_units import (  # noqa: E402
    define_operating_unit,
    get_operating_unit,
    list_operating_units,
    operating_unit_resource,
    require_operating_unit,
    set_operating_unit_status,
    validate_operating_unit_payload,
)


def _define(log: Path, **overrides):
    base = dict(
        unit_id="residual_compiler",
        unit_kind="transformation_lane",
        display_name="Residual Compiler",
        owner_role="role.residual_compiler_manager",
        allowed_work_kinds=["compile", "probe"],
        allowed_exits=["exact_gap", "tested_hold"],
        worker_roles=["role.proof_execution_worker"],
        log_path=log,
    )
    base.update(overrides)
    return define_operating_unit(**base)


def test_define_get_and_list_operating_unit(tmp_path: Path):
    log = tmp_path / "operating_units.jsonl"
    unit = _define(log)

    assert unit.status == "active"
    assert get_operating_unit("residual_compiler", log_path=log) == unit
    assert [u.unit_id for u in list_operating_units(log_path=log)] == ["residual_compiler"]
    assert require_operating_unit("residual_compiler", log_path=log) == unit


def test_redefine_is_idempotent_and_preserves_created_at(tmp_path: Path):
    log = tmp_path / "operating_units.jsonl"
    first = _define(log)
    second = _define(log, display_name="Residual Compiler v2")

    units = list_operating_units(log_path=log)
    assert len(units) == 1, "redefine must replace, not append"
    assert second.created_at_utc == first.created_at_utc
    assert second.display_name == "Residual Compiler v2"


def test_validation_rejects_incomplete_contracts(tmp_path: Path):
    log = tmp_path / "operating_units.jsonl"

    with pytest.raises(ValueError, match="allowed_exits"):
        _define(log, allowed_exits=[])

    with pytest.raises(ValueError, match="allowed_work_kinds"):
        _define(log, allowed_work_kinds=[])

    with pytest.raises(ValueError, match="unit_id"):
        _define(log, unit_id="Bad Id")


def test_governance_exit_must_be_an_allowed_exit():
    errors = validate_operating_unit_payload(
        {
            "unit_id": "gate",
            "unit_kind": "governance_gate",
            "display_name": "Governance Gate",
            "owner_role": "role.gov",
            "allowed_work_kinds": ["ratify"],
            "allowed_exits": ["ratified"],
            "governance_required_for": ["family_promotion"],
        }
    )
    assert any("governance_required_for" in error for error in errors)


def test_set_status_pauses_and_retires(tmp_path: Path):
    log = tmp_path / "operating_units.jsonl"
    _define(log)

    paused = set_operating_unit_status("residual_compiler", "paused", log_path=log)
    assert paused.status == "paused"
    retired = set_operating_unit_status("residual_compiler", "retired", log_path=log)
    assert retired.status == "retired"

    with pytest.raises(KeyError):
        set_operating_unit_status("missing_unit", "paused", log_path=log)


def test_operating_unit_resource_envelope_shape(tmp_path: Path):
    log = tmp_path / "operating_units.jsonl"
    resource = operating_unit_resource(_define(log))

    assert resource.kind == "OperatingUnit"
    assert resource.metadata.name == "residual_compiler"
    assert resource.spec["allowed_exits"] == ["exact_gap", "tested_hold"]
    assert resource.status["status"] == "active"


def test_worker_role_authorization_helper(tmp_path: Path):
    log = tmp_path / "operating_units.jsonl"
    restricted = _define(log)
    assert restricted.allows_worker_role("role.proof_execution_worker") is True
    assert restricted.allows_worker_role("role.intruder") is False

    open_unit = _define(log, unit_id="open_lane", worker_roles=[])
    assert open_unit.allows_worker_role(None) is True
