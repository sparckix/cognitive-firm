"""Lightweight command-surface discovery for the org runtime.

The goal is not to be a shell parser. The goal is to make existing repo
commands legible to the daemon so it can prefer them over ad hoc scripts.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from cognitive_firm.common.paths import REPO_ROOT


MAKE_TARGET_RE = re.compile(r"^([A-Za-z0-9_.-]+):", re.MULTILINE)
MAKE_TOKEN_RE = re.compile(r"\bmake\s+([A-Za-z0-9_.-]+)\b")
PYTHON_SCRIPT_RE = re.compile(r"\bpython(?:3)?\s+([A-Za-z0-9_./-]+\.py)\b")


@dataclass(frozen=True)
class CommandAuthorityEffect:
    """Declared authority-sensitive effect for a known command.

    This is effect metadata, not execution policy. It lets surfaces expose
    which governance or learning decision class a command touches before a
    human or adapter runs it.
    """

    effect_id: str
    effect_kind: str
    description: str
    decision_class: str | None = None
    resource_class: str | None = None
    requires_explicit_scope: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CommandOperatorGuidance:
    """Projection-only guidance for a known operator path.

    This ranks existing commands for a reviewer. It is not a runner, policy,
    scheduler, or workflow stage.
    """

    path_id: str
    path_label: str
    step: int
    total_steps: int
    description: str
    optional: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


COMMAND_AUTHORITY_EFFECTS: dict[str, tuple[CommandAuthorityEffect, ...]] = {
    "make agent-fleet-review-packet": (
        CommandAuthorityEffect(
            effect_id="agent_fleet_audit_review_packet",
            effect_kind="evidence_collection",
            description=(
                "Writes a persistent agent-invocation receipt, governed-run "
                "bundle, and Markdown runbook for human review."
            ),
            decision_class="agent_fleet_audit",
            resource_class="agent_invocation_receipt",
        ),
    ),
    "make adoption-onramp-packet": (
        CommandAuthorityEffect(
            effect_id="adoption_onramp_evidence_collection",
            effect_kind="evidence_collection",
            description=(
                "Runs fixed no-cost proof commands and packages their outputs "
                "for human adoption review."
            ),
            decision_class="adoption_readiness",
            resource_class="adoption_evidence",
        ),
    ),
    "make adoption-onramp-full-replay": (
        CommandAuthorityEffect(
            effect_id="adoption_onramp_full_clean_copy_replay",
            effect_kind="evidence_replay",
            description=(
                "Stages a clean public copy and reruns the full no-cost "
                "adoption evidence collector for portability review."
            ),
            decision_class="adoption_readiness",
            resource_class="adoption_evidence",
        ),
    ),
    "make adoption-onramp-replay": (
        CommandAuthorityEffect(
            effect_id="adoption_onramp_core_clean_copy_replay",
            effect_kind="evidence_replay",
            description=(
                "Stages a clean public copy and reruns the required core "
                "adoption evidence collector for portability review."
            ),
            decision_class="adoption_readiness",
            resource_class="adoption_evidence",
        ),
    ),
    "make adoption-readiness-packet": (
        CommandAuthorityEffect(
            effect_id="adoption_readiness_review",
            effect_kind="review_packet",
            description=(
                "Renders the latest collected adoption evidence when present, "
                "or the expected proof gaps for human review."
            ),
            decision_class="adoption_readiness",
            resource_class="adoption_evidence",
        ),
    ),
    "make field-pilot-action-impact-demo": (
        CommandAuthorityEffect(
            effect_id="policy_promotion_review",
            effect_kind="governance_review_packet",
            description=(
                "Compiles action-impact evidence into a policy-promotion "
                "review packet."
            ),
            decision_class="policy_change",
            resource_class="policy_promotion_packet",
            requires_explicit_scope=True,
        ),
    ),
    "make formal-provider-bundle-demo": (
        CommandAuthorityEffect(
            effect_id="formal_provider_trust_evidence",
            effect_kind="formal_verification_evidence",
            description=(
                "Demonstrates signed formal-provider evidence in a governed "
                "run bundle."
            ),
            decision_class="formal_verification_trust",
            resource_class="formal_verification",
            requires_explicit_scope=True,
        ),
    ),
    "make learning-loop-walkthrough": (
        CommandAuthorityEffect(
            effect_id="learning_event_promotion",
            effect_kind="learning_loop_walkthrough",
            description=(
                "Shows approved learning promoted into future work context "
                "with a learning-use receipt."
            ),
            decision_class="learning_policy_change",
            resource_class="learning_event",
            requires_explicit_scope=True,
        ),
    ),
    "make langgraph-adapter-policy-preview": (
        CommandAuthorityEffect(
            effect_id="runtime_adapter_policy_preview",
            effect_kind="overlay_preview",
            description=(
                "Previews the bundled LangGraph adapter-policy overlay against "
                "a starter org and verifies it does not widen authority."
            ),
            decision_class="adapter_policy",
            resource_class="runtime_adapter_policy_package",
            requires_explicit_scope=True,
        ),
    ),
    "make release-candidate-check": (
        CommandAuthorityEffect(
            effect_id="release_candidate_gate",
            effect_kind="release_gate",
            description=(
                "Runs public, clean-container, and diff-audit release "
                "candidate checks."
            ),
            decision_class="release",
            resource_class="release_candidate",
            requires_explicit_scope=True,
        ),
    ),
}


COMMAND_OPERATOR_GUIDANCE: dict[str, CommandOperatorGuidance] = {
    "make smoke-public": CommandOperatorGuidance(
        path_id="first_review",
        path_label="First serious review",
        step=1,
        total_steps=3,
        description=(
            "Run the public gate before inspecting adoption evidence."
        ),
    ),
    "make adoption-onramp-packet": CommandOperatorGuidance(
        path_id="first_review",
        path_label="First serious review",
        step=2,
        total_steps=3,
        description=(
            "Collect the fixed no-cost evidence set for human adoption review."
        ),
    ),
    "make adoption-readiness-packet": CommandOperatorGuidance(
        path_id="first_review",
        path_label="First serious review",
        step=3,
        total_steps=3,
        description=(
            "Render the latest on-ramp handoff, or expected proof gaps when "
            "no on-ramp packet exists."
        ),
    ),
}


OPERATOR_PATH_ALIASES: dict[str, tuple[str, ...]] = {
    "first_review": (
        "first review",
        "first serious review",
        "adoption first review",
        "review adoption",
        "reviewer handoff",
    ),
}


OPERATOR_PATH_METADATA: dict[str, dict[str, Any]] = {
    "first_review": {
        "purpose": (
            "Verify the public gate, collect deterministic adoption evidence, "
            "and render a reviewer handoff."
        ),
        "use_when": (
            "Use before a first human/adopter review of the repo or release "
            "candidate."
        ),
        "not_a": [
            "command runner",
            "scheduler",
            "adoption approval",
            "workflow engine",
        ],
    },
}


@lru_cache(maxsize=1)
def list_make_targets(repo_root: Path = REPO_ROOT) -> frozenset[str]:
    makefile = repo_root / "Makefile"
    if not makefile.exists():
        return frozenset()
    text = makefile.read_text(encoding="utf-8", errors="ignore")
    targets = {
        match.group(1)
        for match in MAKE_TARGET_RE.finditer(text)
        if "%" not in match.group(1) and not match.group(1).startswith(".")
    }
    return frozenset(targets)


@lru_cache(maxsize=1)
def list_python_entrypoints(repo_root: Path = REPO_ROOT) -> frozenset[str]:
    paths = set()
    for root in (repo_root / "scripts", repo_root / "src"):
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            try:
                rel = path.relative_to(repo_root).as_posix()
            except ValueError:
                continue
            paths.add(rel)
    return frozenset(paths)


def command_surface_matches(text: str) -> list[str]:
    """Return exact repo commands referenced by a task or prompt body."""
    normalized = text.lower()
    text_tokens = _command_tokens(text)
    matches: list[str] = []

    for candidate in _operator_path_command_matches(text_tokens):
        if candidate not in matches:
            matches.append(candidate)

    for target in sorted(list_make_targets()):
        if _mentions_make_target(normalized, text_tokens, target):
            candidate = f"make {target}"
            if candidate not in matches:
                matches.append(candidate)

    for rel in sorted(list_python_entrypoints()):
        basename = Path(rel).name.lower()
        stem = Path(rel).stem
        if (
            rel.lower() in normalized
            or basename in normalized
            or _has_token_sequence(text_tokens, _command_tokens(stem))
        ):
            candidate = f"python {rel}"
            if candidate not in matches:
                matches.append(candidate)

    for target in MAKE_TOKEN_RE.findall(text):
        candidate = f"make {target}"
        if target in list_make_targets() and candidate not in matches:
            matches.append(candidate)

    for rel in PYTHON_SCRIPT_RE.findall(text):
        rel = rel.rstrip(".,);:")
        candidate = f"python {rel}"
        if rel in list_python_entrypoints() and candidate not in matches:
            matches.append(candidate)

    return matches


def command_authority_effects(command: str) -> list[CommandAuthorityEffect]:
    """Return declared authority-sensitive effects for an exact command."""

    return list(COMMAND_AUTHORITY_EFFECTS.get(command, ()))


def command_operator_guidance(command: str) -> CommandOperatorGuidance | None:
    """Return projection-only operator-path guidance for an exact command."""

    return COMMAND_OPERATOR_GUIDANCE.get(command)


def command_operator_path(path_id: str) -> dict[str, Any]:
    """Return read-only command guidance for a named operator path."""

    metadata = OPERATOR_PATH_METADATA.get(path_id, {})
    steps = [
        {
            "command": command,
            **guidance.as_dict(),
        }
        for command, guidance in sorted(
            COMMAND_OPERATOR_GUIDANCE.items(),
            key=lambda item: (item[1].path_id, item[1].step, item[0]),
        )
        if guidance.path_id == path_id and _make_target_exists_for_command(command)
    ]
    label = steps[0]["path_label"] if steps else path_id
    path = {
        "path_id": path_id,
        "path_label": label,
        "steps": steps,
        "read_only": True,
        "projection_only": True,
        "boundary": {
            "does_not_execute_commands": True,
            "does_not_schedule_work": True,
            "does_not_mutate_kernel_state": True,
            "does_not_approve_adoption": True,
        },
    }
    path.update(metadata)
    return path


def command_surface_match_records(
    text: str,
    *,
    authority_domains: list[Any] | None = None,
    roles: dict[str, dict[str, Any]] | None = None,
    source_role_id: str | None = None,
) -> list[dict[str, Any]]:
    """Return read-only command matches with declared authority effects.

    ``authority_domains`` may be omitted when the caller only needs metadata.
    When supplied, each effect is checked against the scope resolver. The check
    is still projection-only: it does not execute, schedule, approve, or mutate.
    When ``source_role_id`` and ``roles`` are supplied, each effect also traces
    whether that role can escalate to the authority resolved for the effect.
    """

    records: list[dict[str, Any]] = []
    for command in command_surface_matches(text):
        effects = [
            _authority_effect_payload(
                effect,
                authority_domains,
                roles=roles,
                source_role_id=source_role_id,
            )
            for effect in command_authority_effects(command)
        ]
        issues = [
            issue
            for effect in effects
            for issue in effect.get("issues", [])
        ]
        records.append(
            {
                "command": command,
                "command_kind": _command_kind(command),
                "executes": False,
                "operator_guidance": (
                    guidance.as_dict()
                    if (guidance := command_operator_guidance(command))
                    else None
                ),
                "authority_effects": effects,
                "authority_effect_validation": {
                    "status": _effect_validation_status(effects, issues),
                    "checked": authority_domains is not None,
                    "issues": issues,
                },
            }
        )
    return records


def command_surface_hint(text: str) -> str:
    matches = command_surface_matches(text)
    if not matches:
        return "No exact repo command matched the task text."
    return "Known repo command surface: " + ", ".join(f"`{m}`" for m in matches)


def _command_tokens(text: str) -> list[str]:
    """Split command-ish prose on separators without creating substrings."""

    return re.findall(r"[a-z0-9]+", text.lower())


def _operator_path_command_matches(text_tokens: list[str]) -> list[str]:
    path_ids = [
        path_id
        for path_id, aliases in OPERATOR_PATH_ALIASES.items()
        if any(
            _has_token_sequence(text_tokens, _command_tokens(alias))
            for alias in aliases
        )
    ]
    if not path_ids:
        return []
    return [
        command
        for command, guidance in sorted(
            COMMAND_OPERATOR_GUIDANCE.items(),
            key=lambda item: (item[1].path_id, item[1].step, item[0]),
        )
        if guidance.path_id in path_ids and _make_target_exists_for_command(command)
    ]


def _mentions_make_target(
    normalized_text: str,
    text_tokens: list[str],
    target: str,
) -> bool:
    if re.search(rf"\bmake\s+{re.escape(target.lower())}\b", normalized_text):
        return True
    return _has_token_sequence(text_tokens, _command_tokens(target))


def _has_token_sequence(tokens: list[str], sequence: list[str]) -> bool:
    if not sequence:
        return False
    width = len(sequence)
    return any(
        tokens[index:index + width] == sequence
        for index in range(len(tokens) - width + 1)
    )


def _command_kind(command: str) -> str:
    if command.startswith("make "):
        return "make_target"
    return "python_script"


def _make_target_exists_for_command(command: str) -> bool:
    if not command.startswith("make "):
        return False
    return command.removeprefix("make ") in list_make_targets()


def _authority_effect_payload(
    effect: CommandAuthorityEffect,
    authority_domains: list[Any] | None,
    *,
    roles: dict[str, dict[str, Any]] | None = None,
    source_role_id: str | None = None,
) -> dict[str, Any]:
    payload = effect.as_dict()
    resolution, issues = _resolve_authority_effect(effect, authority_domains)
    payload["authority_resolution"] = resolution
    escalation, escalation_issues = _source_role_escalation_payload(
        effect,
        authority_domains,
        roles=roles,
        source_role_id=source_role_id,
    )
    if escalation is not None:
        payload["source_role_escalation"] = escalation
        issues.extend(escalation_issues)
    payload["issues"] = issues
    return payload


def _resolve_authority_effect(
    effect: CommandAuthorityEffect,
    authority_domains: list[Any] | None,
) -> tuple[dict[str, Any], list[str]]:
    if authority_domains is None:
        return (
            {
                "status": "not_evaluated",
                "reason": "authority domains were not supplied",
            },
            [],
        )
    if not authority_domains:
        return (
            {
                "status": "single_authority_fallback",
                "reason": (
                    "no authority-domain file is configured; the T1 single "
                    "authority invariant decides this command's effects"
                ),
            },
            [],
        )

    from cognitive_firm.orchestration.authority_domains import (
        resolve_authority_domain_for_scope,
    )

    domain = resolve_authority_domain_for_scope(
        authority_domains,
        resource_class=effect.resource_class,
        decision_class=effect.decision_class,
    )
    if domain is None:
        scope = _effect_scope_label(effect)
        return (
            {
                "status": "unresolved",
                "decision_class": effect.decision_class,
                "resource_class": effect.resource_class,
            },
            [f"command effect {effect.effect_id} has no authority domain for {scope}"],
        )

    resolution = {
        "status": "resolved",
        "domain_id": domain.domain_id,
        "authority_role_id": domain.authority_role_id,
        "scope_kind": domain.scope_kind,
        "scope_id": domain.scope_id,
    }
    issues: list[str] = []
    if (
        effect.requires_explicit_scope
        and domain.scope_kind == "global"
        and (effect.decision_class or effect.resource_class)
    ):
        resolution["status"] = "global_fallback"
        issues.append(
            f"command effect {effect.effect_id} requires an explicit "
            f"authority domain for {_effect_scope_label(effect)}"
        )
    return resolution, issues


def _source_role_escalation_payload(
    effect: CommandAuthorityEffect,
    authority_domains: list[Any] | None,
    *,
    roles: dict[str, dict[str, Any]] | None,
    source_role_id: str | None,
) -> tuple[dict[str, Any] | None, list[str]]:
    if not source_role_id:
        return None, []
    if authority_domains is None:
        return (
            {
                "status": "not_evaluated",
                "role_id": source_role_id,
                "reason": "authority domains were not supplied",
            },
            [],
        )
    if roles is None:
        return (
            {
                "status": "not_evaluated",
                "role_id": source_role_id,
                "reason": "role index was not supplied",
            },
            [],
        )

    from cognitive_firm.orchestration.authority_domains import (
        trace_role_escalation_for_scope,
    )

    trace = trace_role_escalation_for_scope(
        roles,
        authority_domains,
        role_id=source_role_id,
        resource_class=effect.resource_class,
        decision_class=effect.decision_class,
    )
    payload = trace.as_dict()
    payload["status"] = "ok" if trace.reaches_authority else "blocked"
    return payload, list(trace.issues or [])


def _effect_scope_label(effect: CommandAuthorityEffect) -> str:
    parts = []
    if effect.decision_class:
        parts.append(f"decision_class:{effect.decision_class}")
    if effect.resource_class:
        parts.append(f"resource_class:{effect.resource_class}")
    return ", ".join(parts) or "unscoped effect"


def _effect_validation_status(
    effects: list[dict[str, Any]],
    issues: list[str],
) -> str:
    if not effects:
        return "not_applicable"
    if issues:
        return "blocked"
    if all(
        (effect.get("authority_resolution") or {}).get("status")
        == "not_evaluated"
        for effect in effects
    ):
        return "not_evaluated"
    return "ok"
