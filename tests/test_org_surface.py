from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.evidence_gaps import create_evidence_gap  # noqa: E402
from cognitive_firm.orchestration.accountability_cases import create_accountability_case  # noqa: E402
from cognitive_firm.orchestration.human_work import (  # noqa: E402
    create_agent_requested_human_work_session,
    create_human_work_session,
    update_human_work_state,
)
from cognitive_firm.orchestration.learning_events import create_learning_event  # noqa: E402
from cognitive_firm.orchestration.org_surface import (  # noqa: E402
    build_org_surface,
    format_surface_brief,
)
from cognitive_firm.orchestration.run_checkpoints import (  # noqa: E402
    set_run_state,
    start_run,
)


def test_org_surface_collects_blockers_and_human_work(tmp_path: Path):
    gaps_log = tmp_path / "evidence_gaps.jsonl"
    human_log = tmp_path / "human_work.jsonl"

    create_evidence_gap(
        gap_type="missing_source",
        target="claim A",
        description="Need a primary source before continuing.",
        severity="blocking",
        producer="reviewer",
        log_path=gaps_log,
    )
    create_evidence_gap(
        gap_type="external_comparator",
        target="claim B",
        description="Helpful external comparator.",
        severity="useful",
        producer="reviewer",
        log_path=gaps_log,
    )
    create_human_work_session(
        requested_by="role.manager",
        human_actor="principal",
        objective="verify restricted source",
        work_mode="source_check",
        bottleneck_class="access",
        receipt_required=True,
        receipt_type="note",
        log_path=human_log,
    )

    surface = build_org_surface(
        project_root=tmp_path,
        evidence_gaps_log=gaps_log,
        human_work_log=human_log,
        damage_limit=0,
    )

    assert surface.counts["blocking_evidence_gaps"] == 1
    assert surface.counts["open_evidence_gaps"] == 2
    assert surface.counts["active_human_work_sessions"] == 1
    assert surface.counts["waiting_human_work_sessions"] == 1

    brief = format_surface_brief(surface)
    assert "claim A" in brief
    assert "verify restricted source" in brief
    assert "receipt-required" in brief


def test_org_surface_surfaces_a2h_followup_receipts_and_pressure(tmp_path: Path):
    human_log = tmp_path / "human_work.jsonl"
    sessions = [
        create_agent_requested_human_work_session(
            requested_by_role="role.researcher",
            human_actor="principal",
            objective=f"Check private source {index}.",
            work_mode="source_check",
            bottleneck_class="access",
            human_deliverable="source support claim",
            receipt_required=True,
            receipt_type="note",
            log_path=human_log,
        )
        for index in range(3)
    ]

    update_human_work_state(sessions[0].session_id, "claimed", log_path=human_log)
    update_human_work_state(sessions[0].session_id, "in_progress", log_path=human_log)
    update_human_work_state(
        sessions[0].session_id,
        "completed",
        completion_summary="Source supports the claim.",
        receipt="source note",
        log_path=human_log,
    )

    surface = build_org_surface(
        project_root=tmp_path,
        evidence_gaps_log=tmp_path / "missing_gaps.jsonl",
        human_work_log=human_log,
        damage_limit=0,
    )

    assert surface.counts["a2h_waiting_on_human_sessions"] == 2
    assert surface.counts["a2h_followup_sessions"] == 1
    assert surface.counts["a2h_missing_receipt_sessions"] == 2
    assert surface.counts["a2h_pressure_groups"] == 1
    brief = format_surface_brief(surface)
    assert "A2H Follow-Up" in brief
    assert "A2H Waiting On Human" in brief
    assert "A2H Missing Receipts" in brief
    assert "A2H Pressure" in brief
    assert "source connector" in brief


def test_org_surface_surfaces_open_accountability_cases(tmp_path: Path):
    cases_log = tmp_path / "accountability_cases.jsonl"
    create_accountability_case(
        trigger_ref="action:restricted-source-use",
        accountable_role="role.manager",
        responsible_actor="agent.researcher",
        decision_right_basis="role mandate",
        authority_envelope_ref="org/roles/manager.yaml",
        risk_tier="high",
        recourse_path="reopen",
        rationale="Restricted source decision needs explicit closure.",
        log_path=cases_log,
    )

    surface = build_org_surface(
        project_root=tmp_path,
        evidence_gaps_log=tmp_path / "missing_gaps.jsonl",
        human_work_log=tmp_path / "missing_human.jsonl",
        accountability_cases_log=cases_log,
        damage_limit=0,
    )

    assert surface.counts["open_accountability_cases"] == 1
    assert surface.counts["high_risk_accountability_cases"] == 1
    assert "Open Accountability Cases" in format_surface_brief(surface)


