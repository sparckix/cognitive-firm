"""Cross-primitive integration test.

Each primitive has unit tests; this test exercises the SEAMS between them.

Scenario (a typical research-firm task flow):

  1. Role A (research_director) delegates work to Role B (debate_runner)
     via a `request` AgentMessage. Obligation lifecycle starts at `pending`.

  2. Role B accepts (`pending` -> `accepted` -> `in_progress`).

  3. Role B's task awaits an artifact a producer role committed to deliver.
     Producer emits `task.artifact.promised` then `task.artifact.fulfilled`
     to transitions.jsonl with a deterministic predicate_hash.

  4. Role B's `awaits` filter sees the predicate_hash satisfied; the task
     is dispatchable.

  5. Role B completes work; obligation transitions
     `in_progress` -> `fulfilled`.

  6. Saga compensation primitive sees no terminal failure in the chain
     and does NOT fire. list_active_sagas() returns empty.

  7. The transition log shows the expected end-to-end event sequence:
       agent.message.sent (request)
       agent.obligation.accepted
       agent.obligation.in_progress
       task.artifact.promised
       task.artifact.fulfilled
       agent.obligation.fulfilled

This is the seam-bug test that unit tests miss: a primitive whose unit
tests pass can still misbehave when its outputs are consumed by another
primitive whose unit tests also pass.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration import agent_channels
from cognitive_firm.orchestration.agent_channels import (
    send_agent_message,
    update_obligation_state,
    list_blocked_obligations,
)
from cognitive_firm.orchestration.artifact_dependencies import (
    promise_artifact,
    fulfill_artifact,
    is_awaits_satisfied,
    predicate_hash,
)
from cognitive_firm.orchestration.saga_compensation import (
    list_active_sagas,
    compensate_failed_obligation,
)
from cognitive_firm.orchestration import transition_log
from cognitive_firm.orchestration import saga_compensation as saga_mod


# ── fixture: redirect channel + transition log into tmp_path ────────────


@pytest.fixture
def isolated_state(tmp_path: Path, monkeypatch):
    """Redirect channels dir, roles dir, and transition log into tmp_path
    so the test runs in clean state and does not touch real org/."""
    channels = tmp_path / "channels"
    channels.mkdir()
    roles = tmp_path / "roles"
    roles.mkdir()

    # Two roles linked via delegates_to
    (roles / "research_director.yaml").write_text(
        "role_id: research_director\n"
        "delegates_to:\n  - debate_runner\nescalates_to:\n  - manager\n",
        encoding="utf-8",
    )
    (roles / "debate_runner.yaml").write_text(
        "role_id: debate_runner\n"
        "delegates_to:\nescalates_to:\n  - research_director\n",
        encoding="utf-8",
    )
    (roles / "manager.yaml").write_text(
        "role_id: manager\n"
        "delegates_to:\n  - research_director\n  - debate_runner\nescalates_to:\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(agent_channels, "CHANNELS_DIR", channels)
    monkeypatch.setattr(agent_channels, "ROLES_DIR", roles)
    monkeypatch.setattr(saga_mod, "CHANNELS_DIR", channels)

    log_path = tmp_path / "transitions.jsonl"
    monkeypatch.setattr(transition_log, "TRANSITIONS_LOG", log_path)
    monkeypatch.setattr(saga_mod, "TRANSITIONS_LOG", log_path)

    yield tmp_path


def _read_log_events(log_path: Path) -> list[dict]:
    """Helper: return all event records from the transition log in order."""
    if not log_path.exists():
        return []
    out = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    return out


# ── the test ────────────────────────────────────────────────────────────


def test_obligation_with_artifact_dependency_completes_no_saga(isolated_state):
    """End-to-end happy path: obligation A delegates to B, B awaits an
    artifact, producer fulfills it, B completes, no saga.

    The seam this test catches: if any primitive emits the wrong event
    name, fails to record a transition, or breaks predicate_hash determinism,
    the chain breaks and downstream primitives misbehave.
    """
    log_path = isolated_state / "transitions.jsonl"

    # Step 1 — research_director delegates to debate_runner via a request.
    # The request body asserts the task awaits an artifact.
    request_msg = send_agent_message(
        from_role="research_director",
        to_role="debate_runner",
        kind="request",
        subject="Append next turn to GP-031 debate seam",
        body=(
            "Append the next debate turn to seam GP-031. "
            "This task awaits the latest evidence_compile artifact "
            "with score >= 0.7 before proceeding."
        ),
        metadata={
            "task_id": "task_gp031_next_turn",
            "awaits": [
                {"artifact_key": "evidence_compile.gp031", "predicate_hash": predicate_hash("score >= 0.7")},
            ],
        },
    )
    assert request_msg.obligation_state == "pending"
    assert request_msg.kind == "request"

    # Step 2 — debate_runner accepts and starts work.
    update_obligation_state(role_id="debate_runner", message_id=request_msg.message_id,
                            new_state="accepted", actor="debate_runner",
                            note="acknowledging GP-031 next-turn request")
    update_obligation_state(role_id="debate_runner", message_id=request_msg.message_id,
                            new_state="in_progress", actor="debate_runner")

    # Step 3 — Before B can finish, a producer emits the artifact promise +
    # fulfillment that B's awaits depend on.
    predicate = "score >= 0.7"
    p_hash = predicate_hash(predicate)

    promise_artifact(
        role_id="evidence_producer",
        task_id="task_evidence_compile_gp031",
        artifact_key="evidence_compile.gp031",
        predicate=predicate,
        causality_id="obj_gp031_evidence",
        log_path=log_path,
    )
    fulfill_artifact(
        role_id="evidence_producer",
        task_id="task_evidence_compile_gp031",
        artifact_key="evidence_compile.gp031",
        artifact_path="org/artifacts/gp031/evidence_v3.md",
        sha256="abc123def456" * 5 + "0123",
        predicate=predicate,
        predicate_eval={"score_ge_0_7": True},
        causality_id="obj_gp031_evidence",
        log_path=log_path,
    )

    # Step 4 — verify B's awaits filter sees the artifact as ready.
    awaits = [{"artifact_key": "evidence_compile.gp031", "predicate_hash": p_hash}]
    ready, missing = is_awaits_satisfied(awaits, log_path=log_path)
    assert ready is True, f"awaits not satisfied; missing: {missing}"
    assert missing == []

    # Step 5 — B completes the work.
    update_obligation_state(role_id="debate_runner", message_id=request_msg.message_id,
                            new_state="fulfilled", actor="debate_runner",
                            note="appended turn 16; debate state IN_PROGRESS")

    # Step 6 — saga compensation: no terminal failure, so should not fire.
    active = list_active_sagas(log_path=log_path)
    assert active == [], (
        f"saga unexpectedly active on a happy-path completion: {active}"
    )

    # And: list_blocked_obligations should be empty (nothing in blocked_input).
    blocked = list_blocked_obligations()
    assert blocked == [], (
        f"obligation unexpectedly blocked after fulfillment: {[m.subject for m in blocked]}"
    )

    # Step 7 — verify the transition log shows the expected event sequence.
    events = _read_log_events(log_path)
    event_names = [e.get("event") for e in events]
    expected_subset = [
        "agent.message.sent",
        "agent.obligation.accepted",
        "agent.obligation.in_progress",
        "task.artifact.promised",
        "task.artifact.fulfilled",
        "agent.obligation.fulfilled",
    ]
    for expected in expected_subset:
        assert expected in event_names, (
            f"missing expected event '{expected}' in log; got: {event_names}"
        )

    # Stronger: the obligation events must appear in lifecycle order.
    obligation_events = [e for e in events if e.get("event", "").startswith("agent.obligation.")]
    obligation_states_in_order = [e["event"].split(".")[-1] for e in obligation_events]
    assert obligation_states_in_order == ["accepted", "in_progress", "fulfilled"], (
        f"obligation events out of order: {obligation_states_in_order}"
    )

    # And the artifact events must come BEFORE the fulfilled obligation
    # (B couldn't have fulfilled if the artifact wasn't ready).
    fulfilled_obligation_idx = next(
        i for i, e in enumerate(events) if e.get("event") == "agent.obligation.fulfilled"
    )
    artifact_fulfilled_idx = next(
        i for i, e in enumerate(events) if e.get("event") == "task.artifact.fulfilled"
    )
    assert artifact_fulfilled_idx < fulfilled_obligation_idx, (
        "artifact must be fulfilled before obligation completes"
    )


def test_obligation_chain_with_terminal_failure_triggers_saga(isolated_state):
    """Inverse case: terminal failure in a chain triggers saga compensation
    on the fulfilled ancestor. Catches the seam where parent_obligation_id
    is set but saga doesn't actually walk the chain.
    """
    # Build a 2-step chain.
    m1 = send_agent_message(
        from_role="research_director", to_role="debate_runner",
        kind="request", subject="step 1 of 2", body="...",
    )
    update_obligation_state(role_id="debate_runner", message_id=m1.message_id,
                            new_state="accepted", actor="debate_runner")
    update_obligation_state(role_id="debate_runner", message_id=m1.message_id,
                            new_state="in_progress", actor="debate_runner")
    update_obligation_state(role_id="debate_runner", message_id=m1.message_id,
                            new_state="fulfilled", actor="debate_runner",
                            note="step 1 produced side effects (e.g., wrote to seam)")

    # Step 2 fails terminally.
    m2 = send_agent_message(
        from_role="debate_runner", to_role="research_director",
        kind="request", subject="step 2 of 2", body="...",
        parent_obligation_id=m1.message_id,
    )
    update_obligation_state(role_id="research_director", message_id=m2.message_id,
                            new_state="refused", actor="research_director",
                            note="cannot proceed without principal review")

    # Saga compensation should walk the parent chain and emit one
    # compensation request for m1 (the fulfilled ancestor).
    compensations = compensate_failed_obligation(
        role_id="research_director", message_id=m2.message_id,
        reason="step 2 refused; rolling back step 1 side effects",
    )
    assert len(compensations) == 1
    assert compensations[0].to_role == "debate_runner"
    assert compensations[0].parent_obligation_id == m2.message_id

    # And the active-saga list now reflects this.
    active = list_active_sagas()
    assert len(active) == 1
    assert active[0]["saga_root_failure"] == m2.message_id


def test_predicate_hash_drift_blocks_downstream(isolated_state):
    """Seam between mandate revision and downstream consumers: if a producer
    changes its predicate text, the predicate_hash changes; any consumer
    still referencing the OLD hash gets blocked. This catches the
    silent-stale-success failure mode the artifact-dependency primitive
    is designed to prevent."""
    log_path = isolated_state / "transitions.jsonl"
    old_predicate = "score >= 0.5"
    new_predicate = "score >= 0.7 AND fresh"

    # Producer fulfills with the NEW predicate
    fulfill_artifact(
        role_id="producer", task_id="t1",
        artifact_key="A", artifact_path="x", sha256="abc",
        predicate=new_predicate,
        predicate_eval={"score_ge_0_7": True, "fresh": True},
        log_path=log_path,
    )

    # Consumer A is up-to-date (new predicate hash) — should pass
    new_awaits = [{"artifact_key": "A", "predicate_hash": predicate_hash(new_predicate)}]
    ok_new, _ = is_awaits_satisfied(new_awaits, log_path=log_path)
    assert ok_new is True, "fresh consumer should be satisfied"

    # Consumer B is stale (old predicate hash) — should be blocked
    old_awaits = [{"artifact_key": "A", "predicate_hash": predicate_hash(old_predicate)}]
    ok_old, missing = is_awaits_satisfied(old_awaits, log_path=log_path)
    assert ok_old is False, "stale-predicate consumer should NOT match new fulfillment"
    assert missing  # non-empty missing list

    # Confirm: the two predicates produce different hashes (sanity)
    assert predicate_hash(old_predicate) != predicate_hash(new_predicate)
