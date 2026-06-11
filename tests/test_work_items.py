from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration import work_items as work_items_module  # noqa: E402
from cognitive_firm.orchestration.kernel_events import list_kernel_events  # noqa: E402
from cognitive_firm.orchestration.operating_units import (  # noqa: E402
    define_operating_unit,
    set_operating_unit_status,
)
from cognitive_firm.orchestration.resource_envelope import validate_resource  # noqa: E402
from cognitive_firm.orchestration.work_items import (  # noqa: E402
    claim_next_work_item,
    claim_work_item,
    complete_work_item,
    enqueue_work_item,
    fail_work_item,
    heartbeat_work_item,
    list_dead_letters,
    list_work_items,
    main as work_items_main,
    requeue_dead_letter,
    retire_work_item,
    work_item_resource,
)


class _Logs:
    """Bundle of temp log paths for one isolated work-item world."""

    def __init__(self, tmp_path: Path):
        self.units = tmp_path / "operating_units.jsonl"
        self.work = tmp_path / "work_items.jsonl"
        self.events = tmp_path / "kernel_events.jsonl"


@pytest.fixture()
def logs(tmp_path: Path) -> _Logs:
    bundle = _Logs(tmp_path)
    define_operating_unit(
        unit_id="residual_compiler",
        unit_kind="transformation_lane",
        display_name="Residual Compiler",
        owner_role="role.residual_compiler_manager",
        allowed_work_kinds=["compile", "probe"],
        allowed_exits=["exact_gap", "tested_hold"],
        worker_roles=["role.proof_execution_worker"],
        governance_required_for=["exact_gap"],
        log_path=bundle.units,
    )
    return bundle


def _enqueue(logs: _Logs, **overrides):
    base = dict(
        unit_id="residual_compiler",
        kind="compile",
        log_path=logs.work,
        operating_units_log=logs.units,
        kernel_events_log=logs.events,
    )
    base.update(overrides)
    return enqueue_work_item(**base)


def _claim(logs: _Logs, **overrides):
    base = dict(
        unit_id="residual_compiler",
        actor="actor.worker_1",
        role_id="role.proof_execution_worker",
        log_path=logs.work,
        operating_units_log=logs.units,
        kernel_events_log=logs.events,
    )
    base.update(overrides)
    return claim_next_work_item(**base)


def test_enqueue_is_idempotent_on_idempotency_key(logs: _Logs):
    first = _enqueue(logs, idempotency_key="source:123")
    second = _enqueue(logs, idempotency_key="source:123")

    assert first.work_id == second.work_id
    assert len(list_work_items(log_path=logs.work)) == 1


def test_enqueue_rejects_unknown_work_kind(logs: _Logs):
    with pytest.raises(ValueError, match="allowed_work_kinds"):
        _enqueue(logs, kind="not_a_real_kind")


def test_enqueue_rejects_inactive_unit(logs: _Logs):
    set_operating_unit_status("residual_compiler", "paused", log_path=logs.units)
    with pytest.raises(ValueError, match="not active"):
        _enqueue(logs)


def test_claim_next_respects_priority_then_age(logs: _Logs):
    low = _enqueue(logs, priority=0)
    high = _enqueue(logs, priority=10)

    claimed = _claim(logs)
    assert claimed is not None
    assert claimed.work_id == high.work_id, "higher priority must be claimed first"
    assert claimed.status == "claimed"
    assert claimed.attempts == 1
    assert claimed.claim_token == 1

    second = _claim(logs)
    assert second is not None and second.work_id == low.work_id


def test_unauthorized_worker_role_cannot_claim(logs: _Logs):
    _enqueue(logs)
    with pytest.raises(PermissionError, match="authorized worker"):
        _claim(logs, role_id="role.intruder")


def test_claim_next_returns_none_when_queue_empty(logs: _Logs):
    assert _claim(logs) is None


def test_complete_requires_a_bounded_exit(logs: _Logs):
    _enqueue(logs)
    claimed = _claim(logs)
    assert claimed is not None

    with pytest.raises(ValueError, match="allowed_exits"):
        complete_work_item(
            claimed.work_id,
            actor="actor.worker_1",
            claim_token=claimed.claim_token,
            exit_kind="made_up_exit",
            log_path=logs.work,
            operating_units_log=logs.units,
            kernel_events_log=logs.events,
        )

    done = complete_work_item(
        claimed.work_id,
        actor="actor.worker_1",
        claim_token=claimed.claim_token,
        exit_kind="exact_gap",
        producer="role.llm_proposer",
        verifier="role.canary_validator",
        artifact_refs=[{"kind": "canary_spec", "path": "specs/c1.json"}],
        log_path=logs.work,
        operating_units_log=logs.units,
        kernel_events_log=logs.events,
    )
    assert done.status == "done"
    assert done.exit_kind == "exact_gap"
    assert done.lease_until_utc is None


