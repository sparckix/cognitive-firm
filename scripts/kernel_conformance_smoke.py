#!/usr/bin/env python3
"""Run small kernel-contract conformance fixtures."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from cognitive_firm.orchestration.actor_identity import build_actor_context, register_actor_identity
from cognitive_firm.orchestration.actor_membership import grant_actor_membership
from cognitive_firm.identity_provisioning import (
    DirectoryActor,
    DirectoryMembership,
    ProvisioningPlan,
    apply_provisioning_plan,
)
from cognitive_firm.orchestration.human_work import list_human_work_sessions
from cognitive_firm.orchestration.otel_export import write_otel_projection
from cognitive_firm.orchestration.policy_decisions import (
    PolicyDecisionRequest,
    PolicyRule,
    evaluate_policy,
)
from cognitive_firm.orchestration.runtime_adapters import (
    RuntimeEvent,
    bridge_runtime_interrupt_to_human_work,
    record_runtime_event,
)
from cognitive_firm.orchestration.state_surface_inventory import unregistered_stateful_modules
from cognitive_firm.orchestration.tenant_isolation import tenant_overlay_root, validate_tenant_ref


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="cf-kernel-conformance-") as raw:
        root = Path(raw)
        transition_log = root / "transitions.jsonl"
        human_work_log = root / "human_work.jsonl"
        actor_identity_log = root / "actors.jsonl"
        actor_membership_log = root / "memberships.jsonl"
        policy_log = root / "policy.jsonl"
        otel_path = root / "otel.json"

        start = record_runtime_event(
            RuntimeEvent(
                runtime_name="conformance_runtime",
                external_run_id="run-1",
                kind="started",
                owner_role="role.manager",
                actor="role.manager",
                objective="verify runtime projection",
            ),
            log_path=transition_log,
        )
        interrupt = bridge_runtime_interrupt_to_human_work(
            runtime_name="conformance_runtime",
            external_run_id="run-1",
            actor="role.manager",
            interrupt_id="needs-human",
            interrupt_summary="Human input required before external side effect",
            human_actor="human.principal",
            human_deliverable="approve or reject the side effect",
            resume_ref="runtime://run-1/resume/needs-human",
            log_path=transition_log,
            human_work_log_path=human_work_log,
        )
        spans = write_otel_projection(output_path=otel_path, log_path=transition_log)
        policy = evaluate_policy(
            PolicyDecisionRequest(
                action="runtime.resume",
                actor_id="human.principal",
                role_id="role.manager",
                resource_ref=interrupt["resume_ref"],
                context={"risk_tier": "low"},
            ),
            rules=[
                PolicyRule(
                    rule_id="allow-low-risk-resume",
                    effect="allow",
                    reason="principal may resume this low-risk conformance run",
                    match={"actor_id": "human.principal", "context.risk_tier": "low"},
                )
            ],
            policy_ref="conformance/local",
            log_path=policy_log,
        )
        for actor_id, role_id in (
            ("human.alice", "role.manager"),
            ("human.bob", "role.reviewer"),
        ):
            register_actor_identity(
                actor_id=actor_id,
                actor_kind="human",
                display_name=actor_id,
                roles_allowed=[role_id],
                tenant_ids=["tenant-a"],
                log_path=actor_identity_log,
            )
        grant_actor_membership(
            actor_id="human.alice",
            role_id="role.manager",
            granted_by="human.owner",
            decision_right_basis="conformance bootstrap",
            tenant_id="tenant-a",
            log_path=actor_membership_log,
        )
        build_actor_context(
            actor_id="human.alice",
            role_id="role.manager",
            tenant_id="tenant-a",
            identity_log=actor_identity_log,
            membership_log=actor_membership_log,
            enforce_registered=True,
            enforce_membership=True,
        )
        try:
            build_actor_context(
                actor_id="human.bob",
                role_id="role.reviewer",
                tenant_id="tenant-a",
                identity_log=actor_identity_log,
                membership_log=actor_membership_log,
                enforce_registered=True,
                enforce_membership=True,
            )
        except PermissionError:
            membership_denial_checked = True
        else:
            membership_denial_checked = False
        provisioning = apply_provisioning_plan(
            ProvisioningPlan(
                actors=[
                    DirectoryActor(
                        actor_id="human.carol",
                        actor_kind="human",
                        display_name="Carol",
                        auth_subject="oidc:carol",
                        identity_provider="corp-oidc",
                        roles_allowed=["role.reviewer"],
                        tenant_ids=["tenant-a"],
                    )
                ],
                memberships=[
                    DirectoryMembership(
                        actor_id="human.carol",
                        role_id="role.reviewer",
                        granted_by="service.provisioner",
                        decision_right_basis="conformance directory group",
                        tenant_id="tenant-a",
                    )
                ],
            ),
            actor_identity_log=actor_identity_log,
            actor_membership_log=actor_membership_log,
        )
        carol = build_actor_context(
            actor_id="human.carol",
            role_id="role.reviewer",
            tenant_id="tenant-a",
            identity_log=actor_identity_log,
            membership_log=actor_membership_log,
            enforce_registered=True,
            enforce_membership=True,
        )
        tenant_boundary = tenant_overlay_root(root / "tenants", "tenant-a")
        tenant_boundary.root.mkdir(parents=True)
        tenant_file = tenant_boundary.root / "roles" / "reviewer.yaml"
        tenant_file.parent.mkdir()
        tenant_file.write_text("role_id: reviewer\n", encoding="utf-8")
        validate_tenant_ref(
            actor=carol,
            tenant_id="tenant-a",
            path=tenant_file,
            boundary=tenant_boundary,
        )
        unregistered = unregistered_stateful_modules(REPO_ROOT / "src")
        if unregistered:
            raise SystemExit(f"unregistered stateful modules: {unregistered}")
        sessions = list_human_work_sessions(log_path=human_work_log)
        if not sessions:
            raise SystemExit("runtime interrupt did not create human-work session")
        if not spans:
            raise SystemExit("OTel projection produced no spans")
        if not policy.allowed:
            raise SystemExit("policy conformance decision denied unexpectedly")
        if not membership_denial_checked:
            raise SystemExit("actor membership enforcement did not reject missing membership")
        if not provisioning.actors_created or not provisioning.memberships_created:
            raise SystemExit("identity provisioning did not create actor and membership records")
        print(
            json.dumps(
                {
                    "ok": True,
                    "run_id": start["cognitive_run_id"],
                    "human_work_session": sessions[0].session_id,
                    "otel_spans": len(spans),
                    "policy_effect": policy.effect,
                    "actor_membership_enforced": True,
                    "identity_provisioning_checked": True,
                    "tenant_isolation_checked": True,
                    "state_surface_gate": "clean",
                },
                sort_keys=True,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
