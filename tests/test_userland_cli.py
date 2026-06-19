"""Tests for ``cognitive-firm-userland`` — the userland's terminal carrier."""

from __future__ import annotations

import pytest

import functools
import json
from types import SimpleNamespace

from cognitive_firm.kernel_service import KernelServiceConfig, dispatch_kernel_request
from cognitive_firm.orchestration.human_work import (
    create_agent_requested_human_work_session,
    create_human_work_session,
    list_human_work_sessions,
)
from cognitive_firm.orchestration.learning_events import (
    create_learning_event,
    list_learning_event_encounters,
    record_learning_event_encounter,
)
from cognitive_firm.orchestration.leases import list_leases
from cognitive_firm.orchestration.outcome_links import create_outcome_link
from cognitive_firm.orchestration.routine_reviews import schedule_routine_review
from cognitive_firm.orchestration.run_checkpoints import append_checkpoint, start_run
from cognitive_firm.userland import cli
from cognitive_firm.userland.cli import main


def test_vocabulary_prints_the_shared_glossary(capsys):
    rc = main(["vocabulary"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "userland vocabulary" in out
    assert "term(s):" in out
    # The L4 glossary is non-empty and renders label + definition lines.
    assert len(out.strip().splitlines()) > 1


def test_commands_prints_read_only_command_matches(capsys):
    rc = main(["commands", "adoption readiness packet"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "command surface - " in out
    assert "make adoption-readiness-packet" in out
    assert "kind: make_target" in out
    assert "executes: false" in out
    assert "authority effects:" in out
    assert "decision_class=adoption_readiness" in out
    assert "resolution=single_authority_fallback" in out
    assert "{" not in out


def test_commands_prints_adoption_onramp_packet(capsys):
    rc = main(["commands", "adoption onramp packet"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "make adoption-onramp-packet" in out
    assert "decision_class=adoption_readiness" in out
    assert "executes: false" in out


def test_commands_prints_first_review_operator_path(capsys):
    rc = main(["commands", "first serious review"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "make smoke-public" in out
    assert "make adoption-onramp-packet" in out
    assert "make adoption-readiness-packet" in out
    assert "operator path: first_review step 1/3 (required)" in out
    assert "operator path: first_review step 2/3 (required)" in out
    assert "operator path: first_review step 3/3 (required)" in out
    assert "executes: false" in out
    assert "{" not in out


def test_operator_path_prints_first_review_path(capsys):
    rc = main(["operator-path", "first_review"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "operator path - first_review (3 step(s)), read-only" in out
    assert (
        "purpose: Verify the public gate, collect deterministic adoption "
        "evidence, and render a reviewer handoff."
    ) in out
    assert "projection-only: true" in out
    assert "executes: false" in out
    assert (
        "boundary: no command execution; no scheduling; no state mutation; "
        "no adoption approval"
    ) in out
    assert (
        "not a: command runner, scheduler, adoption approval, workflow engine"
    ) in out
    assert "1/3 make smoke-public (required)" in out
    assert "2/3 make adoption-onramp-packet (required)" in out
    assert "3/3 make adoption-readiness-packet (required)" in out
    assert "{" not in out


def test_commands_passes_source_role_and_prints_escalation(
    monkeypatch,
    capsys,
):
    captured_routes: list[str] = []

    def fake_dispatch(method: str, route: str):
        captured_routes.append(route)
        return SimpleNamespace(
            status=200,
            payload={
                "query": "field pilot action impact demo",
                "matches": [
                    {
                        "command": "make field-pilot-action-impact-demo",
                        "command_kind": "make_target",
                        "executes": False,
                        "authority_effects": [
                            {
                                "effect_id": "policy_promotion_review",
                                "decision_class": "policy_change",
                                "resource_class": "policy_promotion_packet",
                                "authority_resolution": {"status": "resolved"},
                                "source_role_escalation": {
                                    "status": "ok",
                                    "escalation_path": [
                                        "worker",
                                        "policy_authority",
                                    ],
                                },
                            }
                        ],
                        "authority_effect_validation": {
                            "status": "ok",
                            "issues": [],
                        },
                    }
                ],
                "hint": "Known repo command surface",
            },
        )

    monkeypatch.setattr(cli, "dispatch_kernel_request", fake_dispatch)

    rc = main(
        [
            "commands",
            "field pilot action impact demo",
            "--role-id",
            "worker",
        ]
    )
    out = capsys.readouterr().out

    assert rc == 0
    assert captured_routes == [
        "/kernel/command-surface?"
        "query=field+pilot+action+impact+demo&role_id=worker"
    ]
    assert "source role escalation: ok; role.worker -> role.policy_authority" in out
    assert "{" not in out


def test_needs_me_for_an_actor_with_no_signals(capsys):
    rc = main(["needs-me", "human_nobody_home"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Nothing needs you right now." in out


def test_inbox_lists_a_member_humans_open_work(tmp_path, capsys):
    log = tmp_path / "human_work.jsonl"
    create_human_work_session(
        requested_by="research_office",
        human_actor="alice",
        objective="review the draft",
        work_mode="edit",
        bottleneck_class="taste",
        human_deliverable="annotated draft",
        deadline_utc="2026-06-01T00:00:00+00:00",
        log_path=log,
    )
    create_human_work_session(
        requested_by="research_office",
        human_actor="bob",
        objective="bob's unrelated task",
        work_mode="edit",
        bottleneck_class="taste",
        log_path=log,
    )

    rc = main(["inbox", "alice", "--human-work-log", str(log)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "alice — 1 open task(s):" in out
    assert "review the draft" in out
    assert "annotated draft" in out
    assert "2026-06-01T00:00:00+00:00" in out
    assert "bob's unrelated task" not in out


def test_inbox_for_an_actor_with_no_work(tmp_path, capsys):
    log = tmp_path / "human_work.jsonl"
    rc = main(["inbox", "ghost", "--human-work-log", str(log)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "ghost has no open work." in out


def test_receipt_records_human_review_of_agent_output(
    tmp_path, monkeypatch, capsys
):
    config = KernelServiceConfig(human_work_log=tmp_path / "human_work.jsonl")
    session = create_human_work_session(
        requested_by="role.reviewer",
        human_actor="principal",
        objective="Review the agent output before release.",
        work_mode="judgment",
        bottleneck_class="cognition",
        receipt_required=True,
        receipt_type="artifact_ref",
        log_path=config.human_work_log,
    )
    _bind(monkeypatch, config)

    rc = main([
        "receipt",
        session.session_id,
        "--actor",
        "principal",
        "--summary",
        "Accepted after checking the cited diff.",
        "--receipt-type",
        "artifact_ref",
        "--artifact-ref",
        "artifact://human-review/release-note-accepted",
        "--agent-output-ref",
        "artifact://agent-output/release-note",
        "--action-attestation-ref",
        "action_attestation:aat_release_note",
        "--review-decision",
        "accepted",
        "--confidence",
        "high",
        "--observability",
        "digital_artifact",
    ])

    out = capsys.readouterr().out
    assert rc == 0
    assert "human-work receipt hwr_" in out
    assert f"session:     {session.session_id}" in out
    assert "subjects:    artifact://agent-output/release-note, action_attestation:aat_release_note" in out
    assert "artifacts:   artifact://human-review/release-note-accepted" in out
    assert "{" not in out

    updated = list_human_work_sessions(log_path=config.human_work_log)[0]
    assert updated.work_receipts[0]["metadata"]["review_decision"] == "accepted"
    assert updated.work_receipts[0]["subject_refs"] == [
        "artifact://agent-output/release-note",
        "action_attestation:aat_release_note",
    ]


def test_status_prints_a_plain_language_org_health_summary(capsys):
    rc = main(["status"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "org status" in out
    # The summary is operator-facing prose, not a JSON dump.
    assert "{" not in out
    assert "running:" in out
    assert "blocked:" in out
    assert "governance:" in out


def _gate_config(tmp_path) -> KernelServiceConfig:
    """A kernel config with isolated gate directories for resolve tests."""
    return KernelServiceConfig(
        gates_dir=tmp_path / "gates" / "pending",
        gates_resolved_dir=tmp_path / "gates" / "resolved",
        transition_log=tmp_path / "transitions.jsonl",
    )


def test_resolve_acts_on_a_pending_gate(tmp_path, monkeypatch, capsys):
    config = _gate_config(tmp_path)
    config.gates_dir.mkdir(parents=True)
    (config.gates_dir / "gate_42.json").write_text(
        '{"gate_id":"gate_42","question":"approve the plan?"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        cli, "dispatch_kernel_request",
        functools.partial(dispatch_kernel_request, config=config),
    )

    rc = main(["resolve", "gate_42", "--option", "approve", "--reason", "looks good"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "gate gate_42 resolved with option 'approve'." in out
    assert (config.gates_resolved_dir / "gate_42.json").exists()
    assert (config.gates_dir / "gate_42.json.handled").exists()


def test_resolve_a_missing_gate_errors_to_stderr(tmp_path, monkeypatch, capsys):
    config = _gate_config(tmp_path)
    config.gates_dir.mkdir(parents=True)
    monkeypatch.setattr(
        cli, "dispatch_kernel_request",
        functools.partial(dispatch_kernel_request, config=config),
    )

    rc = main(["resolve", "gate_nope", "--option", "approve"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "ERROR:" in captured.err


def test_resolve_requires_an_option():
    with pytest.raises(SystemExit):
        main(["resolve", "gate_42"])


def test_unknown_verb_exits_nonzero(capsys):
    with pytest.raises(SystemExit):
        main(["not-a-verb"])


# --- governed-install human loop: proposals / approve / decline ----------

from cognitive_firm.orchestration.governance_changes import (  # noqa: E402
    InvariantCheck,
    propose_governance_change,
)
from cognitive_firm.orchestration.kernel_events import (  # noqa: E402
    list_kernel_events,
)


def _passing_checks() -> list[InvariantCheck]:
    """Invariant checks that carry a proposal to ``review_ready``."""
    return [
        InvariantCheck(
            invariant=inv,
            status="pass",
            rationale="ok",
            evidence_refs=[f"test://{inv}"],
        )
        for inv in (
            "principal_independence",
            "deterministic_enforcement_floor",
            "fail_closed_behavior",
            "write_scope_preserved",
            "tenant_boundary_preserved",
        )
    ]


def _review_ready_evidence() -> dict:
    return {
        "source_refs": ["authority_diff:test"],
        "expected_behavior_change": "analyst may write to drafts/",
        "risk_summary": "bounded test proposal; no production authority change",
        "rollback_plan": "restore the previous role file",
    }


def _gov_config(tmp_path) -> KernelServiceConfig:
    """A kernel config with an isolated org dir and transition log."""
    return KernelServiceConfig(
        org_dir=tmp_path / "org",
        transition_log=tmp_path / "transitions.jsonl",
        gates_dir=tmp_path / "gates" / "pending",
        gates_resolved_dir=tmp_path / "gates" / "resolved",
    )


def _governance_log(config: KernelServiceConfig):
    return config.org_dir / "governance_changes" / "governance_changes.jsonl"


def _bind(monkeypatch, config: KernelServiceConfig) -> None:
    monkeypatch.setattr(
        cli, "dispatch_kernel_request",
        functools.partial(dispatch_kernel_request, config=config),
    )


def test_proposals_lists_governance_changes_awaiting_review(
    tmp_path, monkeypatch, capsys
):
    config = _gov_config(tmp_path)
    propose_governance_change(
        change_kind="role_change",
        title="Widen analyst write scope",
        proposed_by="operator",
        target_ref="roles/analyst.yaml",
        rationale="overlay install",
        **_review_ready_evidence(),
        invariant_checks=_passing_checks(),
        log_path=_governance_log(config),
    )
    _bind(monkeypatch, config)

    rc = main(["proposals"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "1 governance change(s) awaiting review:" in out
    assert "Widen analyst write scope" in out
    assert "analyst may write to drafts/" in out
    assert "review:   awaiting_review" in out
    assert "evidence: pass" in out


def test_proposal_prints_evidence_and_invariant_detail(
    tmp_path, monkeypatch, capsys
):
    config = _gov_config(tmp_path)
    proposal = propose_governance_change(
        change_kind="role_change",
        title="Widen analyst write scope",
        proposed_by="operator",
        target_ref="roles/analyst.yaml",
        rationale="overlay install",
        **_review_ready_evidence(),
        invariant_checks=_passing_checks(),
        log_path=_governance_log(config),
    )
    _bind(monkeypatch, config)

    rc = main(["proposal", proposal.proposal_id])
    out = capsys.readouterr().out
    assert rc == 0
    assert f"governance proposal {proposal.proposal_id}" in out
    assert "status:   review_ready" in out
    assert "effect:   analyst may write to drafts/" in out
    assert "evidence sufficiency: pass" in out
    assert "[pass] write_scope_preserved" in out
    assert "refs: test://write_scope_preserved" in out
    assert "{" not in out


def test_proposal_packet_prints_review_handoff(
    tmp_path, monkeypatch, capsys
):
    config = _gov_config(tmp_path)
    proposal = propose_governance_change(
        change_kind="role_change",
        title="Widen analyst write scope",
        proposed_by="operator",
        target_ref="roles/analyst.yaml",
        rationale="overlay install",
        **_review_ready_evidence(),
        invariant_checks=_passing_checks(),
        log_path=_governance_log(config),
    )
    _bind(monkeypatch, config)

    rc = main(["proposal-packet", proposal.proposal_id, "--event-limit", "3"])
    out = capsys.readouterr().out

    assert rc == 0
    assert f"proposal review packet {proposal.proposal_id}" in out
    assert "read-only projection" in out
    assert "state:    awaiting_review (review_ready)" in out
    assert "effect:   analyst may write to drafts/" in out
    assert "follow:   proposal_only" in out
    assert "provenance:" in out
    assert "review questions:" in out
    assert "test://write_scope_preserved" in out
    assert "POST /kernel/governance-changes/" in out
    assert "{" not in out

    rc = main(["proposal-packet", proposal.proposal_id, "--markdown"])
    markdown = capsys.readouterr().out
    assert rc == 0
    assert "# Governance Change Review Packet" in markdown
    assert "## Follow-Through" in markdown
    assert "Widen analyst write scope" in markdown
    assert "test://write_scope_preserved" in markdown


def test_proposal_template_prints_service_generated_post_body(capsys):
    rc = main([
        "proposal-template",
        "--change-kind",
        "route_policy_change",
        "--title",
        "Route stalled queues",
        "--proposed-by",
        "role.manager",
        "--target-ref",
        "policy:queue-routing",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    body = json.loads(out)
    assert body["change_kind"] == "route_policy_change"
    assert body["title"] == "Route stalled queues"
    assert body["proposed_by"] == "role.manager"
    assert body["target_ref"] == "policy:queue-routing"
    assert body["source_refs"] == ["<evidence-ref>"]
    assert {
        check["invariant"] for check in body["invariant_checks"]
    } == {
        "deterministic_enforcement_floor",
        "fail_closed_behavior",
        "principal_independence",
        "tenant_boundary_preserved",
        "write_scope_preserved",
    }


def test_proposals_when_none_await_review(tmp_path, monkeypatch, capsys):
    config = _gov_config(tmp_path)
    _bind(monkeypatch, config)

    rc = main(["proposals"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "No governance changes are awaiting review." in out


def test_timeline_prints_a_plain_language_provenance_view(
    tmp_path, monkeypatch, capsys
):
    config = _gov_config(tmp_path)
    run = start_run(
        owner_role="role.manager",
        objective="inspect the queue",
        tenant_id="tenant-a",
        project_id="project-a",
        run_id="run_cli_timeline",
        log_path=config.transition_log,
    )
    append_checkpoint(
        run.run_id,
        actor="role.manager",
        step_id="inspect",
        status="completed",
        summary="Inspected the queue evidence.",
        log_path=config.transition_log,
    )
    _bind(monkeypatch, config)

    rc = main(["timeline", "--run-id", run.run_id])
    out = capsys.readouterr().out
    assert rc == 0
    assert "provenance timeline" in out
    assert "read-only" in out
    assert f"run_id={run.run_id}" in out
    assert "counts: kernel_events=" in out
    assert "run.started" in out
    assert "run.checkpoint" in out
    assert "{" not in out


def test_timeline_requires_a_selector(capsys):
    rc = main(["timeline"])
    captured = capsys.readouterr()
    assert rc == 2
    assert (
        "requires --run-id, --ref, --tenant-id, or --tenant-id with --project-id"
        in captured.err
    )


def test_timeline_rejects_unanchored_project_scope(capsys):
    rc = main(["timeline", "--project-id", "project-a"])
    captured = capsys.readouterr()
    assert rc == 2
    assert (
        "timeline --project-id requires --tenant-id unless --run-id anchors scope"
        in captured.err
    )


def test_human_pressure_prints_observer_only_groups(
    tmp_path, monkeypatch, capsys
):
    config = KernelServiceConfig(human_work_log=tmp_path / "human_work.jsonl")
    for index in range(3):
        create_agent_requested_human_work_session(
            requested_by_role="role.researcher",
            human_actor=f"human.{index}",
            objective=f"Check restricted source {index}.",
            work_mode="source_check",
            bottleneck_class="access",
            human_deliverable="bounded source receipt",
            tenant_id="tenant-a",
            project_id="project-a",
            log_path=config.human_work_log,
        )
    _bind(monkeypatch, config)

    rc = main([
        "human-pressure",
        "--agent-counterparty-role",
        "role.researcher",
        "--tenant-id",
        "tenant-a",
    ])
    out = capsys.readouterr().out

    assert rc == 0
    assert "human-work pressure - 1 group(s), observer-only" in out
    assert "tenant_id=tenant-a" in out
    assert "role.researcher / access" in out
    assert "missing_receipts: 3" in out
    assert "source connector" in out
    assert "not automation or routing decisions" in out
    assert "{" not in out


def test_speed_envelope_prints_accountable_speed(capsys):
    rc = main(
        [
            "speed-envelope",
            "--risk-tier",
            "irreversible",
            "--bottleneck-class",
            "authority",
            "--deployment-class",
            "external_write",
            "--no-reversible",
            "--external-side-effect",
        ]
    )
    out = capsys.readouterr().out

    assert rc == 0
    assert "human-speed envelope" in out
    assert "class:   gate_before_action" in out
    assert "record:  policy_decision_or_gate_plus_lease" in out
    assert "gate_required: true" in out
    assert "do not authorize or dispatch work" in out
    assert "{" not in out


def test_learning_candidates_prints_human_work_pressure_candidates(
    tmp_path, monkeypatch, capsys
):
    config = KernelServiceConfig(human_work_log=tmp_path / "human_work.jsonl")
    for index in range(3):
        create_agent_requested_human_work_session(
            requested_by_role="role.researcher",
            human_actor=f"human.{index}",
            objective=f"Check restricted source {index}.",
            work_mode="source_check",
            bottleneck_class="access",
            human_deliverable="bounded source receipt",
            tenant_id="tenant-a",
            project_id="project-a",
            session_id=f"hws_{index}",
            log_path=config.human_work_log,
        )
    _bind(monkeypatch, config)

    rc = main(["learning-candidates", "--source", "human_work"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "learning-transition candidates - 1 candidate(s), observer-only" in out
    assert "source: human_work" in out
    assert "a2h_pressure" in out
    assert "a2h_pressure:role.researcher:access" in out
    assert "human_work_session:hws_0" in out
    assert "{" not in out


def test_learning_candidates_accepts_attention_source(monkeypatch, capsys):
    captured_routes = []

    def fake_dispatch(method, route):
        captured_routes.append(route)
        return SimpleNamespace(
            status=200,
            payload={
                "source": "attention",
                "source_counts": {"attention": 1},
                "candidates": [
                    {
                        "candidate_id": "ltc_attention",
                        "transition_kind": "route_policy_change",
                        "severity": "warning",
                        "source_kind": "attention_unrouted_signal",
                        "object_ref": "attention_signal:gate_1",
                        "suggested_owner_role": "role.manager",
                        "rationale": "Attention signal has no target actor.",
                        "review_question": "Who should own this signal?",
                        "source_refs": ["gate://gate_1"],
                        "observer_only": True,
                    }
                ],
            },
        )

    monkeypatch.setattr(cli, "dispatch_kernel_request", fake_dispatch)

    rc = main(["learning-candidates", "--source", "attention"])
    out = capsys.readouterr().out

    assert rc == 0
    assert captured_routes == ["/kernel/learning-transition-candidates?source=attention"]
    assert "source: attention" in out
    assert "source_counts: attention=1" in out
    assert "attention_unrouted_signal" in out
    assert "{" not in out


def test_lease_terminal_loop_acquires_lists_and_releases(
    tmp_path, monkeypatch, capsys
):
    config = KernelServiceConfig(leases_log=tmp_path / "leases.jsonl")
    _bind(monkeypatch, config)

    rc = main([
        "lease-acquire",
        "governance_change:gcp_cli:decision",
        "--actor",
        "human.principal",
        "--role",
        "role.principal",
        "--ttl-seconds",
        "60",
        "--purpose",
        "approve proposal from terminal userland",
    ])
    out = capsys.readouterr().out

    assert rc == 0
    assert "lease lease_" in out
    assert "resource:      governance_change:gcp_cli:decision" in out
    assert "holder:        human.principal" in out
    assert "role:          role.principal" in out
    assert "--lease-id lease_" in out
    assert "--fencing-token 1" in out
    assert "{" not in out

    lease = list_leases(log_path=config.leases_log)[0]

    rc = main([
        "leases",
        "--resource-ref",
        "governance_change:gcp_cli:decision",
        "--state",
        "active",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "leases - 1 lease(s), read-only" in out
    assert f"[active] {lease.lease_id}" in out
    assert "token:    1" in out
    assert "{" not in out

    rc = main([
        "lease-release",
        lease.lease_id,
        "--actor",
        "human.principal",
        "--role",
        "role.principal",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert f"lease {lease.lease_id} released" in out
    assert "state:    released" in out

    rc = main(["leases", "--state", "active"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "leases - 0 lease(s), read-only" in out


def test_decision_profiles_print_read_only_procedure_recipes(capsys):
    rc = main(["decision-profiles"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "decision procedure profiles" in out
    assert "read-only" in out
    assert "binding: evidence_only" in out
    assert "quorum_majority" in out
    assert "unanimity" in out
    assert "{" not in out


def test_decision_case_terminal_lifecycle_records_procedure_evidence(
    tmp_path, monkeypatch, capsys
):
    config = KernelServiceConfig(
        decision_aggregation_log=tmp_path / "decision_aggregation.jsonl",
    )
    _bind(monkeypatch, config)

    rc = main([
        "decision-open",
        "--case-id",
        "dac_cli_review",
        "--subject-ref",
        "governance_change:gcp_cli_review",
        "--decision-class",
        "route_policy_change",
        "--scope-kind",
        "tenant",
        "--scope-ref",
        "tenant-a",
        "--procedure-profile",
        "majority",
        "--eligibility-basis",
        "two reviewer roles sampled from the release bucket",
        "--eligible-role",
        "role.reviewer_a",
        "--eligible-role",
        "role.reviewer_b",
        "--eligible-role",
        "role.reviewer_c",
        "--evidence-ref",
        "artifact://review-bucket/cli",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "decision aggregation case dac_cli_review opened" in out
    assert "binding:   evidence_only" in out
    assert "profile:   majority" in out
    assert "{" not in out

    for actor_id, role_id in (
        ("human.alice", "role.reviewer_a"),
        ("human.bob", "role.reviewer_b"),
    ):
        rc = main([
            "decision-position",
            "dac_cli_review",
            "--actor-id",
            actor_id,
            "--role-id",
            role_id,
            "--position",
            "approve",
            "--rationale",
            "Reviewed the evidence bucket.",
        ])
        out = capsys.readouterr().out
        assert rc == 0
        assert "decision position recorded for dac_cli_review" in out
        assert "position:  approve" in out
        assert "{" not in out

    rc = main(["decision-compute", "dac_cli_review"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "decision aggregation case dac_cli_review computed" in out
    assert "recommendation: approve" in out
    assert "quorum_met:     true" in out
    assert "evidence_only" in out
    assert "{" not in out

    rc = main(["decision-cases", "--subject-ref", "governance_change:gcp_cli_review"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "decision aggregation cases - 1 case(s), evidence-only" in out
    assert "result:    approve" in out


def test_decision_open_passes_mutation_lease_evidence(
    tmp_path, monkeypatch, capsys
):
    config = KernelServiceConfig(
        decision_aggregation_log=tmp_path / "decision_aggregation.jsonl",
        leases_log=tmp_path / "leases.jsonl",
        require_leases=True,
    )
    actor_context = {"actor_id": "human.principal", "actor_kind": "human"}
    lease = dispatch_kernel_request(
        "POST",
        "/kernel/leases",
        {
            "resource_ref": "decision_aggregation:open",
            "ttl_seconds": 60,
            "actor_context": actor_context,
        },
        config=config,
    )
    assert lease.status == 201
    _bind(monkeypatch, config)

    rc = main([
        "decision-open",
        "--case-id",
        "dac_cli_lease",
        "--subject-ref",
        "governance_change:gcp_cli_lease",
        "--decision-class",
        "route_policy_change",
        "--scope-kind",
        "tenant",
        "--scope-ref",
        "tenant-a",
        "--procedure-kind",
        "single_authority",
        "--eligibility-basis",
        "principal records one bounded evidence position",
        "--eligible-actor",
        "human.principal",
        "--actor",
        "human.principal",
        "--lease-id",
        lease.payload["lease"]["lease_id"],
        "--fencing-token",
        str(lease.payload["lease"]["fencing_token"]),
    ])
    out = capsys.readouterr().out

    assert rc == 0
    assert "decision aggregation case dac_cli_lease opened" in out
    assert "single_authority" in out


def test_decision_route_escalation_surfaces_learning_candidate(
    tmp_path, monkeypatch, capsys
):
    config = KernelServiceConfig(
        decision_aggregation_log=tmp_path / "decision_aggregation.jsonl",
        capability_signals_log=tmp_path / "capability_signals.jsonl",
    )
    _bind(monkeypatch, config)

    assert main([
        "decision-open",
        "--case-id",
        "dac_cli_escalate",
        "--subject-ref",
        "governance_change:gcp_cli_escalate",
        "--decision-class",
        "route_policy_change",
        "--scope-kind",
        "tenant",
        "--scope-ref",
        "tenant-a",
        "--procedure-kind",
        "quorum_majority",
        "--quorum",
        "2",
        "--eligibility-basis",
        "two reviewers needed for this bucket",
        "--eligible-role",
        "role.reviewer_a",
        "--eligible-role",
        "role.reviewer_b",
    ]) == 0
    capsys.readouterr()
    assert main([
        "decision-position",
        "dac_cli_escalate",
        "--actor-id",
        "human.alice",
        "--role-id",
        "role.reviewer_a",
        "--position",
        "approve",
        "--rationale",
        "One reviewer approved; quorum is still missing.",
    ]) == 0
    capsys.readouterr()
    assert main(["decision-compute", "dac_cli_escalate"]) == 0
    capsys.readouterr()

    rc = main([
        "decision-route-escalation",
        "dac_cli_escalate",
        "--summary",
        "Reviewer quorum failed for the release bucket.",
        "--owner-role",
        "role.manager",
        "--actor",
        "role.manager",
    ])
    out = capsys.readouterr().out

    assert rc == 0
    assert "decision aggregation escalation routed for dac_cli_escalate" in out
    assert "candidate:" in out
    assert "resolved_decision=False" in out
    assert "override:  False" in out
    assert "{" not in out


def test_proposal_from_candidate_preserves_governance_gate(
    tmp_path, monkeypatch, capsys
):
    config = KernelServiceConfig(
        human_work_log=tmp_path / "human_work.jsonl",
        org_dir=tmp_path / "org",
    )
    for index in range(3):
        create_agent_requested_human_work_session(
            requested_by_role="role.researcher",
            human_actor=f"human.{index}",
            objective=f"Check restricted source {index}.",
            work_mode="source_check",
            bottleneck_class="access",
            human_deliverable="bounded source receipt",
            session_id=f"hws_{index}",
            log_path=config.human_work_log,
        )
    candidates = dispatch_kernel_request(
        "GET",
        "/kernel/learning-transition-candidates?source=human_work",
        config=config,
    ).payload["candidates"]
    candidate_id = candidates[0]["candidate_id"]
    _bind(monkeypatch, config)

    rc = main([
        "proposal-from-candidate",
        candidate_id,
        "--source",
        "human_work",
        "--target-ref",
        "org/policies/source-access.md",
        "--expected-behavior-change",
        "Review repeated source-access pressure before future routing changes.",
        "--risk-summary",
        "May overcorrect by automating useful human source checks.",
        "--rollback-plan",
        "Retire the policy change and restore manual review.",
        "--actor",
        "role.manager",
    ])
    out = capsys.readouterr().out

    assert rc == 0
    assert "governance proposal" in out
    assert "from candidate" in out
    assert "status:      blocked" in out
    assert "invariants:  missing checks" in out
    assert "learning_transition_candidate:" in out
    assert "{" not in out

    proposals = dispatch_kernel_request(
        "GET",
        "/kernel/governance-changes",
        config=config,
    ).payload["proposals"]
    assert len(proposals) == 1
    proposal = proposals[0]
    assert proposal["status"] == "blocked"
    assert proposal["metadata"]["candidate_id"] == candidate_id
    assert "human_work_session:hws_0" in proposal["source_refs"]


def test_graph_prints_projection_edges(tmp_path, monkeypatch, capsys):
    config = _gov_config(tmp_path)
    run = start_run(
        owner_role="role.manager",
        objective="inspect the queue graph",
        tenant_id="tenant-a",
        project_id="project-a",
        run_id="run_cli_graph",
        log_path=config.transition_log,
    )
    append_checkpoint(
        run.run_id,
        actor="role.manager",
        step_id="inspect",
        status="completed",
        summary="Inspected graph evidence.",
        payload_ref="artifact://graph-evidence",
        log_path=config.transition_log,
    )
    _bind(monkeypatch, config)

    rc = main(["graph", "--run-id", run.run_id, "--limit", "4"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "provenance graph" in out
    assert "read-only projection" in out
    assert f"run_id={run.run_id}" in out
    assert "not workflow state" in out
    assert "--mentions_ref-->" in out
    assert "artifact://graph-evidence" in out
    assert "{" not in out


def test_graph_requires_a_selector(capsys):
    rc = main(["graph"])
    captured = capsys.readouterr()
    assert rc == 2
    assert (
        "requires --run-id, --ref, --tenant-id, or --tenant-id with --project-id"
        in captured.err
    )


def test_graph_rejects_unanchored_project_scope(capsys):
    rc = main(["graph", "--project-id", "project-a"])
    captured = capsys.readouterr()
    assert rc == 2
    assert (
        "graph --project-id requires --tenant-id unless --run-id anchors scope"
        in captured.err
    )


def test_provenance_report_prints_portable_handoff(
    tmp_path, monkeypatch, capsys
):
    config = KernelServiceConfig(
        org_dir=tmp_path / "org",
        transition_log=tmp_path / "transitions.jsonl",
        action_attestation_log=tmp_path / "action_attestations.jsonl",
        human_work_log=tmp_path / "human_work.jsonl",
        outcome_links_log=tmp_path / "outcome_links.jsonl",
        routine_reviews_log=tmp_path / "routine_reviews.jsonl",
        learning_events_log=tmp_path / "learning_events.jsonl",
        learning_encounters_log=tmp_path / "learning_encounters.jsonl",
    )
    run = start_run(
        owner_role="role.manager",
        objective="inspect the queue report",
        tenant_id="tenant-a",
        project_id="project-a",
        run_id="run_cli_report",
        log_path=config.transition_log,
    )
    append_checkpoint(
        run.run_id,
        actor="role.manager",
        step_id="inspect",
        status="completed",
        summary="Inspected report evidence.",
        payload_ref="artifact://report-evidence",
        log_path=config.transition_log,
    )
    _bind(monkeypatch, config)

    rc = main(["provenance-report", "--run-id", run.run_id, "--event-limit", "3"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "provenance report" in out
    assert "read-only projection" in out
    assert "coverage=partial" in out
    assert f"run_id={run.run_id}" in out
    assert "gap:" in out
    assert "review questions:" in out
    assert "artifact://report-evidence" in out
    assert "{" not in out

    rc = main(["provenance-report", "--run-id", run.run_id, "--markdown"])
    markdown = capsys.readouterr().out
    assert rc == 0
    assert "# Provenance Report" in markdown
    assert "artifact://report-evidence" in markdown


def test_provenance_report_requires_a_selector(capsys):
    rc = main(["provenance-report"])
    captured = capsys.readouterr()
    assert rc == 2
    assert (
        "requires --run-id, --ref, --tenant-id, or --tenant-id with --project-id"
        in captured.err
    )


def test_provenance_report_rejects_unanchored_project_scope(capsys):
    rc = main(["provenance-report", "--project-id", "project-a"])
    captured = capsys.readouterr()
    assert rc == 2
    assert (
        "provenance-report --project-id requires --tenant-id "
        "unless --run-id anchors scope"
    ) in captured.err


def test_composition_packet_prints_read_only_traceability_matrix(
    tmp_path,
    monkeypatch,
    capsys,
):
    config = KernelServiceConfig(org_dir=tmp_path / "org", require_leases=True)
    _bind(monkeypatch, config)
    observed_path = tmp_path / "first-gated-action.json"
    observed_path.write_text(
        json.dumps(
            {
                "bundle_validation": {"ok": True},
                "summary": {
                    "verdict": "passed",
                    "run_id": "run_1",
                    "bundle_id": "gab_1",
                    "bundle_digest": "sha256:" + "a" * 64,
                    "authority_snapshot": {
                        "status": "resolved",
                        "role_ref": "org/roles/analyst.yaml",
                        "mandate_ref": "org/mandates/analyst.md",
                        "mandate_hash": "abc123",
                    },
                    "ids": {
                        "action_attestations": ["aat_1"],
                        "human_work_sessions": ["hws_1"],
                        "outcome_links": ["olink_1"],
                        "work_items": ["work_1"],
                    },
                },
                "work_item": {"status": "done", "work_id": "work_1"},
            }
        ),
        encoding="utf-8",
    )

    rc = main([
        "composition-packet",
        "--observed-json",
        str(observed_path),
        "--action-label",
        "first gated action",
    ])
    out = capsys.readouterr().out

    assert rc == 0
    assert "governed action composition" in out
    assert "status:      ready_for_review" in out
    assert "read_only:   true" in out
    assert "blockers:    0" in out
    assert "{" not in out


def test_composition_packet_returns_nonzero_for_required_blockers(
    tmp_path,
    monkeypatch,
    capsys,
):
    config = KernelServiceConfig(org_dir=tmp_path / "org", require_leases=True)
    _bind(monkeypatch, config)
    observed_path = tmp_path / "thin-green-demo.json"
    observed_path.write_text(
        json.dumps(
            {
                "bundle_validation": {"ok": True},
                "summary": {
                    "verdict": "passed",
                    "run_id": "run_1",
                    "bundle_id": "gab_1",
                    "bundle_digest": "sha256:" + "a" * 64,
                    "authority_snapshot": {"status": "resolved"},
                    "ids": {"action_attestations": ["aat_1"]},
                },
                "work_item": {"status": "done", "work_id": "work_1"},
            }
        ),
        encoding="utf-8",
    )

    rc = main([
        "composition-packet",
        "--observed-json",
        str(observed_path),
        "--action-label",
        "thin green demo",
    ])
    out = capsys.readouterr().out

    assert rc == 1
    assert "status:      missing_required_evidence" in out
    assert "required blockers:" in out
    assert "human_work: missing" in out
    assert "{" not in out


def test_work_context_prints_context_packet_without_raw_json(
    tmp_path, monkeypatch, capsys
):
    config = KernelServiceConfig(
        learning_events_log=tmp_path / "learning_events.jsonl",
        outcome_links_log=tmp_path / "outcome_links.jsonl",
        routine_reviews_log=tmp_path / "routine_reviews.jsonl",
    )
    event = create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Route stalled queues through reviewer handoff.",
        future_application_cue="queue stalls",
        approved_by="role.owner",
        approval_ref="governance_change:gcp_queue_review",
        owner_role="role.manager",
        tenant_id="tenant-a",
        log_path=config.learning_events_log,
    )
    _bind(monkeypatch, config)

    rc = main([
        "work-context",
        "--assigned-to",
        "role.manager",
        "--tenant-id",
        "tenant-a",
        "--cue",
        "queue stalls",
        "--learning-only",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "work context" in out
    assert "read-only" in out
    assert "packet:" in out
    assert "policy:      projection_only" in out
    assert "learning_events=1" in out
    assert event.learning_event_id in out
    assert "Route stalled queues through reviewer handoff." in out
    assert "{" not in out


def test_work_context_prints_structured_filters_without_role(
    tmp_path, monkeypatch, capsys
):
    config = KernelServiceConfig(
        learning_events_log=tmp_path / "learning_events.jsonl",
        outcome_links_log=tmp_path / "outcome_links.jsonl",
        routine_reviews_log=tmp_path / "routine_reviews.jsonl",
    )
    event = create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Check provider proof evidence before trusting verifier output.",
        future_application_cue="formal verifier provider payload",
        approved_by="role.owner",
        approval_ref="governance_change:gcp_provider_proof",
        tenant_id="tenant-a",
        metadata={
            "cue_signatures": ["formal_verification.provider_payload"],
            "resource_refs": ["formal_provider:trusted_checker"],
            "topology_refs": ["state_surface:formal_verifications"],
        },
        log_path=config.learning_events_log,
    )
    _bind(monkeypatch, config)

    rc = main([
        "work-context",
        "--tenant-id",
        "tenant-a",
        "--cue-signature",
        "formal_verification.provider_payload",
        "--resource-ref",
        "formal_provider:trusted_checker",
        "--topology-ref",
        "state_surface:formal_verifications",
    ])

    out = capsys.readouterr().out
    assert rc == 0
    assert "assigned_to: structured query" in out
    assert "cue_sig:     formal_verification.provider_payload" in out
    assert "resources:   formal_provider:trusted_checker" in out
    assert "topology:    state_surface:formal_verifications" in out
    assert "candidates:  suppressed for no-role structured query" in out
    assert event.learning_event_id in out
    assert "Check provider proof evidence before trusting verifier output." in out
    assert "{" not in out


def test_context_packet_verify_checks_captured_work_context(
    tmp_path, monkeypatch, capsys
):
    config = KernelServiceConfig(
        learning_events_log=tmp_path / "learning_events.jsonl",
        outcome_links_log=tmp_path / "outcome_links.jsonl",
        routine_reviews_log=tmp_path / "routine_reviews.jsonl",
    )
    create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Route stalled queues through reviewer handoff.",
        future_application_cue="queue stalls",
        approved_by="role.owner",
        approval_ref="governance_change:gcp_queue_review",
        owner_role="role.manager",
        tenant_id="tenant-a",
        log_path=config.learning_events_log,
    )
    _bind(monkeypatch, config)
    context = dispatch_kernel_request(
        "GET",
        "/kernel/work-discovery?assigned_to=role.manager&tenant_id=tenant-a&cue=queue+stalls&learning_only=true",
        config=config,
    ).payload
    packet_path = tmp_path / "work_context.json"
    packet_path.write_text(json.dumps(context, sort_keys=True), encoding="utf-8")

    rc = main(["context-packet-verify", str(packet_path)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "context packet verification" in out
    assert "ok:          true" in out
    assert "digest_only_no_log_lookup" in out
    assert "{" not in out

    tampered = dict(context["context_packet"])
    tampered["basis"] = {
        **context["context_packet"]["basis"],
        "learning_event_ids": ["learn_tampered"],
    }
    packet_path.write_text(json.dumps(tampered, sort_keys=True), encoding="utf-8")

    rc = main(["context-packet-verify", str(packet_path)])
    out = capsys.readouterr().out

    assert rc == 1
    assert "ok:          false" in out
    assert "context_packet.digest does not match basis" in out


def test_context_packet_verify_rejects_non_object_json(
    tmp_path, capsys
):
    packet_path = tmp_path / "invalid_context_packet.json"
    packet_path.write_text(json.dumps(["not", "a", "packet"]), encoding="utf-8")

    rc = main(["context-packet-verify", str(packet_path)])
    captured = capsys.readouterr()

    assert rc == 2
    assert "context packet JSON must contain an object" in captured.err

    packet_path.write_text(json.dumps({"context_packet": None}), encoding="utf-8")

    rc = main(["context-packet-verify", str(packet_path)])
    captured = capsys.readouterr()

    assert rc == 2
    assert "context packet JSON must contain an object" in captured.err


def test_learning_use_records_a_context_packet_receipt(
    tmp_path, monkeypatch, capsys
):
    config = KernelServiceConfig(
        learning_events_log=tmp_path / "learning_events.jsonl",
        learning_encounters_log=tmp_path / "learning_encounters.jsonl",
    )
    event = create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Route stalled queues through reviewer handoff.",
        future_application_cue="queue stalls",
        approved_by="role.owner",
        approval_ref="governance_change:gcp_queue_review",
        owner_role="role.manager",
        tenant_id="tenant-a",
        log_path=config.learning_events_log,
    )
    _bind(monkeypatch, config)

    rc = main([
        "learning-use",
        event.learning_event_id,
        "--role",
        "role.manager",
        "--cue",
        "queue stalls",
        "--outcome",
        "applied",
        "--context-packet-ref",
        "ctx_queue",
        "--tenant-id",
        "tenant-a",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert "learning-use receipt" in out
    assert event.learning_event_id in out
    assert "outcome:        applied" in out
    assert "context_packet: ctx_queue" in out
    assert "{" not in out


def test_learning_use_verifies_context_packet_json(
    tmp_path, monkeypatch, capsys
):
    config = KernelServiceConfig(
        learning_events_log=tmp_path / "learning_events.jsonl",
        learning_encounters_log=tmp_path / "learning_encounters.jsonl",
        outcome_links_log=tmp_path / "outcome_links.jsonl",
        routine_reviews_log=tmp_path / "routine_reviews.jsonl",
    )
    event = create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Route stalled queues through reviewer handoff.",
        future_application_cue="queue stalls",
        approved_by="role.owner",
        approval_ref="governance_change:gcp_queue_review",
        owner_role="role.manager",
        tenant_id="tenant-a",
        log_path=config.learning_events_log,
    )
    other_event = create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Use a different queue routine.",
        future_application_cue="other queue routine",
        approved_by="role.owner",
        approval_ref="governance_change:gcp_other",
        owner_role="role.manager",
        tenant_id="tenant-a",
        log_path=config.learning_events_log,
    )
    _bind(monkeypatch, config)
    context = dispatch_kernel_request(
        "GET",
        "/kernel/work-discovery?assigned_to=role.manager&tenant_id=tenant-a&cue=queue+stalls&learning_only=true",
        config=config,
    ).payload
    packet_path = tmp_path / "work_context.json"
    packet_path.write_text(json.dumps(context, sort_keys=True), encoding="utf-8")

    rc = main([
        "learning-use",
        event.learning_event_id,
        "--role",
        "role.manager",
        "--cue",
        "queue stalls",
        "--outcome",
        "applied",
        "--context-packet-json",
        str(packet_path),
    ])
    out = capsys.readouterr().out

    assert rc == 0
    assert "learning-use receipt" in out
    assert context["context_packet"]["context_packet_id"] in out

    rc = main(["learning-loop", event.learning_event_id])
    out = capsys.readouterr().out

    assert rc == 0
    assert "verified_packets:" in out
    assert context["context_packet"]["context_packet_id"] in out

    rc = main([
        "learning-use",
        other_event.learning_event_id,
        "--role",
        "role.manager",
        "--cue",
        "queue stalls",
        "--outcome",
        "applied",
        "--context-packet-json",
        str(packet_path),
    ])
    captured = capsys.readouterr()

    assert rc == 2
    assert "context_packet does not include learning_event_id" in captured.err


def test_learning_use_rejects_non_object_context_packet_json(
    tmp_path, monkeypatch, capsys
):
    config = KernelServiceConfig(
        learning_events_log=tmp_path / "learning_events.jsonl",
        learning_encounters_log=tmp_path / "learning_encounters.jsonl",
    )
    event = create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Route stalled queues through reviewer handoff.",
        future_application_cue="queue stalls",
        approved_by="role.owner",
        approval_ref="governance_change:gcp_queue_review",
        owner_role="role.manager",
        tenant_id="tenant-a",
        log_path=config.learning_events_log,
    )
    _bind(monkeypatch, config)
    packet_path = tmp_path / "invalid_context_packet.json"
    packet_path.write_text(json.dumps(["not", "a", "packet"]), encoding="utf-8")

    rc = main([
        "learning-use",
        event.learning_event_id,
        "--role",
        "role.manager",
        "--cue",
        "queue stalls",
        "--outcome",
        "applied",
        "--context-packet-json",
        str(packet_path),
    ])
    captured = capsys.readouterr()

    assert rc == 2
    assert "context packet JSON must contain an object" in captured.err
    assert list_learning_event_encounters(log_path=config.learning_encounters_log) == []

    packet_path.write_text(json.dumps({"context_packet": None}), encoding="utf-8")

    rc = main([
        "learning-use",
        event.learning_event_id,
        "--role",
        "role.manager",
        "--cue",
        "queue stalls",
        "--outcome",
        "applied",
        "--context-packet-json",
        str(packet_path),
    ])
    captured = capsys.readouterr()

    assert rc == 2
    assert "context packet JSON must contain an object" in captured.err
    assert list_learning_event_encounters(log_path=config.learning_encounters_log) == []


def test_learning_loop_prints_one_event_closure_state(
    tmp_path, monkeypatch, capsys
):
    config = KernelServiceConfig(
        learning_events_log=tmp_path / "learning_events.jsonl",
        learning_encounters_log=tmp_path / "learning_encounters.jsonl",
        outcome_links_log=tmp_path / "outcome_links.jsonl",
        routine_reviews_log=tmp_path / "routine_reviews.jsonl",
    )
    event = create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Route stalled queues through reviewer handoff.",
        future_application_cue="queue stalls",
        approved_by="role.owner",
        approval_ref="governance_change:gcp_queue_review",
        owner_role="role.manager",
        tenant_id="tenant-a",
        metadata={
            "cue_signatures": ["queue.stalled"],
            "resource_refs": ["work_queue:triage"],
        },
        log_path=config.learning_events_log,
    )
    record_learning_event_encounter(
        learning_event_id=event.learning_event_id,
        role="role.manager",
        cue="queue stalls",
        outcome="applied",
        context_packet_ref="ctx_queue",
        tenant_id="tenant-a",
        log_path=config.learning_encounters_log,
    )
    link = create_outcome_link(
        change_ref=f"learning_event:{event.learning_event_id}",
        change_kind="learning_event",
        learning_event_id=event.learning_event_id,
        metric_name="queue_cycle_time",
        metric_unit="hours",
        created_by="role.manager",
        tenant_id="tenant-a",
        log_path=config.outcome_links_log,
    )
    review = schedule_routine_review(
        routine_ref=f"learning_event:{event.learning_event_id}",
        routine_kind="learning_event",
        learning_event_id=event.learning_event_id,
        review_due_utc="2999-01-01T00:00:00+00:00",
        scheduled_by="role.manager",
        tenant_id="tenant-a",
        log_path=config.routine_reviews_log,
    )
    _bind(monkeypatch, config)

    rc = main(["learning-loop", event.learning_event_id])
    out = capsys.readouterr().out
    assert rc == 0
    assert f"learning loop {event.learning_event_id}" in out
    assert "state:          awaiting_outcome_verdict" in out
    assert "Route stalled queues through reviewer handoff." in out
    assert "cue_signatures: queue.stalled" in out
    assert "resource_refs: work_queue:triage" in out
    assert "context_packets: ctx_queue" in out
    assert "encounters: applied=1" in out
    assert "outcome_links: 1" in out
    assert "routine_reviews: 1" in out
    assert link.outcome_link_id in out
    assert review.review_id in out
    assert "{" not in out


def test_learning_use_surfaces_kernel_receipt_validation(
    tmp_path, monkeypatch, capsys
):
    config = KernelServiceConfig(
        learning_events_log=tmp_path / "learning_events.jsonl",
        learning_encounters_log=tmp_path / "learning_encounters.jsonl",
    )
    event = create_learning_event(
        learning_unit_kind="routine_change",
        decision_use="Route stalled queues through reviewer handoff.",
        future_application_cue="queue stalls",
        approved_by="role.owner",
        approval_ref="governance_change:gcp_queue_review",
        owner_role="role.manager",
        tenant_id="tenant-a",
        log_path=config.learning_events_log,
    )
    _bind(monkeypatch, config)

    rc = main([
        "learning-use",
        event.learning_event_id,
        "--role",
        "role.manager",
        "--cue",
        "queue stalls",
        "--outcome",
        "ignored",
    ])
    captured = capsys.readouterr()
    assert rc == 2
    assert "ignored learning encounters require a reason" in captured.err


def test_approve_records_an_attested_event(tmp_path, monkeypatch, capsys):
    config = _gov_config(tmp_path)
    proposal = propose_governance_change(
        change_kind="role_change",
        title="Widen analyst write scope",
        proposed_by="operator",
        target_ref="roles/analyst.yaml",
        rationale="overlay install",
        **_review_ready_evidence(),
        invariant_checks=_passing_checks(),
        log_path=_governance_log(config),
    )
    _bind(monkeypatch, config)

    rc = main(["approve", proposal.proposal_id, "--reason", "reviewed"])
    out = capsys.readouterr().out
    assert rc == 0
    assert f"governance change {proposal.proposal_id} approved" in out
    assert "attested event:" in out

    events = list_kernel_events(log_path=config.transition_log)
    approved = [e for e in events if e.verb == "governance_change.approved"]
    assert len(approved) == 1
    assert approved[0].object_ref == f"governance_change:{proposal.proposal_id}"
    assert approved[0].payload["reason"] == "reviewed"


def test_approve_passes_mutation_lease_evidence(
    tmp_path, monkeypatch, capsys
):
    config = KernelServiceConfig(
        org_dir=tmp_path / "org",
        transition_log=tmp_path / "transitions.jsonl",
        gates_dir=tmp_path / "gates" / "pending",
        gates_resolved_dir=tmp_path / "gates" / "resolved",
        leases_log=tmp_path / "leases.jsonl",
        require_leases=True,
    )
    proposal = propose_governance_change(
        change_kind="role_change",
        title="Widen analyst write scope",
        proposed_by="operator",
        target_ref="roles/analyst.yaml",
        rationale="overlay install",
        **_review_ready_evidence(),
        invariant_checks=_passing_checks(),
        log_path=_governance_log(config),
    )
    actor_context = {
        "actor_id": "human.principal",
        "actor_kind": "human",
        "role_id": "role.principal",
    }
    lease = dispatch_kernel_request(
        "POST",
        "/kernel/leases",
        {
            "resource_ref": f"governance_change:{proposal.proposal_id}:decision",
            "ttl_seconds": 60,
            "actor_context": actor_context,
        },
        config=config,
    )
    assert lease.status == 201
    _bind(monkeypatch, config)

    rc = main([
        "approve",
        proposal.proposal_id,
        "--actor",
        "human.principal",
        "--reason",
        "reviewed with fenced approval",
        "--lease-id",
        lease.payload["lease"]["lease_id"],
        "--fencing-token",
        str(lease.payload["lease"]["fencing_token"]),
    ])

    out = capsys.readouterr().out
    assert rc == 0
    assert f"governance change {proposal.proposal_id} approved" in out
    approved = [
        e
        for e in list_kernel_events(log_path=config.transition_log)
        if e.verb == "governance_change.approved"
    ]
    assert len(approved) == 1
    assert approved[0].actor == "human.principal"


def test_decline_records_an_attested_event(tmp_path, monkeypatch, capsys):
    config = _gov_config(tmp_path)
    proposal = propose_governance_change(
        change_kind="role_change",
        title="Widen analyst write scope",
        proposed_by="operator",
        target_ref="roles/analyst.yaml",
        rationale="overlay install",
        **_review_ready_evidence(),
        invariant_checks=_passing_checks(),
        log_path=_governance_log(config),
    )
    _bind(monkeypatch, config)

    rc = main(["decline", proposal.proposal_id, "--actor", "human_lead"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "declined by human_lead" in out

    events = list_kernel_events(log_path=config.transition_log)
    declined = [e for e in events if e.verb == "governance_change.declined"]
    assert len(declined) == 1
    assert declined[0].actor == "human_lead"


def test_an_approved_proposal_stops_appearing_in_proposals(
    tmp_path, monkeypatch, capsys
):
    config = _gov_config(tmp_path)
    proposal = propose_governance_change(
        change_kind="role_change",
        title="Widen analyst write scope",
        proposed_by="operator",
        target_ref="roles/analyst.yaml",
        rationale="overlay install",
        **_review_ready_evidence(),
        invariant_checks=_passing_checks(),
        log_path=_governance_log(config),
    )
    _bind(monkeypatch, config)

    assert main(["proposals"]) == 0
    assert "awaiting review:" in capsys.readouterr().out

    assert main(["approve", proposal.proposal_id]) == 0
    capsys.readouterr()

    # The loop closes: a decided proposal no longer nags the operator.
    assert main(["proposals"]) == 0
    assert "No governance changes are awaiting review." in capsys.readouterr().out


def test_a_proposal_cannot_be_decided_twice(tmp_path, monkeypatch, capsys):
    config = _gov_config(tmp_path)
    proposal = propose_governance_change(
        change_kind="role_change",
        title="Widen analyst write scope",
        proposed_by="operator",
        target_ref="roles/analyst.yaml",
        rationale="overlay install",
        **_review_ready_evidence(),
        invariant_checks=_passing_checks(),
        log_path=_governance_log(config),
    )
    _bind(monkeypatch, config)

    assert main(["approve", proposal.proposal_id]) == 0
    capsys.readouterr()

    rc = main(["decline", proposal.proposal_id])
    captured = capsys.readouterr()
    assert rc == 2
    assert "already been decided" in captured.err


def test_approve_a_missing_proposal_errors(tmp_path, monkeypatch, capsys):
    config = _gov_config(tmp_path)
    _bind(monkeypatch, config)

    rc = main(["approve", "gcp_does_not_exist"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "ERROR:" in captured.err


def test_approve_a_blocked_proposal_is_refused(tmp_path, monkeypatch, capsys):
    config = _gov_config(tmp_path)
    # An expanding overlay fails write_scope_preserved -> status "blocked".
    proposal = propose_governance_change(
        change_kind="role_change",
        title="Authority-expanding overlay",
        proposed_by="operator",
        target_ref="roles/analyst.yaml",
        rationale="overlay install",
        invariant_checks=[
            InvariantCheck(
                invariant="write_scope_preserved",
                status="fail",
                rationale="overlay widens authority",
            )
        ],
        log_path=_governance_log(config),
    )
    assert proposal.status == "blocked"
    _bind(monkeypatch, config)

    rc = main(["approve", proposal.proposal_id])
    captured = capsys.readouterr()
    assert rc == 2
    assert "not awaiting review" in captured.err
