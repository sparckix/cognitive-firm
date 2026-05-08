"""GP-232 Phase A — obligation lifecycle on AgentMessage.

The lifecycle is distinct from the envelope's `status` field:
  - status      = "open" | "acknowledged" | "closed"   (was the message read?)
  - obligation  = "pending" | "accepted" | ...         (was the work done?)

A request can be acknowledged (envelope read) while the obligation is still
pending (work not yet accepted). The two are orthogonal axes that the panel
audit said the kernel was conflating.

Tests cover:
  - default state: request/proposal/handoff start at obligation=pending; other
    kinds carry no obligation
  - state-machine validator accepts legal transitions, rejects illegal
  - update_obligation_state mutates the message + emits a transition row
  - list_blocked_obligations finds the blocked_input messages
  - parent_obligation_id chain (saga prerequisite)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration import agent_channels  # noqa: E402
from cognitive_firm.orchestration.agent_channels import (  # noqa: E402
    AgentMessage,
    ObligationState,
    list_blocked_obligations,
    send_agent_message,
    update_obligation_state,
    validate_obligation_transition,
)
from cognitive_firm.orchestration.transition_log import append_transition  # noqa: E402,F401


# ── helper: redirect channel + role state into tmp_path ────────────────


@pytest.fixture
def isolated_channels(tmp_path: Path, monkeypatch):
    """Point the channel root at a tmp dir + register two roles by faking
    role yaml files that the channel_allowed policy can read."""
    channels = tmp_path / "channels"
    channels.mkdir()
    roles = tmp_path / "roles"
    roles.mkdir()

    # Minimal role yaml so channel_allowed sees the roles + their links.
    # Note: _extract_yaml_list parses block-style only, not inline lists.
    (roles / "alice.yaml").write_text(
        "role_id: alice\ndelegates_to:\n  - bob\nescalates_to:\n",
        encoding="utf-8",
    )
    (roles / "bob.yaml").write_text(
        "role_id: bob\ndelegates_to:\nescalates_to:\n  - alice\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(agent_channels, "CHANNELS_DIR", channels)
    monkeypatch.setattr(agent_channels, "ROLES_DIR", roles)
    yield tmp_path


# ── validator unit tests ───────────────────────────────────────────────


def test_validator_accepts_legal_transitions():
    legal = [
        ("pending", "accepted"),
        ("pending", "refused"),
        ("pending", "expired"),
        ("accepted", "in_progress"),
        ("accepted", "refused"),
        ("in_progress", "blocked_input"),
        ("in_progress", "fulfilled"),
        ("blocked_input", "in_progress"),
        ("blocked_input", "refused"),
    ]
    for f, t in legal:
        ok, _ = validate_obligation_transition(f, t)
        assert ok, f"legal transition {f} -> {t} rejected"


def test_validator_rejects_terminal_transitions():
    """fulfilled / refused / expired are terminal — no outgoing transitions."""
    for terminal in ("fulfilled", "refused", "expired"):
        for target in ("pending", "in_progress", "fulfilled"):
            ok, reason = validate_obligation_transition(terminal, target)
            assert not ok
            assert "terminal" in reason


def test_validator_rejects_illegal_skip_states():
    """pending cannot jump straight to fulfilled — must pass accepted +
    in_progress first. This is what catches "agent claimed done without
    doing the work" cases."""
    ok, reason = validate_obligation_transition("pending", "fulfilled")
    assert not ok
    assert "illegal" in reason


def test_validator_rejects_unknown_states():
    ok, reason = validate_obligation_transition("nonsense", "pending")
    assert not ok
    assert "unknown" in reason
    ok, reason = validate_obligation_transition("pending", "nonsense")
    assert not ok
    assert "unknown" in reason


# ── default obligation state on send ───────────────────────────────────


def test_request_starts_at_pending(isolated_channels):
    msg = send_agent_message(
        from_role="alice", to_role="bob",
        kind="request", subject="please do X", body="x details",
    )
    assert msg.obligation_state == "pending"
    assert msg.parent_obligation_id is None


