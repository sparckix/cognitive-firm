#!/usr/bin/env python3
"""Executable multi-human/multi-service authority walkthrough."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.kernel_service import (  # noqa: E402
    KernelServiceConfig,
    dispatch_kernel_request,
)
from cognitive_firm.orchestration.state_backends import SqliteMutationBackend  # noqa: E402


def _actor_context(actor_id: str, role_id: str, project_id: str = "project-a") -> dict[str, str]:
    kind = "human" if actor_id.startswith("human.") else "service"
    return {
        "actor_id": actor_id,
        "actor_kind": kind,
        "role_id": role_id,
        "surface": "walkthrough",
        "tenant_id": "tenant-a",
        "project_id": project_id,
    }


def _owner_context() -> dict[str, str]:
    context = _actor_context("human.owner", "role.owner")
    context["identity_provider"] = "fixture"
    context["auth_subject"] = "owner@example.com"
    return context


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="cf-multi-actor-") as raw:
        root = Path(raw)
        identity_log = root / "org" / "identity" / "actor_identities.jsonl"
        membership_log = root / "org" / "identity" / "actor_memberships.jsonl"
        lease_log = root / "org" / "leases" / "leases.jsonl"
        human_log = root / "org" / "human_work" / "human_work.jsonl"
        policy_log = root / "org" / "policy" / "policy_decisions.jsonl"
        mutation_db = root / "workspace" / "events.sqlite"

        bootstrap_config = KernelServiceConfig(
            actor_identity_log=identity_log,
            actor_membership_log=membership_log,
            human_work_log=human_log,
            policy_decisions_log=policy_log,
        )

        for actor_id, display_name, actor_kind, auth_subject in [
            ("human.reviewer", "Human Reviewer", "human", "reviewer@example.com"),
            ("human.owner", "Human Owner", "human", "owner@example.com"),
            ("service.worker", "Service Worker", "service", "svc-worker"),
            ("service.app", "Service App", "service", "svc-app"),
        ]:
            response = dispatch_kernel_request(
                "POST",
                "/kernel/actors",
                {
                    "actor_id": actor_id,
                    "display_name": display_name,
                    "actor_kind": actor_kind,
                    "identity_provider": "fixture",
                    "auth_subject": auth_subject,
                    "actor_context": _owner_context(),
                },
                config=bootstrap_config,
            )
            if response.status != 201:
                raise SystemExit(f"actor registration failed: {response.payload}")

        for actor_id, role_id in [
            ("human.reviewer", "role.reviewer"),
            ("human.owner", "role.owner"),
            ("service.worker", "role.worker"),
            ("service.app", "role.app"),
        ]:
            response = dispatch_kernel_request(
                "POST",
                "/kernel/memberships",
                {
                    "actor_id": actor_id,
                    "role_id": role_id,
                    "tenant_id": "tenant-a",
                    "project_id": "project-a",
                    "granted_by": "human.owner",
                    "decision_right_basis": "fixture/multi-actor",
                    "actor_context": _owner_context(),
                },
                config=bootstrap_config,
            )
            if response.status != 201:
                raise SystemExit(f"membership grant failed: {response.payload}")

        backend = SqliteMutationBackend(mutation_db)
        config = KernelServiceConfig(
            mutation_backend=backend,
            enforce_registered_actors=True,
            enforce_actor_membership=True,
            enforce_subject_scope=True,
            actor_identity_log=identity_log,
            actor_membership_log=membership_log,
            leases_log=lease_log,
            human_work_log=human_log,
            policy_decisions_log=policy_log,
        )

        policy_response = dispatch_kernel_request(
            "POST",
            "/kernel/policy-decisions/evaluate",
            {
                "request": {
                    "action": "kernel_event.append",
                    "actor_id": "service.worker",
                    "resource_ref": "kernel_event:project-a",
                    "tenant_id": "tenant-a",
                    "role_id": "role.worker",
                    "project_id": "project-a",
                },
                "rules": [
                    {
                        "rule_id": "allow-worker-project-a",
                        "effect": "allow",
                        "reason": "worker has scoped project membership",
                        "match": {"actor_id": "service.worker", "project_id": "project-a"},
                    }
                ],
                "actor_context": _actor_context("service.worker", "role.worker"),
            },
            config=config,
        )
        if policy_response.status != 201:
            raise SystemExit(f"policy evaluation failed: {policy_response.payload}")
        policy = policy_response.payload["policy_decision"]

        session_response = dispatch_kernel_request(
            "POST",
            "/kernel/human-work",
            {
                "requested_by": "service.worker",
                "human_actor": "human.reviewer",
                "objective": "Review bounded source claim before external use.",
                "work_mode": "source_check",
                "bottleneck_class": "cognition",
                "collaborating_roles": ["role.worker", "role.reviewer"],
                "actor_context": _actor_context("service.worker", "role.worker"),
            },
            config=config,
        )
        if session_response.status != 201:
            raise SystemExit(f"human-work creation failed: {session_response.payload}")
        session = session_response.payload["session"]

        lease_response = dispatch_kernel_request(
            "POST",
            "/kernel/leases",
            {
                "resource_ref": "kernel_event:project-a",
                "ttl_seconds": 300,
                "actor_context": _actor_context("service.worker", "role.worker"),
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
                    "policy_decision": policy["decision_id"],
                },
                "actor_context": _actor_context("service.worker", "role.worker"),
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
                "actor_context": _actor_context("service.worker", "role.worker", "project-b"),
            },
            config=config,
        )
        if accepted.status != 201 or denied.status != 400:
            raise SystemExit("multi-actor authority fixture did not enforce scoped membership")

        print(json.dumps({
            "ok": True,
            "accepted_status": accepted.status,
            "denied_status": denied.status,
            "human_work_session": session["session_id"],
            "lease_token": lease["fencing_token"],
            "policy_decision": policy["decision_id"],
        }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
