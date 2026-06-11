"""Bootability check for an installed organization.

``boot_check`` is the stable entry point the installer's verify step (and other
tools) call: given an organization directory, it returns the concrete reasons
the org cannot boot as a *governed* organization — structural problems and
governance-graph defects. An empty list means the org is bootable.

It reads only the org's own files; it does not reach into kernel surface
internals, so it stays stable as the kernel evolves (spec G5).
"""

from __future__ import annotations

from collections import deque
from pathlib import Path

import yaml

from cognitive_firm.orchestration.authority_domains import (
    authority_roles_in_domains,
    load_authority_domains,
    validate_authority_domains,
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

_ROLE_REF_PREFIX = "role."


def _role_ref(ref: object) -> str | None:
    """Resolve a ``role.<id>`` reference to its role_id; ignore non-role refs."""
    if isinstance(ref, str) and ref.startswith(_ROLE_REF_PREFIX):
        return ref[len(_ROLE_REF_PREFIX):]
    return None


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

    authorities = sorted(
        rid for rid, r in roles.items() if r.get("role_class") == "authority"
    )
    domains = []
    if org_root is not None:
        try:
            domains = load_authority_domains(org_root)
        except (OSError, ValueError, TypeError) as exc:
            issues.append(f"authority domains do not parse: {exc}")
    if domains:
        issues.extend(validate_authority_domains(domains, roles=roles))
        scoped_authorities = authority_roles_in_domains(domains)
        unscoped = sorted(set(authorities) - scoped_authorities)
        if unscoped:
            issues.append(
                "authority roles are missing authority-domain records: "
                + ", ".join(unscoped)
            )
    if not authorities:
        issues.append(
            "no role has role_class 'authority' - escalation cannot terminate"
        )
    elif len(authorities) > 1 and not domains:
        issues.append(
            f"multiple authority roles ({', '.join(authorities)}) - "
            "exactly one is required unless authority domains are declared"
        )

    escalation: dict[str, list[str]] = {}
    for rid, role in roles.items():
        resolved: list[str] = []
        for ref in role.get("escalates_to") or []:
            target = _role_ref(ref)
            if target is None:
                continue  # a non-role escalation target (e.g. external)
            if target not in roles:
                issues.append(f"role {rid} escalates_to unknown role: {ref}")
            else:
                resolved.append(target)
        escalation[rid] = resolved
        for ref in role.get("delegates_to") or []:
            target = _role_ref(ref)
            if target is not None and target not in roles:
                issues.append(f"role {rid} delegates_to unknown role: {ref}")

    authority_set = set(authorities)
    for rid in roles:
        if rid in authority_set:
            continue
        if not _reaches_authority(rid, escalation, authority_set):
            issues.append(
                f"role {rid} escalation chain never reaches an authority "
                "role - the org has an ungoverned decision path"
            )
    return issues


def _reaches_authority(
    start: str,
    escalation: dict[str, list[str]],
    authority_set: set[str],
) -> bool:
    """BFS the escalation graph from ``start``; True if it reaches authority."""
    seen: set[str] = {start}
    queue: deque[str] = deque(escalation.get(start, []))
    while queue:
        node = queue.popleft()
        if node in authority_set:
            return True
        if node in seen:
            continue
        seen.add(node)
        queue.extend(escalation.get(node, []))
    return False
