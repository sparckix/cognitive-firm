"""Deterministic policy decision records.

Policies answer bounded questions such as "may this actor mutate this
resource?". They do not replace mandates or human judgment; they make one
decision and the evidence for it auditable.
"""

from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from cognitive_firm.common.paths import ORG_ROOT_DIR
from cognitive_firm.orchestration.resource_envelope import KernelResource, make_resource


PolicyEffect = Literal["allow", "deny"]
PolicyDecisionStatus = Literal["matched", "defaulted"]

DEFAULT_POLICY_DECISIONS_LOG = ORG_ROOT_DIR / "policy" / "policy_decisions.jsonl"
VALID_EFFECTS = {"allow", "deny"}


@dataclass(frozen=True)
class PolicyDecisionRequest:
    action: str
    actor_id: str
    resource_ref: str
    tenant_id: str | None = None
    role_id: str | None = None
    project_id: str | None = None
    context: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PolicyRule:
    rule_id: str
    effect: PolicyEffect
    reason: str
    match: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PolicyDecisionResult:
    decision_id: str
    decided_at_utc: str
    effect: PolicyEffect
    status: PolicyDecisionStatus
    reason: str
    request: PolicyDecisionRequest
    matched_rule_id: str | None = None
    policy_ref: str | None = None
    source_surface: str | None = None
    source_decision_ref: str | None = None
    required_approval: str | None = None
    terminal: bool | None = None
    matched_paths: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        return self.effect == "allow"

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["allowed"] = self.allowed
        return payload


def evaluate_policy(
    request: PolicyDecisionRequest,
    *,
    rules: list[PolicyRule | dict[str, Any]] | None = None,
    default_effect: PolicyEffect | str = "deny",
    default_reason: str = "no policy rule matched",
    policy_ref: str | None = None,
    source_surface: str | None = None,
    source_decision_ref: str | None = None,
    required_approval: str | None = None,
    terminal: bool | None = None,
    matched_paths: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    log_path: Path | None = None,
    record: bool = True,
) -> PolicyDecisionResult:
    """Evaluate first-match policy rules and optionally append a decision row."""
    _validate_request(request)
    default = _validate_effect(str(default_effect))
    normalized = [_normalize_rule(rule) for rule in (rules or [])]
    matched = next((rule for rule in normalized if _rule_matches(rule, request)), None)
    if matched is None:
        result = PolicyDecisionResult(
            decision_id=f"pdec_{uuid.uuid4().hex[:12]}",
            decided_at_utc=_now_iso(),
            effect=default,
            status="defaulted",
            reason=default_reason,
            request=request,
            policy_ref=policy_ref,
            source_surface=source_surface,
            source_decision_ref=source_decision_ref,
            required_approval=required_approval,
            terminal=terminal,
            matched_paths=matched_paths or [],
            evidence_refs=evidence_refs or [],
            metadata=metadata or {},
        )
    else:
        result = PolicyDecisionResult(
            decision_id=f"pdec_{uuid.uuid4().hex[:12]}",
            decided_at_utc=_now_iso(),
            effect=matched.effect,
            status="matched",
            reason=matched.reason,
            request=request,
            matched_rule_id=matched.rule_id,
            policy_ref=policy_ref,
            source_surface=source_surface,
            source_decision_ref=source_decision_ref,
            required_approval=required_approval,
            terminal=terminal,
            matched_paths=matched_paths or [],
            evidence_refs=evidence_refs or [],
            metadata=metadata or {},
        )
    if record:
        append_policy_decision(result, log_path=log_path)
    return result


def append_policy_decision(
    result: PolicyDecisionResult,
    *,
    log_path: Path | None = None,
) -> PolicyDecisionResult:
    path = log_path or DEFAULT_POLICY_DECISIONS_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(result.as_dict(), sort_keys=True) + "\n")
    return result


def list_policy_decisions(
    *,
    effect: PolicyEffect | str | None = None,
    actor_id: str | None = None,
    resource_ref: str | None = None,
    tenant_id: str | None = None,
    log_path: Path | None = None,
) -> list[PolicyDecisionResult]:
    if effect is not None:
        effect = _validate_effect(str(effect))
    out: list[PolicyDecisionResult] = []
    for row in _read_jsonl(log_path or DEFAULT_POLICY_DECISIONS_LOG):
        request = PolicyDecisionRequest(**row.pop("request"))
        row.pop("allowed", None)
        result = PolicyDecisionResult(request=request, **row)
        if effect is not None and result.effect != effect:
            continue
        if actor_id is not None and result.request.actor_id != actor_id:
            continue
        if resource_ref is not None and result.request.resource_ref != resource_ref:
            continue
        if tenant_id is not None and result.request.tenant_id != tenant_id:
            continue
        out.append(result)
    return out


