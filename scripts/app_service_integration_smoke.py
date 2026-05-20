from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.kernel_service import KernelServiceConfig, dispatch_kernel_request  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="cognitive-firm-app-service-") as raw:
        root = Path(raw)
        config = KernelServiceConfig(
            human_work_log=root / "human_work.jsonl",
            accountability_cases_log=root / "accountability_cases.jsonl",
            actor_identity_log=root / "actors.jsonl",
            actor_membership_log=root / "memberships.jsonl",
            leases_log=root / "leases.jsonl",
            enforce_registered_actors=True,
            enforce_actor_membership=True,
            require_leases=True,
        )
        bootstrap = KernelServiceConfig(
            human_work_log=config.human_work_log,
            accountability_cases_log=config.accountability_cases_log,
            actor_identity_log=config.actor_identity_log,
            actor_membership_log=config.actor_membership_log,
            leases_log=config.leases_log,
        )
        _register_actor(bootstrap, "human.alice", "role.manager")
        _grant_membership(bootstrap, "human.alice", "role.manager")

        actor_context = {
            "actor_id": "human.alice",
            "actor_kind": "human",
            "role_id": "role.manager",
            "tenant_id": "tenant-example",
            "surface": "app_service_integration_smoke",
        }

        lease = _request(
            "POST",
            "/kernel/leases",
            {
                "resource_ref": "human_work:create",
                "ttl_seconds": 60,
                "actor_context": actor_context,
            },
            config,
            expected=201,
        )["lease"]

        created = _request(
            "POST",
            "/kernel/human-work",
            {
                "requested_by": "role.manager",
                "coordination_pattern": "a2h_work_request",
                "human_actor": "principal",
                "objective": "Verify the app-service integration path.",
                "work_mode": "source_check",
                "bottleneck_class": "access",
                "human_deliverable": "receipt",
                "actor_context": actor_context,
                "lease_id": lease["lease_id"],
                "fencing_token": lease["fencing_token"],
            },
            config,
            expected=201,
        )["session"]

        surface = _request(
            "GET",
            "/kernel/org-surface",
            {"actor_context": actor_context},
            config,
            expected=200,
        )["surface"]
        waiting = surface["counts"]["a2h_waiting_on_human_sessions"]
        if waiting != 1:
            raise AssertionError(f"expected one waiting human-work session, got {waiting}")

        print(
            json.dumps(
                {
                    "ok": True,
                    "actor": actor_context["actor_id"],
                    "role": actor_context["role_id"],
                    "lease_resource": lease["resource_ref"],
                    "human_work_session": created["session_id"],
                    "org_surface_waiting": waiting,
                },
                sort_keys=True,
            )
        )
    return 0


def _register_actor(config: KernelServiceConfig, actor_id: str, role_id: str) -> None:
    _request(
        "POST",
        "/kernel/actors",
        {
            "actor_id": actor_id,
            "actor_kind": "human",
            "display_name": actor_id,
            "roles_allowed": [role_id],
            "tenant_ids": ["tenant-example"],
            "actor_context": {"actor_id": "service.bootstrap", "actor_kind": "service"},
        },
        config,
        expected=201,
    )


def _grant_membership(config: KernelServiceConfig, actor_id: str, role_id: str) -> None:
    _request(
        "POST",
        "/kernel/memberships",
        {
            "actor_id": actor_id,
            "role_id": role_id,
            "tenant_id": "tenant-example",
            "granted_by": "service.bootstrap",
            "decision_right_basis": "app-service smoke bootstrap",
            "actor_context": {"actor_id": "service.bootstrap", "actor_kind": "service"},
        },
        config,
        expected=201,
    )


def _request(
    method: str,
    path: str,
    body: dict | None,
    config: KernelServiceConfig,
    *,
    expected: int,
) -> dict:
    response = dispatch_kernel_request(method, path, body, config=config)
    if response.status != expected:
        raise AssertionError(f"{method} {path} returned {response.status}: {response.payload}")
    return response.payload


if __name__ == "__main__":
    raise SystemExit(main())
