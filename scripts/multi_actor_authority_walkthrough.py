#!/usr/bin/env python3
"""Executable multi-human/multi-service authority walkthrough."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.actor_identity import register_actor_identity  # noqa: E402
from cognitive_firm.orchestration.actor_membership import grant_actor_membership  # noqa: E402
from cognitive_firm.orchestration.human_work import create_human_work_session  # noqa: E402
from cognitive_firm.kernel_service import (  # noqa: E402
    KernelServiceConfig,
    dispatch_kernel_request,
)
from cognitive_firm.orchestration.policy_decisions import PolicyDecisionRequest, evaluate_policy  # noqa: E402
from cognitive_firm.orchestration.state_backends import SqliteMutationBackend  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="cf-multi-actor-") as raw:
        root = Path(raw)
        identity_log = root / "org" / "identity" / "actor_identities.jsonl"
        membership_log = root / "org" / "identity" / "actor_memberships.jsonl"
        lease_log = root / "org" / "leases" / "leases.jsonl"
        human_log = root / "org" / "human_work" / "human_work.jsonl"
        policy_log = root / "org" / "policy" / "policy_decisions.jsonl"
        mutation_db = root / "workspace" / "events.sqlite"

        human_reviewer = register_actor_identity(
            actor_id="human.reviewer",
            display_name="Human Reviewer",
            actor_kind="human",
            identity_provider="fixture",
            auth_subject="reviewer@example.com",
            log_path=identity_log,
        )
        human_owner = register_actor_identity(
            actor_id="human.owner",
            display_name="Human Owner",
            actor_kind="human",
            identity_provider="fixture",
            auth_subject="owner@example.com",
            log_path=identity_log,
        )
        service_worker = register_actor_identity(
            actor_id="service.worker",
            display_name="Service Worker",
            actor_kind="service",
            identity_provider="fixture",
            auth_subject="svc-worker",
            log_path=identity_log,
        )
        service_app = register_actor_identity(
            actor_id="service.app",
            display_name="Service App",
            actor_kind="service",
            identity_provider="fixture",
            auth_subject="svc-app",
            log_path=identity_log,
        )

        for actor, role in [
            (human_reviewer.actor_id, "role.reviewer"),
            (human_owner.actor_id, "role.owner"),
            (service_worker.actor_id, "role.worker"),
            (service_app.actor_id, "role.app"),
        ]:
            grant_actor_membership(
                actor_id=actor,
                role_id=role,
                tenant_id="tenant-a",
                project_id="project-a",
                granted_by="human.owner",
                decision_right_basis="fixture/multi-actor",
                log_path=membership_log,
            )

        backend = SqliteMutationBackend(mutation_db)
        policy = evaluate_policy(
            PolicyDecisionRequest(
                action="kernel_event.append",
                actor_id="service.worker",
                resource_ref="kernel_event:project-a",
                tenant_id="tenant-a",
                role_id="role.worker",
                project_id="project-a",
            ),
            rules=[
                {
                    "rule_id": "allow-worker-project-a",
                    "effect": "allow",
                    "reason": "worker has scoped project membership",
                    "match": {"actor_id": "service.worker", "project_id": "project-a"},
                }
            ],
            log_path=policy_log,
        )
        session = create_human_work_session(
            requested_by="service.worker",
            human_actor="human.reviewer",
            objective="Review bounded source claim before external use.",
            work_mode="source_check",
            bottleneck_class="cognition",
            collaborating_roles=["role.worker", "role.reviewer"],
            log_path=human_log,
        )
        config = KernelServiceConfig(
            mutation_backend=backend,
            enforce_registered_actors=True,
            enforce_actor_membership=True,
            enforce_subject_scope=True,
            actor_identity_log=identity_log,
            actor_membership_log=membership_log,
            leases_log=lease_log,
        )
        lease_response = dispatch_kernel_request(
            "POST",
            "/kernel/leases",
            {
                "resource_ref": "kernel_event:project-a",
                "ttl_seconds": 300,
                "actor_context": {
                    "actor_id": "service.worker",
                    "actor_kind": "service",
                    "role_id": "role.worker",
                    "surface": "walkthrough",
                    "tenant_id": "tenant-a",
                    "project_id": "project-a",
                },
            },
            config=config,
        )
        if lease_response.status != 201:
            raise SystemExit(f"lease acquisition failed: {lease_response.payload}")
        lease = lease_response.payload["lease"]
        accepted = dispatch_kernel_request(
            "POST",
            "/kernel/mutation-events",
            {
                "stream": "transitions",
                "resource_ref": "kernel_event:project-a",
                "lease_id": lease["lease_id"],
                "fencing_token": lease["fencing_token"],
                "event": {
                    "event": "work.proposed",
                    "project_id": "project-a",
                    "policy_decision": policy.decision_id,
                },
                "actor_context": {
                    "actor_id": "service.worker",
                    "actor_kind": "service",
                    "role_id": "role.worker",
                    "surface": "walkthrough",
                    "tenant_id": "tenant-a",
                    "project_id": "project-a",
                },
            },
            config=config,
        )
        denied = dispatch_kernel_request(
            "POST",
            "/kernel/mutation-events",
            {
                "stream": "transitions",
                "resource_ref": "kernel_event:project-a",
                "lease_id": lease["lease_id"],
                "fencing_token": lease["fencing_token"],
                "event": {"event": "work.proposed", "project_id": "project-b"},
                "actor_context": {
                    "actor_id": "service.worker",
                    "actor_kind": "service",
                    "role_id": "role.worker",
                    "surface": "walkthrough",
                    "tenant_id": "tenant-a",
                    "project_id": "project-b",
                },
            },
            config=config,
        )
        if accepted.status != 201 or denied.status != 400:
            raise SystemExit("multi-actor authority fixture did not enforce scoped membership")

        print(json.dumps({
            "ok": True,
            "accepted_status": accepted.status,
            "denied_status": denied.status,
            "human_work_session": session.session_id,
            "lease_token": lease["fencing_token"],
            "policy_decision": policy.decision_id,
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