def test_handoff_starts_at_pending(isolated_channels):
    msg = send_agent_message(
        from_role="alice", to_role="bob",
        kind="handoff", subject="taking over", body="state details",
    )
    assert msg.obligation_state == "pending"


def test_proposal_starts_at_pending(isolated_channels):
    msg = send_agent_message(
        from_role="alice", to_role="bob",
        kind="proposal", subject="suggesting Y", body="rationale",
    )
    assert msg.obligation_state == "pending"


def test_inform_carries_no_obligation(isolated_channels):
    msg = send_agent_message(
        from_role="alice", to_role="bob",
        kind="inform", subject="fyi", body="info",
    )
    assert msg.obligation_state is None


def test_status_carries_no_obligation(isolated_channels):
    msg = send_agent_message(
        from_role="alice", to_role="bob",
        kind="status", subject="progress update", body="50%",
    )
    assert msg.obligation_state is None


# ── update_obligation_state ───────────────────────────────────────────


def test_update_to_accepted(isolated_channels):
    msg = send_agent_message(
        from_role="alice", to_role="bob",
        kind="request", subject="do X", body="x",
    )
    updated = update_obligation_state(
        role_id="bob", message_id=msg.message_id,
        new_state="accepted", actor="bob", note="will do",
    )
    assert updated.obligation_state == "accepted"


def test_full_happy_path_lifecycle(isolated_channels):
    msg = send_agent_message(
        from_role="alice", to_role="bob",
        kind="request", subject="do X", body="x",
    )
    update_obligation_state(role_id="bob", message_id=msg.message_id,
                            new_state="accepted", actor="bob")
    update_obligation_state(role_id="bob", message_id=msg.message_id,
                            new_state="in_progress", actor="bob")
    update_obligation_state(role_id="bob", message_id=msg.message_id,
                            new_state="blocked_input", actor="bob",
                            note="need clarification on Y")
    update_obligation_state(role_id="bob", message_id=msg.message_id,
                            new_state="in_progress", actor="bob",
                            note="resumed after clarification")
    final = update_obligation_state(role_id="bob", message_id=msg.message_id,
                                    new_state="fulfilled", actor="bob")
    assert final.obligation_state == "fulfilled"


def test_update_rejects_illegal_skip(isolated_channels):
    msg = send_agent_message(
        from_role="alice", to_role="bob",
        kind="request", subject="do X", body="x",
    )
    with pytest.raises(ValueError, match="illegal transition"):
        update_obligation_state(
            role_id="bob", message_id=msg.message_id,
            new_state="fulfilled", actor="bob",
        )


def test_update_rejects_terminal_transition(isolated_channels):
    msg = send_agent_message(
        from_role="alice", to_role="bob",
        kind="request", subject="do X", body="x",
    )
    update_obligation_state(role_id="bob", message_id=msg.message_id,
                            new_state="refused", actor="bob",
                            note="out of scope")
    with pytest.raises(ValueError, match="terminal"):
        update_obligation_state(
            role_id="bob", message_id=msg.message_id,
            new_state="pending", actor="bob",
        )


def test_update_on_no_obligation_message_rejects(isolated_channels):
    msg = send_agent_message(
        from_role="alice", to_role="bob",
        kind="inform", subject="fyi", body="info",
    )
    with pytest.raises(ValueError, match="no obligation_state"):
        update_obligation_state(
            role_id="bob", message_id=msg.message_id,
            new_state="accepted", actor="bob",
        )


# ── list_blocked_obligations ──────────────────────────────────────────


