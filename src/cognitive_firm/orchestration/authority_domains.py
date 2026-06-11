"""Authority domains for multi-authority cognitive-firm deployments.

The T1 kernel assumes one boot authority role. Enterprise deployments need
separate authority roles for departments, projects, tenants, operating
units, or decision classes. This module adds the smallest reusable kernel
surface for that: a domain record and deterministic scope resolution.

It does not implement IAM, SSO, HRIS, tenant isolation, or approval policy.
Those systems can provision roles and memberships; the kernel only records
which authority role owns which scope.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from cognitive_firm.common.paths import ORG_ROOT_DIR
from cognitive_firm.orchestration.resource_envelope import KernelResource, make_resource


AuthorityScopeKind = Literal[
    "global",
    "tenant",
    "project",
    "operating_unit",
    "resource_class",
    "decision_class",
]

VALID_SCOPE_KINDS: set[str] = {
    "global",
    "tenant",
    "project",
    "operating_unit",
    "resource_class",
    "decision_class",
}

DEFAULT_AUTHORITY_DOMAINS_PATH = (
    ORG_ROOT_DIR / "authority_domains" / "authority_domains.json"
)

_ROLE_REF_PREFIX = "role."
_SCOPE_PRIORITY = (
    "operating_unit",
    "project",
    "tenant",
    "decision_class",
    "resource_class",
    "global",
)


@dataclass(frozen=True)
class AuthorityDomain:
    """One accountable authority domain.

    ``authority_role_id`` may be written as ``role.foo`` or ``foo``. The
    normalized object always stores the bare role id.
    """

    domain_id: str
    authority_role_id: str
    scope_kind: AuthorityScopeKind
    scope_id: str
    description: str = ""
    metadata: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AuthorityResolution:
    """Resolved authority for one scoped governance interrupt."""

    authority_role_id: str | None
    actor_ids: list[str]
    domain_id: str | None = None
    scope_kind: str | None = None
    scope_id: str | None = None

    @property
    def resolved(self) -> bool:
        return self.authority_role_id is not None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self) | {"resolved": self.resolved}


def authority_domains_path(org_root: Path) -> Path:
    return Path(org_root) / "authority_domains" / "authority_domains.json"


def load_authority_domains(
    org_root: Path | None = None,
    *,
    path: Path | None = None,
) -> list[AuthorityDomain]:
    """Load authority-domain records.

    Accepted file shapes:

    - ``[{...}, {...}]``
    - ``{"authority_domains": [{...}]}``
    - ``{"domains": [{...}]}``
    """

    source = path or authority_domains_path(org_root or ORG_ROOT_DIR)
    if not source.exists():
        return []
    raw = json.loads(source.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        rows = raw.get("authority_domains", raw.get("domains"))
    else:
        rows = raw
    if not isinstance(rows, list):
        raise ValueError("authority domains file must contain a list of domains")
    return [_parse_domain(row) for row in rows]


def validate_authority_domains(
    domains: list[AuthorityDomain],
    *,
    roles: dict[str, dict[str, Any]] | None = None,
) -> list[str]:
    """Return validation issues for domain records.

    When ``roles`` is supplied, each authority must reference an existing role
    whose ``role_class`` is ``authority``.
    """

    issues: list[str] = []
    seen_domain_ids: set[str] = set()
    seen_scopes: set[tuple[str, str]] = set()
    for domain in domains:
        if not domain.domain_id.strip():
            issues.append("authority domain has empty domain_id")
        if domain.domain_id in seen_domain_ids:
            issues.append(f"duplicate authority domain_id: {domain.domain_id}")
        seen_domain_ids.add(domain.domain_id)

        if domain.scope_kind not in VALID_SCOPE_KINDS:
            issues.append(
                f"authority domain {domain.domain_id} has invalid scope_kind: "
                f"{domain.scope_kind}"
            )
        if not domain.scope_id.strip():
            issues.append(
                f"authority domain {domain.domain_id} has empty scope_id"
            )
        if domain.scope_kind == "global" and domain.scope_id != "*":
            issues.append(
                f"authority domain {domain.domain_id} global scope_id must be '*'"
            )
        scope_key = (domain.scope_kind, domain.scope_id)
        if scope_key in seen_scopes:
            issues.append(
                f"duplicate authority scope: {domain.scope_kind}:{domain.scope_id}"
            )
        seen_scopes.add(scope_key)

        if not domain.authority_role_id.strip():
            issues.append(
                f"authority domain {domain.domain_id} has empty authority_role_id"
            )
        if roles is not None:
            role = roles.get(domain.authority_role_id)
            if role is None:
                issues.append(
                    f"authority domain {domain.domain_id} references unknown "
                    f"authority role: {domain.authority_role_id}"
                )
            elif role.get("role_class") != "authority":
                issues.append(
                    f"authority domain {domain.domain_id} references "
                    f"non-authority role: {domain.authority_role_id}"
                )
    return issues


def resolve_authority_role_for_scope(
    domains: list[AuthorityDomain],
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
    operating_unit_id: str | None = None,
    resource_class: str | None = None,
    decision_class: str | None = None,
) -> str | None:
    """Resolve the authority role for a scoped governance interrupt.

    More specific scopes win. If two domains match at the same specificity,
    resolution fails closed with ``None``.
    """

    domain = resolve_authority_domain_for_scope(
        domains,
        tenant_id=tenant_id,
        project_id=project_id,
        operating_unit_id=operating_unit_id,
        resource_class=resource_class,
        decision_class=decision_class,
    )
    return domain.authority_role_id if domain else None


def resolve_authority_domain_for_scope(
    domains: list[AuthorityDomain],
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
    operating_unit_id: str | None = None,
    resource_class: str | None = None,
    decision_class: str | None = None,
) -> AuthorityDomain | None:
    """Resolve the authority domain for a scoped governance interrupt."""

    candidates = _scope_candidates(
        tenant_id=tenant_id,
        project_id=project_id,
        operating_unit_id=operating_unit_id,
        resource_class=resource_class,
        decision_class=decision_class,
    )
    for scope_kind in _SCOPE_PRIORITY:
        scope_id = candidates.get(scope_kind)
        if scope_id is None:
            continue
        matches = [
            domain
            for domain in domains
            if domain.scope_kind == scope_kind and domain.scope_id == scope_id
        ]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            return None
    return None


def resolve_authority_assignment_for_scope(
    domains: list[AuthorityDomain],
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
    operating_unit_id: str | None = None,
    resource_class: str | None = None,
    decision_class: str | None = None,
    actor_membership_log: Path | None = None,
    now: datetime | None = None,
) -> AuthorityResolution:
    """Resolve the authority role and active actors for a scoped interrupt."""

    domain = resolve_authority_domain_for_scope(
        domains,
        tenant_id=tenant_id,
        project_id=project_id,
        operating_unit_id=operating_unit_id,
        resource_class=resource_class,
        decision_class=decision_class,
    )
    if domain is None:
        return AuthorityResolution(authority_role_id=None, actor_ids=[])

    from cognitive_firm.orchestration.actor_membership import (
        list_active_actor_memberships,
    )

    memberships = list_active_actor_memberships(
        role_id=domain.authority_role_id,
        tenant_id=tenant_id,
        project_id=project_id,
        log_path=actor_membership_log,
        now=now,
    )
    return AuthorityResolution(
        authority_role_id=domain.authority_role_id,
        actor_ids=sorted({membership.actor_id for membership in memberships}),
        domain_id=domain.domain_id,
        scope_kind=domain.scope_kind,
        scope_id=domain.scope_id,
    )


def resolve_authority_role_from_org(
    org_root: Path,
    *,
    authority_domains_file: Path | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    operating_unit_id: str | None = None,
    resource_class: str | None = None,
    decision_class: str | None = None,
) -> str | None:
    """Resolve authority role from an org root, preserving the T1 fallback."""
    domains = load_authority_domains(org_root, path=authority_domains_file)
    if domains:
        return resolve_authority_role_for_scope(
            domains,
            tenant_id=tenant_id,
            project_id=project_id,
            operating_unit_id=operating_unit_id,
            resource_class=resource_class,
            decision_class=decision_class,
        )
    authorities = sorted(
        role_id
        for role_id, role in _load_role_index(org_root).items()
        if role.get("role_class") == "authority"
    )
    return authorities[0] if len(authorities) == 1 else None


def resolve_authority_assignment_from_org(
    org_root: Path,
    *,
    authority_domains_file: Path | None = None,
    actor_membership_log: Path | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    operating_unit_id: str | None = None,
    resource_class: str | None = None,
    decision_class: str | None = None,
    now: datetime | None = None,
) -> AuthorityResolution:
    """Resolve authority role and active actors from an org root."""
    domains = load_authority_domains(org_root, path=authority_domains_file)
    if domains:
        return resolve_authority_assignment_for_scope(
            domains,
            tenant_id=tenant_id,
            project_id=project_id,
            operating_unit_id=operating_unit_id,
            resource_class=resource_class,
            decision_class=decision_class,
            actor_membership_log=actor_membership_log,
            now=now,
        )

    role_id = resolve_authority_role_from_org(
        org_root,
        tenant_id=tenant_id,
        project_id=project_id,
        operating_unit_id=operating_unit_id,
        resource_class=resource_class,
        decision_class=decision_class,
    )
    if role_id is None:
        return AuthorityResolution(authority_role_id=None, actor_ids=[])

    from cognitive_firm.orchestration.actor_membership import (
        list_active_actor_memberships,
    )

    memberships = list_active_actor_memberships(
        role_id=role_id,
        tenant_id=tenant_id,
        project_id=project_id,
        log_path=actor_membership_log,
        now=now,
    )
    return AuthorityResolution(
        authority_role_id=role_id,
        actor_ids=sorted({membership.actor_id for membership in memberships}),
    )


def authority_roles_in_domains(domains: list[AuthorityDomain]) -> set[str]:
    return {domain.authority_role_id for domain in domains}


def authority_domain_resource(domain: AuthorityDomain) -> KernelResource:
    """Project an authority-domain record into the common resource envelope.

    The JSON file remains canonical. This projection lets admin tools,
    adapter conformance checks, and migration previews inspect scoped authority
    without needing a custom parser for this primitive.
    """
    tenant_id = domain.scope_id if domain.scope_kind == "tenant" else None
    project_id = domain.scope_id if domain.scope_kind == "project" else None
    labels = {
        "scope_kind": domain.scope_kind,
        "scope_id": domain.scope_id,
        "authority_role_id": domain.authority_role_id,
    }
    links = [
        {"rel": "authority_role", "href": f"role.{domain.authority_role_id}"},
        {"rel": "scope", "href": f"{domain.scope_kind}:{domain.scope_id}"},
    ]
    return make_resource(
        kind="AuthorityDomain",
        name=domain.domain_id,
        resource_id=domain.domain_id,
        tenant_id=tenant_id,
        project_id=project_id,
        stability="alpha",
        labels=labels,
        annotations={
            key: str(value)
            for key, value in (domain.metadata or {}).items()
            if isinstance(key, str) and value is not None
        },
        spec={
            "authority_role_id": domain.authority_role_id,
            "scope_kind": domain.scope_kind,
            "scope_id": domain.scope_id,
            "description": domain.description,
        },
        status={
            "resolvable": True,
        },
        links=links,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect cognitive-firm authority domains."
    )
    parser.add_argument(
        "--org-root",
        type=Path,
        default=ORG_ROOT_DIR,
        help="Organization root. Defaults to ORG_ROOT or the bundled org root.",
    )
    parser.add_argument(
        "--path",
        type=Path,
        help="Explicit authority-domains JSON path.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    list_parser = sub.add_parser("list", help="List authority-domain records.")
    list_parser.add_argument("--json", action="store_true", help="Emit JSON.")
    list_parser.add_argument("--resource", action="store_true", help="Emit resource envelopes.")

    validate_parser = sub.add_parser(
        "validate",
        help="Validate authority-domain records against role files.",
    )
    validate_parser.add_argument("--json", action="store_true", help="Emit JSON.")

    resolve = sub.add_parser(
        "resolve",
        help="Resolve the authority role for a scope.",
    )
    resolve.add_argument("--tenant-id")
    resolve.add_argument("--project-id")
    resolve.add_argument("--operating-unit-id")
    resolve.add_argument("--resource-class")
    resolve.add_argument("--decision-class")
    resolve.add_argument(
        "--actor-membership-log",
        type=Path,
        help="Optional actor membership JSONL path; includes active holders in output.",
    )
    resolve.add_argument("--json", action="store_true", help="Emit JSON.")

    args = parser.parse_args(argv)
    domains = load_authority_domains(args.org_root, path=args.path)

    if args.cmd == "list":
        rows = [domain.as_dict() for domain in domains]
        if args.resource:
            for domain in domains:
                print(json.dumps(authority_domain_resource(domain).as_dict(), sort_keys=True))
            return 0
        if args.json:
            print(json.dumps({"authority_domains": rows}, sort_keys=True))
        else:
            for domain in domains:
                print(
                    f"{domain.domain_id}\t{domain.scope_kind}:{domain.scope_id}"
                    f"\trole.{domain.authority_role_id}"
                )
        return 0

    if args.cmd == "validate":
        roles = _load_role_index(args.org_root)
        issues = validate_authority_domains(domains, roles=roles)
        if args.json:
            print(
                json.dumps(
                    {"ok": not issues, "issues": issues},
                    sort_keys=True,
                )
            )
        else:
            if issues:
                for issue in issues:
                    print(issue)
            else:
                print("OK")
        return 0 if not issues else 1

    if args.cmd == "resolve":
        resolution = resolve_authority_assignment_from_org(
            args.org_root,
            authority_domains_file=args.path,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            operating_unit_id=args.operating_unit_id,
            resource_class=args.resource_class,
            decision_class=args.decision_class,
            actor_membership_log=args.actor_membership_log,
        )
        if args.json:
            print(json.dumps(resolution.as_dict(), sort_keys=True))
        else:
            if resolution.authority_role_id:
                actors = (
                    ",".join(resolution.actor_ids)
                    if resolution.actor_ids
                    else "NO_ACTIVE_ACTOR"
                )
                print(f"role.{resolution.authority_role_id}\t{actors}")
            else:
                print("UNRESOLVED")
        return 0 if resolution.authority_role_id else 1

    return 1


def _parse_domain(row: object) -> AuthorityDomain:
    if not isinstance(row, dict):
        raise ValueError("authority domain entries must be objects")
    scope_kind = str(row.get("scope_kind") or "").strip()
    if scope_kind not in VALID_SCOPE_KINDS:
        # Preserve the value for validate_authority_domains to report cleanly.
        scope_kind_typed = scope_kind  # type: ignore[assignment]
    else:
        scope_kind_typed = scope_kind  # type: ignore[assignment]
    return AuthorityDomain(
        domain_id=str(row.get("domain_id") or "").strip(),
        authority_role_id=_normalize_role_id(row.get("authority_role_id")),
        scope_kind=scope_kind_typed,
        scope_id=str(row.get("scope_id") or "").strip(),
        description=str(row.get("description") or "").strip(),
        metadata=row.get("metadata") if isinstance(row.get("metadata"), dict) else {},
    )


def _normalize_role_id(value: object) -> str:
    text = str(value or "").strip()
    if text.startswith(_ROLE_REF_PREFIX):
        return text[len(_ROLE_REF_PREFIX):]
    return text


def _scope_candidates(
    *,
    tenant_id: str | None = None,
    project_id: str | None = None,
    operating_unit_id: str | None = None,
    resource_class: str | None = None,
    decision_class: str | None = None,
) -> dict[str, str | None]:
    return {
        "operating_unit": operating_unit_id,
        "project": project_id,
        "tenant": tenant_id,
        "decision_class": decision_class,
        "resource_class": resource_class,
        "global": "*",
    }


def _load_role_index(org_root: Path) -> dict[str, dict[str, Any]]:
    import yaml

    roles_dir = Path(org_root) / "roles"
    roles: dict[str, dict[str, Any]] = {}
    if not roles_dir.is_dir():
        return roles
    for role_file in sorted(roles_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(role_file.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if isinstance(data, dict) and data.get("role_id"):
            roles[str(data["role_id"])] = data
    return roles


if __name__ == "__main__":
    raise SystemExit(main())
