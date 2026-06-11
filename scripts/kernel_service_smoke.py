from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.kernel_service import KernelServiceConfig, dispatch_kernel_request  # noqa: E402
from cognitive_firm.orchestration.governance_changes import REQUIRED_INVARIANTS  # noqa: E402
from cognitive_firm.orchestration.state_backends import SqliteMutationBackend  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="cognitive-firm-kernel-smoke-") as raw:
        root = Path(raw)
        backend = SqliteMutationBackend(root / "mutations.sqlite3")
        actor_context = {
            "actor_id": "human.alice",
            "actor_kind": "human",
            "role_id": "role.manager",
            "surface": "kernel_service_smoke",
        }
        config = KernelServiceConfig(
            human_work_log=root / "human_work.jsonl",
            accountability_cases_log=root / "accountability_cases.jsonl",
            actor_identity_log=root / "actors.jsonl",
            leases_log=root / "leases.jsonl",
            org_dir=root / "org",
            gates_dir=root / "workspace" / "gates" / "pending",
            gates_resolved_dir=root / "workspace" / "gates" / "resolved",
            transition_log=root / "workspace" / "transitions.jsonl",
            mutation_backend=backend,
        )

        health = dispatch_kernel_request("GET", "/health", config=config)
        _assert_status(health.status, 200, "health")

        lease = dispatch_kernel_request(
            "POST",
            "/kernel/leases",
            {
                "resource_ref": "smoke:resource",
                "ttl_seconds": 60,
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(lease.status, 201, "lease")
        lease_record = lease.payload["lease"]

        accepted = dispatch_kernel_request(
            "POST",
            "/kernel/mutation-events",
            {
                "stream": "transitions",
                "resource_ref": "smoke:resource",
                "lease_id": lease_record["lease_id"],
                "fencing_token": lease_record["fencing_token"],
                "event": {"event": "smoke.mutation.accepted"},
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(accepted.status, 201, "guarded append")

        rejected = dispatch_kernel_request(
            "POST",
            "/kernel/mutation-events",
            {
                "stream": "transitions",
                "resource_ref": "smoke:resource",
                "lease_id": lease_record["lease_id"],
                "fencing_token": lease_record["fencing_token"] + 1,
                "event": {"event": "smoke.mutation.stale"},
                "actor_context": actor_context,
            },
            config=config,
        )
        if rejected.status != 400:
            raise AssertionError(f"stale fencing unexpectedly accepted: {rejected.payload}")

        events = backend.read_events("transitions")
        if len(events) != 1 or events[0]["event"] != "smoke.mutation.accepted":
            raise AssertionError(f"unexpected events: {events}")

        governance_proposal = dispatch_kernel_request(
            "POST",
            "/kernel/governance-changes",
            {
                "change_kind": "mandate_change",
                "title": "Clarify smoke-test mandate",
                "target_ref": "org/mandates/smoke.md",
                "rationale": "Smoke verifies the governed proposal path.",
                "source_refs": ["smoke:mutation.accepted"],
                "expected_behavior_change": "Future smoke work uses the clarified mandate.",
                "risk_summary": "No authority expansion; test-only workspace.",
                "rollback_plan": "Delete the temp workspace.",
                "invariant_checks": [
                    {
                        "invariant": invariant,
                        "status": "pass",
                        "rationale": f"{invariant} preserved by test fixture.",
                        "evidence_refs": [f"smoke:{invariant}"],
                    }
                    for invariant in sorted(REQUIRED_INVARIANTS)
                ],
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(governance_proposal.status, 201, "governance proposal")
        proposal_id = governance_proposal.payload["proposal"]["proposal_id"]
        if governance_proposal.payload["proposal"]["status"] != "review_ready":
            raise AssertionError(
                f"proposal not review-ready: {governance_proposal.payload}"
            )

        governance_resource = dispatch_kernel_request(
            "GET",
            f"/kernel/governance-changes/{proposal_id}?resource=true",
            config=config,
        )
        _assert_status(governance_resource.status, 200, "governance resource")
        if governance_resource.payload["proposal"]["kind"] != "GovernanceChangeProposal":
            raise AssertionError(
                f"unexpected governance resource: {governance_resource.payload}"
            )

        governance_decision = dispatch_kernel_request(
            "POST",
            f"/kernel/governance-changes/{proposal_id}/decision",
            {
                "decision": "approve",
                "reason": "smoke test approval",
                "actor_context": actor_context,
            },
            config=config,
        )
        _assert_status(governance_decision.status, 200, "governance decision")

        print(
            json.dumps(
                {
                    "ok": True,
                    "service": health.payload["service"],
                    "backend": backend.connector_id,
                    "accepted_events": len(events),
                    "governance_proposal_status": governance_proposal.payload[
                        "proposal"
                    ]["status"],
                    "governance_decision": governance_decision.payload["result"][
                        "decision"
                    ],
                    "stale_rejected": True,
                },
                sort_keys=True,
            )
        )
    return 0


def _assert_status(actual: int, expected: int, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label} returned {actual}, expected {expected}")


if __name__ == "__main__":
    raise SystemExit(main())
