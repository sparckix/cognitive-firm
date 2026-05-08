"""GP-232 Phase B — content-addressed artifact-dependency primitive.

Three adversarial panels (distributed-systems engineer, biological-systems
comparative thinker, A2A protocol auditor) independently converged on the
same architectural answer for "task B depends on task A's output X":

  - Reuse `transitions.jsonl` (the GP-231 outbox substrate). Do NOT create
    a separate dependency log; that recreates the split-brain problem.
  - Producer emits `task.artifact.promised` THEN, after producing,
    `task.artifact.fulfilled` with content_hash + predicate_eval.
  - Consumer declares `awaits: [{artifact_key, predicate_hash}]` in role yaml.
  - work_discovery filters non-ready candidates.
  - Static cycle / predicate-drift detection at admission time.

The biological panel admitted the framing was decorative; the primitive is
content-addressed typed pub-sub with TTL. One calibration nudge from that
panel: monitor for gradient lock-in on artifact_key reuse.

Phase B ships:
  - promise_artifact() / fulfill_artifact() event emitters
  - is_awaits_satisfied(awaits, log_path) checker
  - rebuild_artifact_index() — secondary index keyed by artifact_key
  - check_dependency_cycles() — static cycle detection on awaits/promises graph
  - artifact_key_concentration() — gradient-lock-in monitor

Phase C will add saga compensation via parent_obligation_id (see GP-232).
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from cognitive_firm.orchestration.transition_log import (
    TRANSITIONS_LOG,
    append_transition,
)


log = logging.getLogger(__name__)


# ── helpers ────────────────────────────────────────────────────────────


def _read_log(log_path: Path) -> list[dict[str, Any]]:
    if not log_path.exists():
        return []
    out: list[dict[str, Any]] = []
    with log_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    return out


def predicate_hash(predicate_text: str) -> str:
    """Stable short hash of a predicate string. Used to key consumers'
    `awaits` declarations against the producer's `predicate_hash`. A
    mandate revision that changes the predicate text changes the hash,
    blocking downstream consumers until they update their awaits — the
    structural fix for silent predicate drift.
    """
    full = hashlib.sha256(predicate_text.encode("utf-8")).hexdigest()
    return f"p_{full[:8]}"


# ── promise + fulfill event emitters ──────────────────────────────────


def promise_artifact(
    *,
    role_id: str,
    task_id: str,
    artifact_key: str,
    predicate: str,
    expires_at_utc: Optional[str] = None,
    causality_id: Optional[str] = None,
    log_path: Path | None = None,
) -> dict[str, Any]:
    """Emit task.artifact.promised. The producer commits to producing
    artifact_key satisfying the predicate; consumers' awaits filter against
    this row's predicate_hash. Expires_at_utc supports TTL semantics
    (the biological panel's calibration nudge — markers must decay)."""
    if log_path is None:
        log_path = TRANSITIONS_LOG
    return append_transition(
        event="task.artifact.promised",
        actor=role_id,
        role_id=role_id,
        surface="artifact_dependency",
        subject=task_id,
        causality_id=causality_id,
        payload={
            "artifact_key": artifact_key,
            "predicate": predicate,
            "predicate_hash": predicate_hash(predicate),
            "expires_at_utc": expires_at_utc,
        },
        log_path=log_path,
    )


def fulfill_artifact(
    *,
    role_id: str,
    task_id: str,
    artifact_key: str,
    artifact_path: str,
    sha256: str,
    predicate_eval: dict[str, bool],
    predicate: str,
    causality_id: Optional[str] = None,
    supersedes: Optional[list[str]] = None,
    log_path: Path | None = None,
) -> dict[str, Any]:
    """Emit task.artifact.fulfilled. Carries the content hash + per-clause
    eval of the predicate so the audit trail records WHAT was produced
    and that it satisfied each named clause. Downstream consumers'
    awaits filter against this row's predicate_hash + the eval.
    """
    if log_path is None:
        log_path = TRANSITIONS_LOG
    return append_transition(
        event="task.artifact.fulfilled",
        actor=role_id,
        role_id=role_id,
        surface="artifact_dependency",
        subject=task_id,
        causality_id=causality_id,
        payload={
            "artifact_key": artifact_key,
            "artifact_path": artifact_path,
            "sha256": sha256,
            "predicate": predicate,
            "predicate_hash": predicate_hash(predicate),
            "predicate_eval": predicate_eval,
            "supersedes": supersedes or [],
        },
        log_path=log_path,
    )


# ── consumer-side: is the await satisfied? ─────────────────────────────


def is_awaits_satisfied(
    awaits: list[dict[str, str]],
    *,
    now: Optional[datetime] = None,
    log_path: Path | None = None,
) -> tuple[bool, list[str]]:
    """Return (all_satisfied, missing_descriptions).

    awaits is a list like [{"artifact_key": ..., "predicate_hash": ...}, ...]
    All entries must have a matching task.artifact.fulfilled row in the log
    AND every clause of predicate_eval must be true AND any TTL on the
    matching promise must not be expired.
    """
    if log_path is None:
        log_path = TRANSITIONS_LOG
    if not awaits:
        return True, []
    now = now or datetime.now(timezone.utc)
    log_rows = _read_log(log_path)

    # Build the fulfilled-by-key index + the active promise TTL.
    fulfilled: dict[tuple[str, str], dict[str, Any]] = {}
    promise_ttl: dict[tuple[str, str], Optional[str]] = {}
    for row in log_rows:
        evt = row.get("event")
        payload = row.get("payload") or {}
        ak = payload.get("artifact_key")
        ph = payload.get("predicate_hash")
        if not ak or not ph:
            continue
        if evt == "task.artifact.promised":
            promise_ttl[(ak, ph)] = payload.get("expires_at_utc")
        elif evt == "task.artifact.fulfilled":
            fulfilled[(ak, ph)] = payload

    missing: list[str] = []
    for entry in awaits:
        ak = entry.get("artifact_key")
        ph = entry.get("predicate_hash")
        if not ak or not ph:
            missing.append(f"malformed awaits entry: {entry}")
            continue
        match = fulfilled.get((ak, ph))
        if match is None:
            missing.append(f"no fulfilled row for ({ak}, {ph})")
            continue
        eval_clauses = match.get("predicate_eval") or {}
        if not all(bool(v) for v in eval_clauses.values()):
            failed = [k for k, v in eval_clauses.items() if not v]
            missing.append(f"({ak}) predicate clauses failed: {failed}")
            continue
        ttl = promise_ttl.get((ak, ph))
        if ttl:
            try:
                exp = datetime.fromisoformat(ttl)
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if now >= exp:
                    missing.append(f"({ak}) TTL expired at {ttl}")
            except Exception:  # noqa: BLE001
                missing.append(f"({ak}) malformed TTL {ttl}")
    return (len(missing) == 0), missing


# ── secondary index ────────────────────────────────────────────────────


def rebuild_artifact_index(
    *,
    log_path: Path | None = None,
) -> dict[str, list[int]]:
    """Rebuild the artifact_key → [fulfillment offsets] index from the log.

    Per the panel verdict: the index is rebuildable from the log on
    startup; it is a projection, not a separate truth. Same pattern as
    the GP-231 outbox-relay's pending-row scan.
    """
    if log_path is None:
        log_path = TRANSITIONS_LOG
    if not log_path.exists():
        return {}
    out: dict[str, list[int]] = defaultdict(list)
    with log_path.open("r", encoding="utf-8") as fh:
        for offset, line in enumerate(fh):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if row.get("event") != "task.artifact.fulfilled":
                continue
            ak = (row.get("payload") or {}).get("artifact_key")
            if ak:
                out[str(ak)].append(offset)
    return dict(out)


# ── static cycle detection ─────────────────────────────────────────────


def check_dependency_cycles(
    awaits_by_task: dict[str, list[dict[str, str]]],
    promises_by_task: dict[str, list[str]],
) -> list[list[str]]:
    """Run a DFS for cycles on the awaits/promises graph.

    awaits_by_task: task_id -> list of {artifact_key, predicate_hash}
    promises_by_task: task_id -> list of artifact_key

    Returns a list of cycles (each cycle is a list of task_ids). Empty
    list means no cycles.
    """
    # Build artifact_key -> list of promiser tasks.
    promisers: dict[str, list[str]] = defaultdict(list)
    for task_id, keys in promises_by_task.items():
        for k in keys:
            promisers[k].append(task_id)

    # Edge t1 -> t2 means "t1 awaits something t2 promises".
    edges: dict[str, set[str]] = defaultdict(set)
    for task_id, awaits in awaits_by_task.items():
        for entry in awaits:
            ak = entry.get("artifact_key")
            if not ak:
                continue
            for producer in promisers.get(ak, []):
                if producer == task_id:
                    continue
                edges[task_id].add(producer)

    cycles: list[list[str]] = []
    state: dict[str, str] = {}  # WHITE | GRAY | BLACK
    stack: list[str] = []

    def dfs(node: str) -> None:
        state[node] = "GRAY"
        stack.append(node)
        for nbr in edges.get(node, set()):
            s = state.get(nbr, "WHITE")
            if s == "GRAY":
                # Cycle: extract the cycle from the stack.
                if nbr in stack:
                    idx = stack.index(nbr)
                    cycles.append(stack[idx:] + [nbr])
            elif s == "WHITE":
                dfs(nbr)
        stack.pop()
        state[node] = "BLACK"

    for n in list(edges.keys()) + list(awaits_by_task.keys()):
        if state.get(n, "WHITE") == "WHITE":
            dfs(n)
    return cycles


# ── gradient lock-in monitor (biological panel calibration) ───────────


def artifact_key_concentration(
    *,
    log_path: Path | None = None,
    window_hours: float = 168.0,
) -> dict[str, Any]:
    """Surface trail-reinforcement bias: if one artifact_key dominates
    the recent fulfillments, the substrate may be locked into one
    coordination path. Returns {top_key, top_share, total, distribution}.
    Threshold of 0.7 is the biological panel's recommended alarm level.
    """
    if log_path is None:
        log_path = TRANSITIONS_LOG
    rows = _read_log(log_path)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        if row.get("event") != "task.artifact.fulfilled":
            continue
        ts_text = row.get("ts")
        if ts_text:
            try:
                ts = datetime.fromisoformat(ts_text)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts < cutoff:
                    continue
            except Exception:  # noqa: BLE001
                pass
        ak = (row.get("payload") or {}).get("artifact_key")
        if ak:
            counts[str(ak)] += 1
    total = sum(counts.values())
    if total == 0:
        return {"top_key": None, "top_share": 0.0, "total": 0, "distribution": {}}
    top_key, top_count = max(counts.items(), key=lambda kv: kv[1])
    return {
        "top_key": top_key,
        "top_share": top_count / total,
        "total": total,
        "distribution": dict(counts),
        "lock_in_alarm": (top_count / total) >= 0.7,
    }