def test_list_blocked_obligations_finds_blocked(isolated_channels):
    """Ship a request, drive it to blocked_input, confirm it surfaces in
    the list. This is the load-bearing UX primitive — what Orbit + the
    manager daemon use to render "B is blocked on A" to the principal."""
    msg = send_agent_message(
        from_role="alice", to_role="bob",
        kind="request", subject="needs your input", body="...",
    )
    update_obligation_state(role_id="bob", message_id=msg.message_id,
                            new_state="accepted", actor="bob")
    update_obligation_state(role_id="bob", message_id=msg.message_id,
                            new_state="in_progress", actor="bob")
    update_obligation_state(role_id="bob", message_id=msg.message_id,
                            new_state="blocked_input", actor="bob",
                            note="awaiting principal review of Y")

    # Specific role
    blocked = list_blocked_obligations(role_id="bob")
    assert len(blocked) == 1
    assert blocked[0].message_id == msg.message_id
    assert blocked[0].subject == "needs your input"

    # All roles
    blocked_all = list_blocked_obligations()
    assert any(m.message_id == msg.message_id for m in blocked_all)


def test_list_blocked_excludes_non_blocked(isolated_channels):
    """A merely-acknowledged message (envelope read) is NOT blocked.
    This is the conflation the panel audit flagged."""
    msg_a = send_agent_message(
        from_role="alice", to_role="bob",
        kind="request", subject="A", body="a",
    )
    msg_b = send_agent_message(
        from_role="alice", to_role="bob",
        kind="inform", subject="B", body="b",  # no obligation
    )

    # Mark envelope status acknowledged for both, but obligation stays pending.
    from cognitive_firm.orchestration.agent_channels import update_agent_message_status
    update_agent_message_status(role_id="bob", message_id=msg_a.message_id,
                                status="acknowledged", actor="bob")
    update_agent_message_status(role_id="bob", message_id=msg_b.message_id,
                                status="acknowledged", actor="bob")

    blocked = list_blocked_obligations(role_id="bob")
    assert len(blocked) == 0  # neither is blocked_input


# ── parent_obligation_id (saga chain primitive) ───────────────────────


def test_parent_obligation_id_carries_through(isolated_channels):
    """Sagas need a chain. Phase A ships the field; Phase C ships the
    rollback resolver."""
    parent = send_agent_message(
        from_role="alice", to_role="bob",
        kind="request", subject="parent task", body="...",
    )
    child = send_agent_message(
        from_role="bob", to_role="alice",
        kind="handoff", subject="sub-task", body="...",
        parent_obligation_id=parent.message_id,
    )
    assert child.parent_obligation_id == parent.message_id


# ── transition log emission ───────────────────────────────────────────


def test_obligation_state_change_emits_transition(isolated_channels, tmp_path, monkeypatch):
    """Every obligation state change must record a row in transitions.jsonl
    with event=agent.obligation.<state> so the audit trail captures the
    work-state evolution."""
    log_path = tmp_path / "transitions.jsonl"
    monkeypatch.setattr(
        "cognitive_firm.orchestration.transition_log.TRANSITIONS_LOG", log_path
    )
    # The send_agent_message call uses the default TRANSITIONS_LOG via the
    # transition_log module reference; its call site reads the current
    # module-level value, so the monkeypatch above is sufficient.
    import cognitive_firm.orchestration.agent_channels as ach
    monkeypatch.setattr(ach, "append_transition",
                        lambda **kw: append_log_to_path(kw, log_path))

    msg = send_agent_message(
        from_role="alice", to_role="bob",
        kind="request", subject="x", body="y",
    )
    update_obligation_state(role_id="bob", message_id=msg.message_id,
                            new_state="accepted", actor="bob",
                            note="ack")
    rows = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
    obligation_rows = [r for r in rows if r.get("event", "").startswith("agent.obligation.")]
    assert any(r["event"] == "agent.obligation.accepted" for r in obligation_rows)


def append_log_to_path(kwargs, log_path):
    """Test-side helper that mimics append_transition writing to a custom
    path (the production fn writes to TRANSITIONS_LOG which we cannot
    redirect via monkeypatch on the called module without import gymnastics).
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    record = {"event": kwargs.get("event"), **kwargs.get("payload", {})}
    with log_path.open("a") as fh:
        fh.write(json.dumps(record) + "\n")
    return record
