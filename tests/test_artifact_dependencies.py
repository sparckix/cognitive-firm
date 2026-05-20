"""GP-232 Phase B — content-addressed artifact-dependency primitive tests.

Properties under test:
  - promise + fulfill events land in transitions.jsonl with deterministic
    predicate_hash that survives the producer/consumer round-trip
  - is_awaits_satisfied returns False when no fulfilled row exists
  - is_awaits_satisfied returns False when predicate_eval has any False clause
    (the no-stale-success guard)
  - is_awaits_satisfied returns False when the matching promise's TTL expired
  - rebuild_artifact_index correctly maps artifact_key → log offsets
  - check_dependency_cycles detects cycles + returns the cycle path
  - check_dependency_cycles passes a clean DAG
  - artifact_key_concentration flags lock-in when one key dominates >= 70%
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.artifact_dependencies import (  # noqa: E402
    artifact_key_concentration,
    check_dependency_cycles,
    fulfill_artifact,
    is_awaits_satisfied,
    predicate_hash,
    promise_artifact,
    rebuild_artifact_index,
)


# ── round-trip ─────────────────────────────────────────────────────────


def test_promise_then_fulfill_satisfies_awaits(tmp_path: Path):
    log = tmp_path / "transitions.jsonl"
    predicate = "schema_version >= 2 AND score >= 0.7"
    ph = predicate_hash(predicate)

    promise_artifact(
        role_id="research_director", task_id="task_1",
        artifact_key="validator.results.X", predicate=predicate,
        log_path=log,
    )
    fulfill_artifact(
        role_id="research_director", task_id="task_1",
        artifact_key="validator.results.X",
        artifact_path="cognitive_firm_workspace/validator/X.json",
        sha256="9af3" * 16,
        predicate=predicate,
        predicate_eval={"schema_version_ge_2": True, "score_ge_0_7": True},
        log_path=log,
    )

    awaits = [{"artifact_key": "validator.results.X", "predicate_hash": ph}]
    ok, missing = is_awaits_satisfied(awaits, log_path=log)
    assert ok is True
    assert missing == []


def test_predicate_hash_deterministic():
    """Same predicate text → same hash. This is what makes drift detection
    work: a mandate revision that changes the predicate changes the hash,
    and consumers' awaits stop matching until they update."""
    p1 = predicate_hash("score >= 0.7")
    p2 = predicate_hash("score >= 0.7")
    p3 = predicate_hash("score >= 0.8")
    assert p1 == p2
    assert p1 != p3


# ── failure modes ─────────────────────────────────────────────────────


def test_no_fulfilled_row_means_unsatisfied(tmp_path: Path):
    log = tmp_path / "transitions.jsonl"
    predicate = "score >= 0.5"
    promise_artifact(
        role_id="rd", task_id="t1",
        artifact_key="A", predicate=predicate, log_path=log,
    )
    # Promise but no fulfillment.
    awaits = [{"artifact_key": "A", "predicate_hash": predicate_hash(predicate)}]
    ok, missing = is_awaits_satisfied(awaits, log_path=log)
    assert ok is False
    assert "no fulfilled row" in missing[0]


def test_failed_predicate_clause_means_unsatisfied(tmp_path: Path):
    log = tmp_path / "transitions.jsonl"
    predicate = "score >= 0.7 AND fresh"
    fulfill_artifact(
        role_id="rd", task_id="t1",
        artifact_key="A", artifact_path="x", sha256="abc",
        predicate=predicate,
        predicate_eval={"score_ge_0_7": True, "fresh": False},  # one False clause
        log_path=log,
    )
    awaits = [{"artifact_key": "A", "predicate_hash": predicate_hash(predicate)}]
    ok, missing = is_awaits_satisfied(awaits, log_path=log)
    assert ok is False
    assert "predicate clauses failed" in missing[0]
    assert "fresh" in missing[0]


def test_expired_ttl_means_unsatisfied(tmp_path: Path):
    log = tmp_path / "transitions.jsonl"
    predicate = "score >= 0.5"
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    promise_artifact(
        role_id="rd", task_id="t1",
        artifact_key="A", predicate=predicate,
        expires_at_utc=past, log_path=log,
    )
    fulfill_artifact(
        role_id="rd", task_id="t1",
        artifact_key="A", artifact_path="x", sha256="abc",
        predicate=predicate,
        predicate_eval={"score_ge_0_5": True},
        log_path=log,
    )
    awaits = [{"artifact_key": "A", "predicate_hash": predicate_hash(predicate)}]
    ok, missing = is_awaits_satisfied(awaits, log_path=log)
    assert ok is False
    assert "TTL expired" in missing[0]


def test_predicate_drift_blocks_old_consumers(tmp_path: Path):
    """A consumer's awaits with the OLD predicate_hash does not match a
    fulfillment with a NEW predicate_hash. This is the structural drift
    fix the panel asked for."""
    log = tmp_path / "transitions.jsonl"
    old_predicate = "score >= 0.5"
    new_predicate = "score >= 0.7"
    fulfill_artifact(
        role_id="rd", task_id="t1",
        artifact_key="A", artifact_path="x", sha256="abc",
        predicate=new_predicate,
        predicate_eval={"score_ge_0_7": True},
        log_path=log,
    )
    # Consumer is still on the old predicate_hash.
    awaits = [{"artifact_key": "A", "predicate_hash": predicate_hash(old_predicate)}]
    ok, missing = is_awaits_satisfied(awaits, log_path=log)
    assert ok is False, "old-predicate consumer should not match new-predicate fulfillment"


