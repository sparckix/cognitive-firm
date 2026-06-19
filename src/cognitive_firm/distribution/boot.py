"""Bootability check for an installed organization.

``boot_check`` is the stable entry point the installer's verify step (and other
tools) call: given an organization directory, it returns the concrete reasons
the org cannot boot as a *governed* organization — structural problems and
governance-graph defects. An empty list means the org is bootable.

It reads only the org's own files; it does not reach into kernel surface
internals, so it stays stable as the kernel evolves (spec G5).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from cognitive_firm.orchestration.authority_domains import (
    load_authority_domains,
    validate_authority_role_graph,
)

# Top-level keys every role.yaml must carry (role.v1 schema).
ROLE_REQUIRED_KEYS = (
    "schema_version",
    "role_id",
    "role_class",
    "description",
    "authorized_paths",
    "forbidden_paths",
    "delegates_to",
    "escalates_to",
    "budget",
)

def boot_check(org_root: Path) -> list[str]:
    """Return the reasons an installed org cannot boot. Empty list = bootable.

    Structural checks: roles exist, parse, carry the role.v1 keys, and their
    mandate files resolve and are non-empty. Governance-graph checks: see
    ``_check_governance_graph``.
    """
    org_root = Path(org_root)
    issues: list[str] = []

    roles_dir = org_root / "roles"
    role_files = sorted(roles_dir.glob("*.yaml")) if roles_dir.is_dir() else []
    if not role_files:
        issues.append("no role files under roles/ - organization cannot boot")
        return issues

    roles: dict[str, dict] = {}
    for role_file in role_files:
        try:
            data = yaml.safe_load(role_file.read_text())
        except yaml.YAMLError as exc:
            issues.append(f"role {role_file.name} does not parse: {exc}")
            continue
        if not isinstance(data, dict):
            issues.append(f"role {role_file.name} is not a mapping")
            continue
        missing = [k for k in ROLE_REQUIRED_KEYS if k not in data]
        if missing:
            issues.append(
                f"role {role_file.name} missing keys: {', '.join(missing)}"
            )
        role_id = data.get("role_id")
        if role_id:
            if str(role_id) in roles:
                issues.append(f"duplicate role_id: {role_id}")
            roles[str(role_id)] = data
        mandate_path = data.get("mandate_path")
        if mandate_path:
            mpath = org_root / str(mandate_path)
            if not mpath.is_file():
                issues.append(
                    f"role {role_file.name} mandate_path does not resolve: "
                    f"{mandate_path}"
                )
            elif not mpath.read_text().strip():
                issues.append(
                    f"role {role_file.name} mandate file is empty: "
                    f"{mandate_path}"
                )

    if not roles:
        return issues

    issues.extend(_check_governance_graph(roles, org_root=org_root))
    return issues


def _check_governance_graph(
    roles: dict[str, dict],
    *,
    org_root: Path | None = None,
) -> list[str]:
    """Check the escalation/delegation graph is governable.

    - exactly one ``authority`` role, unless authority domains are declared;
    - if domains are declared, every authority role is scoped by a domain;
    - every ``escalates_to`` / ``delegates_to`` role reference resolves;
    - every non-authority role's escalation chain reaches an authority role
      (no dead end, no cycle that never terminates at authority).

    Note: a deeper check — that the terminal authority's mandate covers the
    *decision class* being escalated — needs typed decision classes the role
    schema does not yet carry; reaching an authority at all is the v1 bar.
    """
    issues: list[str] = []

    domains = []
    if org_root is not None:
        try:
            domains = load_authority_domains(org_root)
        except (OSError, ValueError, TypeError) as exc:
            issues.append(f"authority domains do not parse: {exc}")
    issues.extend(validate_authority_role_graph(roles, domains=domains))
    return issues