def test_complete_rejects_collapsed_producer_and_verifier(logs: _Logs):
    _enqueue(logs)
    claimed = _claim(logs)
    assert claimed is not None
    with pytest.raises(ValueError, match="producer and verifier"):
        complete_work_item(
            claimed.work_id,
            actor="actor.worker_1",
            claim_token=claimed.claim_token,
            exit_kind="tested_hold",
            producer="role.same",
            verifier="role.same",
            log_path=logs.work,
            operating_units_log=logs.units,
            kernel_events_log=logs.events,
        )


def test_stale_fencing_token_is_rejected(logs: _Logs):
    _enqueue(logs)
    claimed = _claim(logs)
    assert claimed is not None

    with pytest.raises(PermissionError, match="fencing token"):
        complete_work_item(
            claimed.work_id,
            actor="actor.worker_1",
            claim_token=claimed.claim_token + 1,
            exit_kind="tested_hold",
            log_path=logs.work,
            operating_units_log=logs.units,
            kernel_events_log=logs.events,
        )


def test_expired_claim_is_reclaimable_and_old_holder_is_fenced(logs: _Logs, monkeypatch):
    item = _enqueue(logs)
    base = datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc)
    clock = {"now": base}
    monkeypatch.setattr(work_items_module, "_now", lambda: clock["now"])

    first = claim_work_item(
        item.work_id,
        actor="actor.worker_1",
        role_id="role.proof_execution_worker",
        lease_seconds=60,
        log_path=logs.work,
        operating_units_log=logs.units,
        kernel_events_log=logs.events,
    )

    # Advance past the lease: the claim is now stale and reclaimable.
    clock["now"] = base + timedelta(seconds=120)
    second = claim_work_item(
        first.work_id,
        actor="actor.worker_2",
        role_id="role.proof_execution_worker",
        lease_seconds=60,
        log_path=logs.work,
        operating_units_log=logs.units,
        kernel_events_log=logs.events,
    )
    assert second.claimed_by_actor == "actor.worker_2"
    assert second.claim_token == first.claim_token + 1
    assert second.attempts == 2

    # The original holder can no longer complete the work.
    with pytest.raises(PermissionError):
        complete_work_item(
            first.work_id,
            actor="actor.worker_1",
            claim_token=first.claim_token,
            exit_kind="tested_hold",
            log_path=logs.work,
            operating_units_log=logs.units,
            kernel_events_log=logs.events,
        )


def test_heartbeat_extends_the_lease(logs: _Logs, monkeypatch):
    _enqueue(logs)
    base = datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc)
    clock = {"now": base}
    monkeypatch.setattr(work_items_module, "_now", lambda: clock["now"])

    claimed = _claim(logs)
    assert claimed is not None
    first_lease = claimed.lease_until_utc

    clock["now"] = base + timedelta(seconds=30)
    beat = heartbeat_work_item(
        claimed.work_id,
        actor="actor.worker_1",
        claim_token=claimed.claim_token,
        lease_seconds=300,
        log_path=logs.work,
        kernel_events_log=logs.events,
    )
    assert beat.lease_until_utc is not None and beat.lease_until_utc > (first_lease or "")


def test_retryable_failure_requeues_then_dead_letters(logs: _Logs):
    item = _enqueue(logs, max_attempts=2)

    # Attempt 1: claim then fail retryably -> back to the queue.
    first = _claim(logs)
    assert first is not None
    after_first = fail_work_item(
        first.work_id,
        actor="actor.worker_1",
        claim_token=first.claim_token,
        reason="transient compile error",
        log_path=logs.work,
        kernel_events_log=logs.events,
    )
    assert after_first.status == "queued"
    assert after_first.attempts == 1

    # Attempt 2: claim then fail again -> attempts exhausted -> dead letter.
    second = _claim(logs)
    assert second is not None
    after_second = fail_work_item(
        second.work_id,
        actor="actor.worker_1",
        claim_token=second.claim_token,
        reason="transient compile error again",
        log_path=logs.work,
        kernel_events_log=logs.events,
    )
    assert after_second.status == "dead_letter"
    assert after_second.dead_letter_reason
    assert [d.work_id for d in list_dead_letters(log_path=logs.work)] == [item.work_id]


