from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.kernel_events import list_kernel_events  # noqa: E402
from cognitive_firm.orchestration.resource_allocation import (  # noqa: E402
    RESERVE_POOL,
    allocation_summary,
    apply_allocation_decision,
    current_allocation,
    get_allocation_decision,
    list_allocation_decisions,
    record_allocation_decision,
    require_allocation_decision,
    revert_allocation_decision,
)


class _Logs:
    """Bundle of temp log paths for one isolated allocation world."""

    def __init__(self, tmp_path: Path):
        self.alloc = tmp_path / "allocation_decisions.jsonl"
        self.events = tmp_path / "kernel_events.jsonl"


@pytest.fixture()
def logs(tmp_path: Path) -> _Logs:
    return _Logs(tmp_path)


def _record(logs: _Logs, **overrides):
    base = dict(
        resource_kind="worker_capacity",
        from_unit=RESERVE_POOL,
        to_unit="triage_lane",
        amount=10.0,
        deciding_role="role.general_office",
        deciding_actor="actor.coo",
        authority_basis="mandate:capital_allocation",
        rationale="triage lane is the throughput bottleneck this quarter",
        log_path=logs.alloc,
        kernel_events_log=logs.events,
    )
    base.update(overrides)
    return record_allocation_decision(**base)


def test_record_starts_proposed_and_does_not_move_the_ledger(logs: _Logs):
    decision = _record(logs)
    assert decision.status == "proposed"
    assert decision.decision_id.startswith("alloc_")
    # Proposed decisions are not ledger-affecting.
    assert current_allocation("worker_capacity", log_path=logs.alloc) == {}


def test_apply_moves_the_ledger(logs: _Logs):
    decision = _record(logs)
    applied = apply_allocation_decision(
        decision.decision_id, actor="actor.coo", log_path=logs.alloc,
        kernel_events_log=logs.events,
    )
    assert applied.status == "applied"
    assert applied.applied_at_utc is not None

    ledger = current_allocation("worker_capacity", log_path=logs.alloc)
    assert ledger["triage_lane"] == 10.0
    assert ledger[RESERVE_POOL] == -10.0


def test_current_allocation_math_across_several_applied_decisions(logs: _Logs):
    # Reserve -> triage 10, Reserve -> proof 4, triage -> proof 3.
    d1 = _record(logs, to_unit="triage_lane", amount=10.0)
    d2 = _record(logs, to_unit="proof_mill", amount=4.0)
    d3 = _record(logs, from_unit="triage_lane", to_unit="proof_mill", amount=3.0)
    for d in (d1, d2, d3):
        apply_allocation_decision(
            d.decision_id, actor="actor.coo", log_path=logs.alloc,
            kernel_events_log=logs.events,
        )

    ledger = current_allocation("worker_capacity", log_path=logs.alloc)
    assert ledger["triage_lane"] == 7.0      # +10 -3
    assert ledger["proof_mill"] == 7.0       # +4 +3
    assert ledger[RESERVE_POOL] == -14.0     # -10 -4
    # The ledger is conservative: net of all positions is zero.
    assert round(sum(ledger.values()), 9) == 0.0


def test_decisions_for_other_resource_kinds_are_isolated(logs: _Logs):
    apply_allocation_decision(
        _record(logs, resource_kind="worker_capacity", amount=10.0).decision_id,
        actor="actor.coo", log_path=logs.alloc, kernel_events_log=logs.events,
    )
    apply_allocation_decision(
        _record(logs, resource_kind="budget_usd", amount=500.0).decision_id,
        actor="actor.coo", log_path=logs.alloc, kernel_events_log=logs.events,
    )
    assert current_allocation("worker_capacity", log_path=logs.alloc)["triage_lane"] == 10.0
    assert current_allocation("budget_usd", log_path=logs.alloc)["triage_lane"] == 500.0


def test_revert_removes_the_decision_from_the_ledger(logs: _Logs):
    decision = _record(logs)
    apply_allocation_decision(
        decision.decision_id, actor="actor.coo", log_path=logs.alloc,
        kernel_events_log=logs.events,
    )
    assert current_allocation("worker_capacity", log_path=logs.alloc)["triage_lane"] == 10.0

    reverted = revert_allocation_decision(
        decision.decision_id,
        actor="actor.cfo",
        reason="quarter closed; capacity returns to reserve",
        log_path=logs.alloc,
        kernel_events_log=logs.events,
    )
    assert reverted.status == "reverted"
    assert reverted.reverted_reason
    # A reverted decision no longer contributes to the ledger.
    assert current_allocation("worker_capacity", log_path=logs.alloc) == {}


def test_illegal_transitions_are_rejected(logs: _Logs):
    decision = _record(logs)

    # Cannot revert a decision that was never applied.
    with pytest.raises(ValueError, match="not applied"):
        revert_allocation_decision(
            decision.decision_id, actor="actor.cfo", reason="x",
            log_path=logs.alloc, kernel_events_log=logs.events,
        )

    apply_allocation_decision(
        decision.decision_id, actor="actor.coo", log_path=logs.alloc,
        kernel_events_log=logs.events,
    )
    # Cannot apply an already-applied decision.
    with pytest.raises(ValueError, match="not proposed"):
        apply_allocation_decision(
            decision.decision_id, actor="actor.coo", log_path=logs.alloc,
            kernel_events_log=logs.events,
        )

    revert_allocation_decision(
        decision.decision_id, actor="actor.cfo", reason="done",
        log_path=logs.alloc, kernel_events_log=logs.events,
    )
    # Cannot re-revert.
    with pytest.raises(ValueError, match="not applied"):
        revert_allocation_decision(
            decision.decision_id, actor="actor.cfo", reason="again",
            log_path=logs.alloc, kernel_events_log=logs.events,
        )


