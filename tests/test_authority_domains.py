"""Tests for authority-domain resolution."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cognitive_firm.orchestration.actor_membership import grant_actor_membership
from cognitive_firm.orchestration.authority_domains import (
    AuthorityDomain,
    authority_domain_resource,
    load_authority_domains,
    main,
    resolve_authority_assignment_from_org,
    resolve_authority_assignment_for_scope,
    resolve_authority_role_for_scope,
    trace_role_escalation_for_scope,
    validate_authority_domains,
    validate_authority_role_graph,
)
from cognitive_firm.orchestration.resource_envelope import validate_resource


def test_load_authority_domains_accepts_wrapped_json(tmp_path: Path):
    path = tmp_path / "authority_domains.json"
    path.write_text(
        json.dumps(
            {
                "authority_domains": [
                    {
                        "domain_id": "tenant_a",
                        "authority_role_id": "role.legal_authority",
                        "scope_kind": "tenant",
                        "scope_id": "tenant-a",
                    }
                ]
            }
        )
    )

    domains = load_authority_domains(path=path)

    assert domains == [
        AuthorityDomain(
            domain_id="tenant_a",
            authority_role_id="legal_authority",
            scope_kind="tenant",
            scope_id="tenant-a",
            description="",
            metadata={},
        )
    ]


def test_authority_resolution_prefers_specific_scope():
    domains = [
        AuthorityDomain("global", "principal", "global", "*"),
        AuthorityDomain("tenant_a", "tenant_owner", "tenant", "tenant-a"),
        AuthorityDomain("project_1", "project_owner", "project", "project-1"),
    ]

    assert (
        resolve_authority_role_for_scope(
            domains, tenant_id="tenant-a", project_id="project-1"
        )
        == "project_owner"
    )
    assert resolve_authority_role_for_scope(domains, tenant_id="tenant-a") == "tenant_owner"
    assert resolve_authority_role_for_scope(domains, tenant_id="tenant-b") == "principal"


def test_authority_validation_checks_role_class_and_duplicate_scope():
    domains = [
        AuthorityDomain("a", "lead", "tenant", "tenant-a"),
        AuthorityDomain("b", "missing", "tenant", "tenant-a"),
    ]
    roles = {
        "lead": {"role_class": "manager"},
        "principal": {"role_class": "authority"},
    }

    issues = validate_authority_domains(domains, roles=roles)

    assert any("non-authority role: lead" in issue for issue in issues)
    assert any("unknown authority role: missing" in issue for issue in issues)
    assert any("duplicate authority scope: tenant:tenant-a" in issue for issue in issues)


def test_authority_role_graph_accepts_bare_escalation_ref() -> None:
    roles = {
        "principal": {"role_id": "principal", "role_class": "authority"},
        "reviewer": {
            "role_id": "reviewer",
            "role_class": "reviewer",
            "escalates_to": ["principal"],
        },
    }

    assert validate_authority_role_graph(roles) == []


def test_authority_role_graph_rejects_dead_end_escalation() -> None:
    roles = {
        "principal": {"role_id": "principal", "role_class": "authority"},
        "worker": {
            "role_id": "worker",
            "role_class": "specialist",
            "escalates_to": ["role.manager"],
        },
        "manager": {
            "role_id": "manager",
            "role_class": "manager",
            "escalates_to": [],
        },
    }

    issues = validate_authority_role_graph(roles)

    assert any(
        "role manager escalation chain never reaches an authority role" in issue
        for issue in issues
    )
    assert any(
        "role worker escalation chain never reaches an authority role" in issue
        for issue in issues
    )


def test_authority_role_graph_scopes_multiple_authorities_with_domains() -> None:
    roles = {
        "principal": {"role_id": "principal", "role_class": "authority"},
        "tenant_owner": {"role_id": "tenant_owner", "role_class": "authority"},
        "analyst": {
            "role_id": "analyst",
            "role_class": "specialist",
            "escalates_to": ["role.tenant_owner"],
        },
    }
    domains = [
        AuthorityDomain("global", "principal", "global", "*"),
        AuthorityDomain("tenant_a", "tenant_owner", "tenant", "tenant-a"),
    ]

    assert validate_authority_role_graph(roles, domains=domains) == []


def test_trace_role_escalation_for_scope_reaches_typed_authority() -> None:
    roles = {
        "principal": {"role_id": "principal", "role_class": "authority"},
        "policy_authority": {
            "role_id": "policy_authority",
            "role_class": "authority",
        },
        "manager": {
            "role_id": "manager",
            "role_class": "manager",
            "escalates_to": ["role.policy_authority"],
        },
        "worker": {
            "role_id": "worker",
            "role_class": "specialist",
            "escalates_to": ["manager"],
        },
    }
    domains = [
        AuthorityDomain("global", "principal", "global", "*"),
        AuthorityDomain(
            "policy_change",
            "policy_authority",
            "decision_class",
            "policy_change",
        ),
    ]

    trace = trace_role_escalation_for_scope(
        roles,
        domains,
        role_id="role.worker",
        decision_class="policy_change",
    )

    assert trace.reaches_authority is True
    assert trace.target_authority_role_id == "policy_authority"
    assert trace.escalation_path == ["worker", "manager", "policy_authority"]
    assert trace.issues == []


def test_trace_role_escalation_for_scope_blocks_wrong_authority_path() -> None:
    roles = {
        "principal": {"role_id": "principal", "role_class": "authority"},
        "policy_authority": {
            "role_id": "policy_authority",
            "role_class": "authority",
        },
        "worker": {
            "role_id": "worker",
            "role_class": "specialist",
            "escalates_to": ["principal"],
        },
    }
    domains = [
        AuthorityDomain("global", "principal", "global", "*"),
        AuthorityDomain(
            "policy_change",
            "policy_authority",
            "decision_class",
            "policy_change",
        ),
    ]

    assert validate_authority_role_graph(roles, domains=domains) == []
    trace = trace_role_escalation_for_scope(
        roles,
        domains,
        role_id="worker",
        decision_class="policy_change",
    )

    assert trace.reaches_authority is False
    assert trace.target_authority_role_id == "policy_authority"
    assert trace.escalation_path == []
    assert any(
        "role worker escalation chain does not reach scoped authority role "
        "policy_authority" in issue
        for issue in trace.issues or []
    )


def test_authority_domain_projects_to_resource_envelope():
    domain = AuthorityDomain(
        domain_id="tenant_a",
        authority_role_id="tenant_owner",
        scope_kind="tenant",
        scope_id="tenant-a",
        description="Tenant A authority",
        metadata={"risk_tier": "high"},
    )

    payload = authority_domain_resource(domain).as_dict()

    assert validate_resource(payload) == []
    assert payload["kind"] == "AuthorityDomain"
    assert payload["metadata"]["name"] == "tenant_a"
    assert payload["metadata"]["tenant_id"] == "tenant-a"
    assert payload["metadata"]["labels"]["scope_kind"] == "tenant"
    assert payload["metadata"]["labels"]["authority_role_id"] == "tenant_owner"
    assert payload["metadata"]["annotations"]["risk_tier"] == "high"
    assert payload["spec"]["scope_id"] == "tenant-a"
    assert {"rel": "authority_role", "href": "role.tenant_owner"} in payload["links"]
    assert {"rel": "scope", "href": "tenant:tenant-a"} in payload["links"]


def test_authority_assignment_lists_active_holders(tmp_path: Path):
    membership_log = tmp_path / "memberships.jsonl"
    now = datetime.now(timezone.utc)
    grant_actor_membership(
        actor_id="agent.current",
        role_id="tenant_owner",
        granted_by="human.root",
        decision_right_basis="bounded tenant authority",
        tenant_id="tenant-a",
        log_path=membership_log,
    )
    grant_actor_membership(
        actor_id="agent.expired",
        role_id="tenant_owner",
        granted_by="human.root",
        decision_right_basis="expired delegation",
        tenant_id="tenant-a",
        expires_at_utc=(now - timedelta(days=1)).isoformat(),
        log_path=membership_log,
    )
    domains = [
        AuthorityDomain("tenant_a", "tenant_owner", "tenant", "tenant-a"),
    ]

    resolution = resolve_authority_assignment_for_scope(
        domains,
        tenant_id="tenant-a",
        actor_membership_log=membership_log,
        now=now,
    )

    assert resolution.authority_role_id == "tenant_owner"
    assert resolution.actor_ids == ["agent.current"]
    assert resolution.domain_id == "tenant_a"


def test_authority_assignment_from_org_preserves_single_authority_fallback(tmp_path: Path):
    org_root = tmp_path / "org"
    roles = org_root / "roles"
    roles.mkdir(parents=True)
    (roles / "principal.yaml").write_text(
        "role_id: principal\nrole_class: authority\n"
    )
    membership_log = tmp_path / "memberships.jsonl"
    grant_actor_membership(
        actor_id="service.root",
        role_id="principal",
        granted_by="human.root",
        decision_right_basis="service automation agreement",
        log_path=membership_log,
    )

    resolution = resolve_authority_assignment_from_org(
        org_root,
        actor_membership_log=membership_log,
    )

    assert resolution.authority_role_id == "principal"
    assert resolution.actor_ids == ["service.root"]


def test_authority_domains_cli_resolves_scope(tmp_path: Path, capsys):
    org_root = tmp_path / "org"
    roles = org_root / "roles"
    roles.mkdir(parents=True)
    (roles / "principal.yaml").write_text(
        "role_id: principal\nrole_class: authority\n"
    )
    (roles / "tenant_owner.yaml").write_text(
        "role_id: tenant_owner\nrole_class: authority\n"
    )
    domains = org_root / "authority_domains" / "authority_domains.json"
    domains.parent.mkdir()
    domains.write_text(
        json.dumps(
            {
                "authority_domains": [
                    {
                        "domain_id": "global",
                        "authority_role_id": "role.principal",
                        "scope_kind": "global",
                        "scope_id": "*",
                    },
                    {
                        "domain_id": "tenant_a",
                        "authority_role_id": "role.tenant_owner",
                        "scope_kind": "tenant",
                        "scope_id": "tenant-a",
                    },
                ]
            }
        )
    )

    assert main(["--org-root", str(org_root), "resolve", "--tenant-id", "tenant-a"]) == 0
    assert capsys.readouterr().out.strip() == "role.tenant_owner\tNO_ACTIVE_ACTOR"
    assert main(["--org-root", str(org_root), "validate"]) == 0
    assert capsys.readouterr().out.strip() == "OK"


def test_authority_domains_cli_traces_scoped_escalation(tmp_path: Path, capsys):
    org_root = tmp_path / "org"
    roles = org_root / "roles"
    roles.mkdir(parents=True)
    (roles / "principal.yaml").write_text(
        "role_id: principal\nrole_class: authority\nescalates_to: []\n"
    )
    (roles / "policy_authority.yaml").write_text(
        "role_id: policy_authority\nrole_class: authority\nescalates_to: []\n"
    )
    (roles / "worker.yaml").write_text(
        "role_id: worker\nrole_class: specialist\n"
        "escalates_to:\n  - role.policy_authority\n"
    )
    domains = org_root / "authority_domains" / "authority_domains.json"
    domains.parent.mkdir()
    domains.write_text(
        json.dumps(
            {
                "authority_domains": [
                    {
                        "domain_id": "global",
                        "authority_role_id": "role.principal",
                        "scope_kind": "global",
                        "scope_id": "*",
                    },
                    {
                        "domain_id": "policy_change",
                        "authority_role_id": "role.policy_authority",
                        "scope_kind": "decision_class",
                        "scope_id": "policy_change",
                    },
                ]
            }
        )
    )

    rc = main(
        [
            "--org-root",
            str(org_root),
            "trace-escalation",
            "--role-id",
            "role.worker",
            "--decision-class",
            "policy_change",
        ]
    )

    assert rc == 0
    assert capsys.readouterr().out.strip() == (
        "role.worker -> role.policy_authority"
    )


def test_authority_domains_cli_lists_resource_envelopes(tmp_path: Path, capsys):
    org_root = tmp_path / "org"
    domains = org_root / "authority_domains" / "authority_domains.json"
    domains.parent.mkdir(parents=True)
    domains.write_text(
        json.dumps(
            {
                "authority_domains": [
                    {
                        "domain_id": "global",
                        "authority_role_id": "role.principal",
                        "scope_kind": "global",
                        "scope_id": "*",
                    }
                ]
            }
        )
    )

    assert main(["--org-root", str(org_root), "list", "--resource"]) == 0
    payloads = [json.loads(line) for line in capsys.readouterr().out.splitlines()]

    assert [payload["kind"] for payload in payloads] == ["AuthorityDomain"]
    assert payloads[0]["metadata"]["name"] == "global"
    assert payloads[0]["spec"]["authority_role_id"] == "principal"


def test_authority_domains_cli_validate_fails_on_bad_role(tmp_path: Path, capsys):
    org_root = tmp_path / "org"
    roles = org_root / "roles"
    roles.mkdir(parents=True)
    (roles / "lead.yaml").write_text("role_id: lead\nrole_class: manager\n")
    domains = org_root / "authority_domains" / "authority_domains.json"
    domains.parent.mkdir()
    domains.write_text(
        json.dumps(
            {
                "authority_domains": [
                    {
                        "domain_id": "bad",
                        "authority_role_id": "role.lead",
                        "scope_kind": "tenant",
                        "scope_id": "tenant-a",
                    }
                ]
            }
        )
    )

    assert main(["--org-root", str(org_root), "validate"]) == 1
    assert "non-authority role: lead" in capsys.readouterr().out


def test_authority_domains_cli_validate_catches_dead_end_escalation(
    tmp_path: Path,
    capsys,
) -> None:
    org_root = tmp_path / "org"
    roles = org_root / "roles"
    roles.mkdir(parents=True)
    (roles / "principal.yaml").write_text(
        "role_id: principal\nrole_class: authority\nescalates_to: []\n"
    )
    (roles / "manager.yaml").write_text(
        "role_id: manager\nrole_class: manager\nescalates_to: []\n"
    )
    domains = org_root / "authority_domains" / "authority_domains.json"
    domains.parent.mkdir()
    domains.write_text(
        json.dumps(
            {
                "authority_domains": [
                    {
                        "domain_id": "global",
                        "authority_role_id": "role.principal",
                        "scope_kind": "global",
                        "scope_id": "*",
                    }
                ]
            }
        )
    )

    assert main(["--org-root", str(org_root), "validate"]) == 1
    assert "role manager escalation chain never reaches an authority role" in (
        capsys.readouterr().out
    )
