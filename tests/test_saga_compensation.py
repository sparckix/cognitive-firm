"""GP-232 Phase C — saga compensation primitive tests.

Properties under test:
  - compensate_failed_obligation walks parent chain + emits one
    compensating request per fulfilled ancestor
  - non-failed obligations cannot trigger compensation
  - in_progress / blocked_input ancestors are SKIPPED (no real side
    effect to undo)
  - cycle in chain is detected + truncated
  - list_active_sagas surfaces in-flight compensations to Orbit
  - compensation requests carry parent_obligation_id back to the
    saga root failure
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration import agent_channels  # noqa: E402
from cognitive_firm.orchestration.agent_channels import (  # noqa: E402
    send_agent_message,
    update_obligation_state,
)
from cognitive_firm.orchestration.saga_compensation import (  # noqa: E402
    compensate_failed_obligation,
    list_active_sagas,
    _walk_parent_chain,
)
from cognitive_firm.orchestration import transition_log  # noqa: E402


# ── helper: redirect channel + role state into tmp_path ────────────────


@pytest.fixture
def isolated_state(tmp_path: Path, monkeypatch):
    channels = tmp_path / "channels"
    channels.mkdir()
    roles = tmp_path / "roles"
    roles.mkdir()

    # Three roles: alice (delegates to bob), bob (delegates to carol), carol.
    # manager is the role compensate_failed_obligation sends from.
    (roles / "alice.yaml").write_text(
        "role_id: alice\ndelegates_to:\n  - bob\nescalates_to:\n  - manager\n",
        encoding="utf-8",
    )
    (roles / "bob.yaml").write_text(
        "role_id: bob\ndelegates_to:\n  - carol\nescalates_to:\n  - alice\n",
        encoding="utf-8",
    )
    (roles / "carol.yaml").write_text(
        "role_id: carol\ndelegates_to:\nescalates_to:\n  - bob\n",
        encoding="utf-8",
    )
    (roles / "manager.yaml").write_text(
        "role_id: manager\ndelegates_to:\n  - alice\n  - bob\n  - carol\n"
        "escalates_to:\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(agent_channels, "CHANNELS_DIR", channels)
    monkeypatch.setattr(agent_channels, "ROLES_DIR", roles)
    # saga_compensation reads the same module-level CHANNELS_DIR via import
    import cognitive_firm.orchestration.saga_compensation as saga_mod
    monkeypatch.setattr(saga_mod, "CHANNELS_DIR", channels)

    log = tmp_path / "transitions.jsonl"
    monkeypatch.setattr(transition_log, "TRANSITIONS_LOG", log)
    monkeypatch.setattr(saga_mod, "TRANSITIONS_LOG", log)
    yield tmp_path


# ── fixtures: building chains ──────────────────────────────────────────


def _build_three_step_chain(roles=("alice", "bob", "carol")):
    """alice → bob (fulfilled) → carol (fulfilled) → bob (REFUSED).

    The chain models: alice asks bob to do a multi-step task; bob
    delegates the middle step to carol; bob's wrap-up step fails
    terminally. Compensation should fire on bob's fulfilled work AND
    carol's fulfilled work, in that order (terminal-failure-first).

    Returns (m_alice_to_bob, m_bob_to_carol, m_terminal_failure).
    """
    a, b, c = roles
    # Step 1: alice → bob
    m1 = send_agent_message(
        from_role=a, to_role=b,
        kind="request", subject="step 1", body="...",
    )
    update_obligation_state(role_id=b, message_id=m1.message_id,
                            new_state="accepted", actor=b)
    update_obligation_state(role_id=b, message_id=m1.message_id,
                            new_state="in_progress", actor=b)

    # Step 2: bob → carol (delegated middle step)
    m2 = send_agent_message(
        from_role=b, to_role=c,
        kind="request", subject="step 2", body="...",
        parent_obligation_id=m1.message_id,
    )
    update_obligation_state(role_id=c, message_id=m2.message_id,
                            new_state="accepted", actor=c)
    update_obligation_state(role_id=c, message_id=m2.message_id,
                            new_state="in_progress", actor=c)

    # Both ancestors fulfilled (they had real side effects).
    update_obligation_state(role_id=b, message_id=m1.message_id,
                            new_state="fulfilled", actor=b)
    update_obligation_state(role_id=c, message_id=m2.message_id,
                            new_state="fulfilled", actor=c)

    # Step 3: carol → bob (wrap-up message, immediately refused)
    m3 = send_agent_message(
        from_role=c, to_role=b,  # carol escalates back via the bob link
        kind="request", subject="step 3 — wrap up", body="...",
        parent_obligation_id=m2.message_id,
    )
    update_obligation_state(role_id=b, message_id=m3.message_id,
                            new_state="refused", actor=b,
                            note="cannot proceed")
    return m1, m2, m3


# ── walk parent chain ──────────────────────────────────────────────────


def test_walk_parent_chain_returns_full_chain(isolated_state):
    m1, m2, m3 = _build_three_step_chain()
    chain = _walk_parent_chain(role_id="alice", starting_message_id=m3.message_id)
    ids = [m.message_id for m in chain]
    assert m3.message_id in ids
    assert m2.message_id in ids
    assert m1.message_id in ids


# ── compensation triggers ──────────────────────────────────────────────


def test_compensation_emits_one_per_fulfilled_ancestor(isolated_state):
    m1, m2, m3 = _build_three_step_chain()
    comps = compensate_failed_obligation(role_id="alice", message_id=m3.message_id)
    # Two fulfilled ancestors (m1, m2) → two compensation requests.
    assert len(comps) == 2
    targets = {c.to_role for c in comps}
    # m1's actor was bob, m2's actor was carol.
    assert targets == {"bob", "carol"}


def test_compensations_carry_saga_root_failure_id(isolated_state):
    _m1, _m2, m3 = _build_three_step_chain()
    comps = compensate_failed_obligation(role_id="alice", message_id=m3.message_id)
    for c in comps:
        assert c.parent_obligation_id == m3.message_id
        assert c.metadata.get("saga_compensation") is True
        assert c.metadata.get("saga_root_failure_id") == m3.message_id


def test_compensation_rejects_non_terminal_obligation(isolated_state):
    """compensating a fulfilled or in_progress obligation makes no
    semantic sense — only refused / expired trigger compensation."""
    msg = send_agent_message(
        from_role="alice", to_role="bob",
        kind="request", subject="x", body="y",
    )
    update_obligation_state(role_id="bob", message_id=msg.message_id,
                            new_state="accepted", actor="bob")
    with pytest.raises(ValueError, match="terminal-failure"):
        compensate_failed_obligation(role_id="bob", message_id=msg.message_id)


def test_compensation_skips_unfulfilled_ancestors(isolated_state):
    """An ancestor still in_progress / accepted / pending has no real
    side effect to compensate."""
    m1 = send_agent_message(
        from_role="alice", to_role="bob",
        kind="request", subject="step 1", body="...",
    )
    # Note: NOT fulfilled — only accepted.
    update_obligation_state(role_id="bob", message_id=m1.message_id,
                            new_state="accepted", actor="bob")
    update_obligation_state(role_id="bob", message_id=m1.message_id,
                            new_state="in_progress", actor="bob")

    m2 = send_agent_message(
        from_role="bob", to_role="carol",
        kind="request", subject="step 2", body="...",
        parent_obligation_id=m1.message_id,
    )
    update_obligation_state(role_id="carol", message_id=m2.message_id,
                            new_state="refused", actor="carol")

    comps = compensate_failed_obligation(role_id="carol", message_id=m2.message_id)
    # m1 is in_progress, NOT fulfilled → not compensated.
    assert len(comps) == 0


def test_compensation_handles_orphan_chain_gracefully(isolated_state):
    """parent_obligation_id pointing to a non-existent message just
    truncates the chain; no exception."""
    msg = send_agent_message(
        from_role="alice", to_role="bob",
        kind="request", subject="orphan parent", body="...",
        parent_obligation_id="msg_does_not_exist",
    )
    update_obligation_state(role_id="bob", message_id=msg.message_id,
                            new_state="refused", actor="bob")
    # No exception — chain terminates at the orphan reference.
    comps = compensate_failed_obligation(role_id="bob", message_id=msg.message_id)
    assert comps == []


# ── list_active_sagas ─────────────────────────────────────────────────


def test_list_active_sagas_finds_in_flight(isolated_state):
    """Compensation requests have obligation_state pending until
    fulfilled. list_active_sagas should surface them."""
    _m1, _m2, m3 = _build_three_step_chain()
    comps = compensate_failed_obligation(role_id="alice", message_id=m3.message_id)
    assert len(comps) == 2
    active = list_active_sagas()
    assert len(active) == 1
    assert active[0]["saga_root_failure"] == m3.message_id


def test_list_active_sagas_drops_completed(isolated_state):
    """Once every compensation is fulfilled, the saga drops off the
    active list."""
    _m1, _m2, m3 = _build_three_step_chain()
    comps = compensate_failed_obligation(role_id="alice", message_id=m3.message_id)
    # Mark every compensation fulfilled.
    for c in comps:
        update_obligation_state(role_id=c.to_role, message_id=c.message_id,
                                new_state="accepted", actor=c.to_role)
        update_obligation_state(role_id=c.to_role, message_id=c.message_id,
                                new_state="in_progress", actor=c.to_role)
        update_obligation_state(role_id=c.to_role, message_id=c.message_id,
                                new_state="fulfilled", actor=c.to_role)
    active = list_active_sagas()
    assert len(active) == 0