def test_org_surface_reports_invalid_project_charters(tmp_path: Path):
    charter_dir = tmp_path / "projects" / "example"
    charter_dir.mkdir(parents=True)
    charter = charter_dir / "project_charter.md"
    charter.write_text("## Core Question\n\nWhat should happen?\n", encoding="utf-8")

    surface = build_org_surface(
        project_root=tmp_path,
        evidence_gaps_log=tmp_path / "missing_gaps.jsonl",
        human_work_log=tmp_path / "missing_human.jsonl",
        damage_limit=0,
    )

    assert surface.counts["invalid_project_charters"] == 1
    assert surface.counts["strategy_review_blocking"] == 1
    assert "missing required section: out of scope" in surface.invalid_project_charters[0].errors


def test_org_surface_includes_strategy_review_findings(tmp_path: Path):
    forecast_dir = tmp_path / "forecast"
    forecast_dir.mkdir()
    forecast_summary = forecast_dir / "global_health.json"
    forecast_summary.write_text(
        json.dumps({"contract_count": 2, "decision_use": {"rows": 0}}),
        encoding="utf-8",
    )

    surface = build_org_surface(
        project_root=tmp_path,
        evidence_gaps_log=tmp_path / "missing_gaps.jsonl",
        human_work_log=tmp_path / "missing_human.jsonl",
        forecast_market_summary=forecast_summary,
        action_impact_summary=tmp_path / "missing_action_impact.json",
        damage_limit=0,
    )

    assert surface.counts["strategy_review_findings"] == 1
    assert surface.counts["strategy_review_blocking"] == 1
    assert surface.counts["intelligence_source_warning_or_blocking"] == 1
    assert "forecast_decision_use_missing" in format_surface_brief(surface)
    assert "Intelligence Source Improvements" in format_surface_brief(surface)


def test_org_surface_includes_run_checkpoint_projection(tmp_path: Path):
    transitions = tmp_path / "transitions.jsonl"
    active = start_run(
        owner_role="role.manager",
        objective="review external system state",
        log_path=transitions,
    )
    failed = start_run(
        owner_role="role.research_director",
        objective="compile evidence packet",
        log_path=transitions,
    )
    set_run_state(
        failed.run_id,
        actor="role.research_director",
        state="failed",
        failure_reason="source inaccessible",
        log_path=transitions,
    )

    surface = build_org_surface(
        project_root=tmp_path,
        evidence_gaps_log=tmp_path / "missing_gaps.jsonl",
        human_work_log=tmp_path / "missing_human.jsonl",
        transitions_log=transitions,
        damage_limit=0,
    )

    assert surface.counts["active_runs"] == 1
    assert surface.counts["failed_runs"] == 1
    brief = format_surface_brief(surface)
    assert active.run_id in brief
    assert "source inaccessible" in brief


def test_org_surface_includes_approved_learning_events(tmp_path: Path):
    learning_log = tmp_path / "learning_events.jsonl"
    event = create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Require independent evidence before retrying a branch.",
        future_application_cue="same failure mode repeats across reviewed runs",
        approved_by="role.principal",
        approval_ref="review/1",
        source_carrier_refs=["forecast/c1"],
        log_path=learning_log,
    )

    surface = build_org_surface(
        project_root=tmp_path,
        evidence_gaps_log=tmp_path / "missing_gaps.jsonl",
        human_work_log=tmp_path / "missing_human.jsonl",
        learning_events_log=learning_log,
        damage_limit=0,
    )

    assert surface.counts["active_learning_events"] == 1
    assert surface.active_learning_events[0].learning_event_id == event.learning_event_id
    brief = format_surface_brief(surface)
    assert "Approved Learning Events" in brief
    assert "same failure mode repeats" in brief