def policy_decision_from_authorization(
    *,
    authorization: Any,
    action: str,
    actor_id: str,
    resource_ref: str,
    source_surface: str = "task_authorization",
    source_decision_ref: str | None = None,
    tenant_id: str | None = None,
    role_id: str | None = None,
    project_id: str | None = None,
    context: dict[str, Any] | None = None,
    policy_ref: str | None = None,
    evidence_refs: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    log_path: Path | None = None,
    record: bool = True,
) -> PolicyDecisionResult:
    """Wrap an existing AuthorizationDecision-like object as an audit record."""
    request = PolicyDecisionRequest(
        action=action,
        actor_id=actor_id,
        resource_ref=resource_ref,
        tenant_id=tenant_id,
        role_id=role_id,
        project_id=project_id,
        context=context or {},
    )
    result = PolicyDecisionResult(
        decision_id=f"pdec_{uuid.uuid4().hex[:12]}",
        decided_at_utc=_now_iso(),
        effect="allow" if bool(getattr(authorization, "allowed")) else "deny",
        status="matched",
        reason=str(getattr(authorization, "reason", "")),
        request=request,
        policy_ref=policy_ref,
        source_surface=source_surface,
        source_decision_ref=source_decision_ref,
        required_approval=getattr(authorization, "required_approval", None),
        terminal=getattr(authorization, "terminal", None),
        matched_paths=list(getattr(authorization, "matched_paths", ()) or ()),
        evidence_refs=evidence_refs or [],
        metadata=metadata or {},
    )
    if record:
        append_policy_decision(result, log_path=log_path)
    return result


def policy_decision_resource(result: PolicyDecisionResult) -> KernelResource:
    """Project a policy decision into the common resource envelope.

    The append-only decision row remains canonical. The resource view is for
    adapters, dashboards, migration checks, and conformance fixtures that need
    the same object shape used by other kernel-owned state.
    """
    request = result.request
    labels = {
        "effect": result.effect,
        "status": result.status,
        "action": request.action,
        "actor_id": request.actor_id,
    }
    if request.role_id:
        labels["role_id"] = request.role_id
    if result.matched_rule_id:
        labels["matched_rule_id"] = result.matched_rule_id
    links = [
        {"rel": "actor", "href": request.actor_id},
        {"rel": "resource", "href": request.resource_ref},
    ]
    if request.role_id:
        links.append({"rel": "role", "href": request.role_id})
    if result.policy_ref:
        links.append({"rel": "policy", "href": result.policy_ref})
    if result.source_decision_ref:
        links.append({"rel": "source_decision", "href": result.source_decision_ref})
    for ref in result.evidence_refs:
        links.append({"rel": "evidence", "href": ref})
    return make_resource(
        kind="PolicyDecision",
        name=result.decision_id,
        resource_id=result.decision_id,
        tenant_id=request.tenant_id,
        project_id=request.project_id,
        stability="alpha",
        labels=labels,
        annotations={
            key: str(value)
            for key, value in result.metadata.items()
            if isinstance(key, str) and value is not None
        },
        spec={
            "request": request.as_dict(),
            "policy_ref": result.policy_ref,
            "matched_rule_id": result.matched_rule_id,
            "source_surface": result.source_surface,
            "source_decision_ref": result.source_decision_ref,
            "reason": result.reason,
            "matched_paths": result.matched_paths,
            "evidence_refs": result.evidence_refs,
        },
        status={
            "effect": result.effect,
            "allowed": result.allowed,
            "status": result.status,
            "required_approval": result.required_approval,
            "terminal": result.terminal,
            "decided_at_utc": result.decided_at_utc,
        },
        links=links,
    )


def _validate_request(request: PolicyDecisionRequest) -> None:
    if not request.action.strip():
        raise ValueError("action is required")
    if not request.actor_id.strip():
        raise ValueError("actor_id is required")
    if not request.resource_ref.strip():
        raise ValueError("resource_ref is required")


def _normalize_rule(rule: PolicyRule | dict[str, Any]) -> PolicyRule:
    if isinstance(rule, PolicyRule):
        return rule
    return PolicyRule(
        rule_id=str(rule.get("rule_id") or rule.get("id") or ""),
        effect=_validate_effect(str(rule.get("effect") or "")),
        reason=str(rule.get("reason") or ""),
        match=dict(rule.get("match") or {}),
    )


def _rule_matches(rule: PolicyRule, request: PolicyDecisionRequest) -> bool:
    if not rule.rule_id.strip():
        raise ValueError("rule_id is required")
    if not rule.reason.strip():
        raise ValueError("rule reason is required")
    payload = request.as_dict()
    for key, expected in rule.match.items():
        if key.startswith("context."):
            actual = request.context.get(key.removeprefix("context."))
        else:
            actual = payload.get(key)
        if isinstance(expected, list):
            if actual not in expected:
                return False
        elif actual != expected:
            return False
    return True


def _validate_effect(effect: str) -> PolicyEffect:
    if effect not in VALID_EFFECTS:
        raise ValueError(f"invalid policy effect {effect!r}; expected one of {sorted(VALID_EFFECTS)}")
    return effect  # type: ignore[return-value]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate one local policy decision.")
    parser.add_argument("--request-json", required=True)
    parser.add_argument("--rules-json", default="[]")
    parser.add_argument("--default-effect", choices=sorted(VALID_EFFECTS), default="deny")
    parser.add_argument("--policy-ref")
    parser.add_argument("--log-path", type=Path)
    parser.add_argument("--resource", action="store_true", help="render resource envelope")
    args = parser.parse_args(argv)

    result = evaluate_policy(
        PolicyDecisionRequest(**json.loads(args.request_json)),
        rules=json.loads(args.rules_json),
        default_effect=args.default_effect,
        policy_ref=args.policy_ref,
        log_path=args.log_path,
    )
    payload = policy_decision_resource(result).as_dict() if args.resource else result.as_dict()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
