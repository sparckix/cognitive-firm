from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.kernel_service import KernelServiceConfig, dispatch_kernel_request  # noqa: E402
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

        print(
            json.dumps(
                {
                    "ok": True,
                    "service": health.payload["service"],
                    "backend": backend.connector_id,
                    "accepted_events": len(events),
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