def test_empty_awaits_is_trivially_satisfied(tmp_path: Path):
    log = tmp_path / "transitions.jsonl"
    ok, missing = is_awaits_satisfied([], log_path=log)
    assert ok is True
    assert missing == []


# ── secondary index ────────────────────────────────────────────────────


def test_rebuild_artifact_index(tmp_path: Path):
    log = tmp_path / "transitions.jsonl"
    fulfill_artifact(
        role_id="rd", task_id="t1",
        artifact_key="A", artifact_path="x", sha256="abc",
        predicate="p", predicate_eval={"p": True}, log_path=log,
    )
    fulfill_artifact(
        role_id="rd", task_id="t2",
        artifact_key="B", artifact_path="y", sha256="def",
        predicate="q", predicate_eval={"q": True}, log_path=log,
    )
    fulfill_artifact(
        role_id="rd", task_id="t3",
        artifact_key="A", artifact_path="z", sha256="ghi",
        predicate="p", predicate_eval={"p": True}, log_path=log,
    )
    index = rebuild_artifact_index(log_path=log)
    # Note: each fulfill_artifact also emits a promise row? No — only fulfill.
    # Still, A was fulfilled twice, B once.
    assert "A" in index
    assert "B" in index
    assert len(index["A"]) == 2
    assert len(index["B"]) == 1


# ── cycle detection ────────────────────────────────────────────────────


def test_cycle_detection_finds_simple_cycle():
    """Task A awaits B's output, B awaits A's. Classic deadlock."""
    awaits_by_task = {
        "task_A": [{"artifact_key": "B_output", "predicate_hash": "p_x"}],
        "task_B": [{"artifact_key": "A_output", "predicate_hash": "p_y"}],
    }
    promises_by_task = {
        "task_A": ["A_output"],
        "task_B": ["B_output"],
    }
    cycles = check_dependency_cycles(awaits_by_task, promises_by_task)
    assert len(cycles) > 0
    # The cycle should mention both task_A and task_B.
    flat = {t for c in cycles for t in c}
    assert "task_A" in flat
    assert "task_B" in flat


def test_cycle_detection_passes_clean_dag():
    """A → B → C, no cycles."""
    awaits_by_task = {
        "task_C": [{"artifact_key": "B_output", "predicate_hash": "p_x"}],
        "task_B": [{"artifact_key": "A_output", "predicate_hash": "p_y"}],
    }
    promises_by_task = {
        "task_A": ["A_output"],
        "task_B": ["B_output"],
    }
    cycles = check_dependency_cycles(awaits_by_task, promises_by_task)
    assert cycles == []


def test_cycle_detection_finds_three_node_cycle():
    awaits_by_task = {
        "task_A": [{"artifact_key": "C_output", "predicate_hash": "p"}],
        "task_B": [{"artifact_key": "A_output", "predicate_hash": "p"}],
        "task_C": [{"artifact_key": "B_output", "predicate_hash": "p"}],
    }
    promises_by_task = {
        "task_A": ["A_output"],
        "task_B": ["B_output"],
        "task_C": ["C_output"],
    }
    cycles = check_dependency_cycles(awaits_by_task, promises_by_task)
    assert len(cycles) > 0
    flat = {t for c in cycles for t in c}
    assert {"task_A", "task_B", "task_C"} <= flat


# ── gradient lock-in monitor ──────────────────────────────────────────


def test_concentration_flags_lockin_above_70_pct(tmp_path: Path):
    """The biological panel's calibration nudge: warn if one artifact_key
    dominates >= 70% of recent fulfillments — possible trail reinforcement."""
    log = tmp_path / "transitions.jsonl"
    # 8 fulfillments of A, 2 of B → A is 80%
    for _ in range(8):
        fulfill_artifact(
            role_id="rd", task_id="t",
            artifact_key="A", artifact_path="x", sha256="abc",
            predicate="p", predicate_eval={"p": True}, log_path=log,
        )
    for _ in range(2):
        fulfill_artifact(
            role_id="rd", task_id="t",
            artifact_key="B", artifact_path="y", sha256="def",
            predicate="q", predicate_eval={"q": True}, log_path=log,
        )
    result = artifact_key_concentration(log_path=log)
    assert result["top_key"] == "A"
    assert result["top_share"] == 0.8
    assert result["total"] == 10
    assert result["lock_in_alarm"] is True


def test_concentration_does_not_flag_balanced_distribution(tmp_path: Path):
    log = tmp_path / "transitions.jsonl"
    for k in ("A", "B", "C", "D"):
        fulfill_artifact(
            role_id="rd", task_id="t",
            artifact_key=k, artifact_path="x", sha256="abc",
            predicate="p", predicate_eval={"p": True}, log_path=log,
        )
    result = artifact_key_concentration(log_path=log)
    assert result["top_share"] == 0.25
    assert result["lock_in_alarm"] is False


def test_concentration_handles_empty_log(tmp_path: Path):
    log = tmp_path / "transitions.jsonl"
    result = artifact_key_concentration(log_path=log)
    assert result["total"] == 0
    assert result["top_key"] is None