def test_non_retryable_failure_goes_straight_to_failed(logs: _Logs):
    _enqueue(logs)
    claimed = _claim(logs)
    assert claimed is not None
    failed = fail_work_item(
        claimed.work_id,
        actor="actor.worker_1",
        claim_token=claimed.claim_token,
        reason="payload schema is invalid",
        retryable=False,
        log_path=logs.work,
        kernel_events_log=logs.events,
    )
    assert failed.status == "failed"


def test_requeue_dead_letter_returns_work_to_the_queue(logs: _Logs):
    _enqueue(logs, max_attempts=1)
    claimed = _claim(logs)
    assert claimed is not None
    dead = fail_work_item(
        claimed.work_id,
        actor="actor.worker_1",
        claim_token=claimed.claim_token,
        reason="needs operator review",
        log_path=logs.work,
        kernel_events_log=logs.events,
    )
    assert dead.status == "dead_letter"

    requeued = requeue_dead_letter(
        dead.work_id,
        actor="actor.operator",
        log_path=logs.work,
        kernel_events_log=logs.events,
    )
    assert requeued.status == "queued"
    assert requeued.attempts == 0


def test_retire_stops_a_non_terminal_work_item(logs: _Logs):
    item = _enqueue(logs)
    retired = retire_work_item(
        item.work_id,
        actor="actor.operator",
        reason="no longer worth doing",
        log_path=logs.work,
        kernel_events_log=logs.events,
    )
    assert retired.status == "retired"
    with pytest.raises(ValueError, match="cannot retire"):
        retire_work_item(
            item.work_id,
            actor="actor.operator",
            reason="again",
            log_path=logs.work,
            kernel_events_log=logs.events,
        )


def test_every_transition_emits_a_kernel_event(logs: _Logs):
    item = _enqueue(logs)
    claimed = _claim(logs)
    assert claimed is not None
    complete_work_item(
        claimed.work_id,
        actor="actor.worker_1",
        claim_token=claimed.claim_token,
        exit_kind="tested_hold",
        log_path=logs.work,
        operating_units_log=logs.units,
        kernel_events_log=logs.events,
    )

    verbs = [
        event.verb
        for event in list_kernel_events(
            object_ref=f"work_item:{item.work_id}", log_path=logs.events
        )
    ]
    assert verbs == ["work_item.enqueued", "work_item.claimed", "work_item.completed"]


def test_work_item_projects_to_resource_envelope(logs: _Logs):
    item = _enqueue(
        logs,
        payload={"claim": "bounded"},
        metadata={"cognitive_run_id": "run_123"},
        tenant_id="tenant-a",
        project_id="project-a",
    )
    claimed = _claim(logs)
    assert claimed is not None
    done = complete_work_item(
        claimed.work_id,
        actor="actor.worker_1",
        claim_token=claimed.claim_token,
        exit_kind="tested_hold",
        producer="role.proof_execution_worker",
        verifier="role.reviewer",
        artifact_refs=[{"kind": "run", "path": "run_123"}],
        log_path=logs.work,
        operating_units_log=logs.units,
        kernel_events_log=logs.events,
    )

    resource = work_item_resource(done).as_dict()

    assert validate_resource(resource) == []
    assert resource["kind"] == "WorkItem"
    assert resource["metadata"]["name"] == item.work_id
    assert resource["metadata"]["tenant_id"] == "tenant-a"
    assert resource["metadata"]["project_id"] == "project-a"
    assert resource["metadata"]["annotations"]["cognitive_run_id"] == "run_123"
    assert resource["spec"]["unit_id"] == "residual_compiler"
    assert resource["spec"]["payload"] == {"claim": "bounded"}
    assert resource["status"]["status"] == "done"
    assert resource["status"]["claim_token"] == claimed.claim_token
    assert resource["status"]["exit_kind"] == "tested_hold"
    assert resource["status"]["producer"] == "role.proof_execution_worker"
    assert resource["status"]["verifier"] == "role.reviewer"
    assert {"rel": "operating_unit", "href": "operating_unit:residual_compiler"} in resource["links"]
    assert {"rel": "run", "href": "run_123"} in resource["links"]


def test_work_item_cli_can_render_resource_envelopes(logs: _Logs, capsys):
    item = _enqueue(logs, tenant_id="tenant-a")

    rc = work_items_main(
        [
            "list",
            "--log-path",
            str(logs.work),
            "--resource",
        ]
    )
    payloads = [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip()
    ]

    assert rc == 0
    assert len(payloads) == 1
    assert payloads[0]["kind"] == "WorkItem"
    assert payloads[0]["metadata"]["name"] == item.work_id
    assert validate_resource(payloads[0]) == []