def test_missing_decision_raises(logs: _Logs):
    with pytest.raises(KeyError):
        apply_allocation_decision("alloc_missing", actor="actor.coo", log_path=logs.alloc)
    with pytest.raises(KeyError):
        require_allocation_decision("alloc_missing", log_path=logs.alloc)
    assert get_allocation_decision("alloc_missing", log_path=logs.alloc) is None


def test_from_equals_to_is_rejected(logs: _Logs):
    with pytest.raises(ValueError, match="must differ"):
        _record(logs, from_unit="triage_lane", to_unit="triage_lane")


def test_non_positive_amount_is_rejected(logs: _Logs):
    with pytest.raises(ValueError, match="amount must be positive"):
        _record(logs, amount=0.0)
    with pytest.raises(ValueError, match="amount must be positive"):
        _record(logs, amount=-5.0)


def test_required_governance_fields_are_validated(logs: _Logs):
    with pytest.raises(ValueError, match="authority_basis"):
        _record(logs, authority_basis="  ")
    with pytest.raises(ValueError, match="rationale"):
        _record(logs, rationale="")


def test_effective_window_must_be_ordered(logs: _Logs):
    with pytest.raises(ValueError, match="effective_until_utc"):
        _record(
            logs,
            effective_from_utc="2026-05-21T12:00:00+00:00",
            effective_until_utc="2026-05-20T12:00:00+00:00",
        )


def test_list_filters_by_resource_kind_unit_and_status(logs: _Logs):
    a = _record(logs, resource_kind="worker_capacity", to_unit="triage_lane")
    _record(logs, resource_kind="budget_usd", to_unit="proof_mill")
    apply_allocation_decision(
        a.decision_id, actor="actor.coo", log_path=logs.alloc,
        kernel_events_log=logs.events,
    )

    by_kind = list_allocation_decisions(resource_kind="worker_capacity", log_path=logs.alloc)
    assert [d.resource_kind for d in by_kind] == ["worker_capacity"]

    # unit filter matches either endpoint.
    by_unit = list_allocation_decisions(unit_id="triage_lane", log_path=logs.alloc)
    assert {d.decision_id for d in by_unit} == {a.decision_id}

    by_reserve = list_allocation_decisions(unit_id=RESERVE_POOL, log_path=logs.alloc)
    assert len(by_reserve) == 2

    applied = list_allocation_decisions(status="applied", log_path=logs.alloc)
    assert [d.decision_id for d in applied] == [a.decision_id]

    with pytest.raises(ValueError, match="invalid status"):
        list_allocation_decisions(status="bogus", log_path=logs.alloc)


def test_allocation_summary_reports_ledger_and_status_counts(logs: _Logs):
    d1 = _record(logs, to_unit="triage_lane", amount=10.0)
    d2 = _record(logs, to_unit="proof_mill", amount=4.0)
    _record(logs, to_unit="proof_mill", amount=99.0)  # stays proposed
    apply_allocation_decision(
        d1.decision_id, actor="actor.coo", log_path=logs.alloc,
        kernel_events_log=logs.events,
    )
    apply_allocation_decision(
        d2.decision_id, actor="actor.coo", log_path=logs.alloc,
        kernel_events_log=logs.events,
    )

    summary = allocation_summary("worker_capacity", log_path=logs.alloc)
    assert summary["resource_kind"] == "worker_capacity"
    assert summary["decision_count"] == 3
    assert summary["decisions_by_status"] == {"applied": 2, "proposed": 1, "reverted": 0}
    # The reserve sentinel is excluded from the per-unit ledger view.
    assert summary["ledger"] == {"proof_mill": 4.0, "triage_lane": 10.0}
    assert summary["reserve_pool_net"] == -14.0
    assert summary["allocated_to_units"] == 14.0


def test_every_transition_emits_a_kernel_event(logs: _Logs):
    decision = _record(logs)
    apply_allocation_decision(
        decision.decision_id, actor="actor.coo", log_path=logs.alloc,
        kernel_events_log=logs.events,
    )
    revert_allocation_decision(
        decision.decision_id, actor="actor.cfo", reason="closed",
        log_path=logs.alloc, kernel_events_log=logs.events,
    )

    verbs = [
        event.verb
        for event in list_kernel_events(
            object_ref=f"allocation_decision:{decision.decision_id}",
            log_path=logs.events,
        )
    ]
    assert verbs == [
        "allocation_decision.proposed",
        "allocation_decision.applied",
        "allocation_decision.reverted",
    ]


def test_outcome_links_and_change_refs_are_carried(logs: _Logs):
    decision = _record(
        logs,
        outcome_link_ids=["outcome_1", "outcome_1", "outcome_2"],
        change_refs=["change_7"],
    )
    # Refs are deduplicated and preserved.
    assert decision.outcome_link_ids == ["outcome_1", "outcome_2"]
    assert decision.change_refs == ["change_7"]
    stored = require_allocation_decision(decision.decision_id, log_path=logs.alloc)
    assert stored.outcome_link_ids == ["outcome_1", "outcome_2"]
