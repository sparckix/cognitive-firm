from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.operating_units import (  # noqa: E402
    define_operating_unit,
    get_operating_unit,
    list_operating_units,
    main as operating_units_main,
    operating_unit_resource,
    require_operating_unit,
    set_operating_unit_status,
    validate_operating_unit_payload,
)
from cognitive_firm.orchestration.resource_envelope import validate_resource  # noqa: E402


def _define(log: Path, **overrides):
    base = dict(
        unit_id="research_intake",
        unit_kind="analysis_lane",
        display_name="Research Intake",
        owner_role="role.research_lead",
        allowed_work_kinds=["triage", "source_check"],
        allowed_exits=["summary_ready", "needs_followup"],
        worker_roles=["role.analysis_worker"],
        log_path=log,
    )
    base.update(overrides)
    return define_operating_unit(**base)


def test_define_get_and_list_operating_unit(tmp_path: Path):
    log = tmp_path / "operating_units.jsonl"
    unit = _define(log)

    assert unit.status == "active"
    assert get_operating_unit("research_intake", log_path=log) == unit
    assert [u.unit_id for u in list_operating_units(log_path=log)] == ["research_intake"]
    assert require_operating_unit("research_intake", log_path=log) == unit


def test_redefine_is_idempotent_and_preserves_created_at(tmp_path: Path):
    log = tmp_path / "operating_units.jsonl"
    first = _define(log)
    second = _define(log, display_name="Research Intake v2")

    units = list_operating_units(log_path=log)
    assert len(units) == 1, "redefine must replace, not append"
    assert second.created_at_utc == first.created_at_utc
    assert second.display_name == "Research Intake v2"


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

    paused = set_operating_unit_status("research_intake", "paused", log_path=log)
    assert paused.status == "paused"
    retired = set_operating_unit_status("research_intake", "retired", log_path=log)
    assert retired.status == "retired"

    with pytest.raises(KeyError):
        set_operating_unit_status("missing_unit", "paused", log_path=log)


def test_operating_unit_resource_envelope_shape(tmp_path: Path):
    log = tmp_path / "operating_units.jsonl"
    resource = operating_unit_resource(
        _define(
            log,
            worker_roles=["role.analysis_worker", "role.quality_reviewer"],
            worker_role_classes={
                "role.analysis_worker": "agent",
                "role.quality_reviewer": "governance",
            },
            worker_role_archetypes={
                "role.analysis_worker": "fungible_agent_worker",
                "role.quality_reviewer": "independent_reviewer",
            },
        )
    )

    assert resource.kind == "OperatingUnit"
    assert resource.metadata.name == "research_intake"
    assert resource.spec["allowed_exits"] == ["summary_ready", "needs_followup"]
    assert resource.spec["worker_role_classes"] == {
        "role.analysis_worker": "agent",
        "role.quality_reviewer": "governance",
    }
    assert resource.spec["worker_role_archetypes"] == {
        "role.analysis_worker": "fungible_agent_worker",
        "role.quality_reviewer": "independent_reviewer",
    }
    assert resource.status["status"] == "active"
    assert validate_resource(resource.as_dict()) == []


def test_operating_unit_cli_can_render_resource_envelopes(tmp_path: Path, capsys):
    log = tmp_path / "operating_units.jsonl"
    _define(log, tenant_id="tenant-a", project_id="project-a")

    rc = operating_units_main(["list", "--log-path", str(log), "--resource"])
    payloads = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip()
    ]

    assert rc == 0
    assert len(payloads) == 1
    assert payloads[0]["kind"] == "OperatingUnit"
    assert payloads[0]["metadata"]["tenant_id"] == "tenant-a"
    assert payloads[0]["metadata"]["project_id"] == "project-a"
    assert validate_resource(payloads[0]) == []


def test_worker_role_authorization_helper(tmp_path: Path):
    log = tmp_path / "operating_units.jsonl"
    restricted = _define(log)
    assert restricted.allows_worker_role("role.analysis_worker") is True
    assert restricted.allows_worker_role("role.intruder") is False

    open_unit = _define(log, unit_id="open_lane", worker_roles=[])
    assert open_unit.allows_worker_role(None) is True


def test_worker_role_classes_are_validated(tmp_path: Path):
    log = tmp_path / "operating_units.jsonl"

    with pytest.raises(ValueError, match="worker_role_classes"):
        _define(
            log,
            worker_role_classes={"role.analysis_worker": "wizard"},
        )

    with pytest.raises(ValueError, match="worker_role_classes"):
        _define(
            log,
            worker_role_classes={"role.other": "agent"},
        )


def test_worker_role_archetypes_are_validated(tmp_path: Path):
    log = tmp_path / "operating_units.jsonl"

    with pytest.raises(ValueError, match="unknown worker archetype"):
        _define(
            log,
            worker_role_archetypes={"role.analysis_worker": "missing_archetype"},
        )

    with pytest.raises(ValueError, match="worker_role_archetypes"):
        _define(
            log,
            worker_role_archetypes={"role.other": "fungible_agent_worker"},
        )

    with pytest.raises(ValueError, match="does not match"):
        _define(
            log,
            worker_role_classes={"role.analysis_worker": "llm"},
            worker_role_archetypes={"role.analysis_worker": "fungible_agent_worker"},
        )
