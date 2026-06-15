"""Execution-route classifier for governed role-office work.

The daemon should not rely on a spawned agent to intuit whether a work item is
ordinary role work, expert review, artifact construction, or a repeatable
experiment loop. This module is deliberately small: it turns task frontmatter
and body text into a typed routing contract the runtime must obey or explicitly
override.

The route is not authority. Mandates, leases, policy decisions, and resource
budgets still determine whether execution is allowed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


ROUTES = {
    "route_only",
    "direct_work",
    "expert_review",
    "synthesis_review",
    "scripted_run",
    "artifact_build",
    "joint_work",
    "experiment_loop",
    "docs_records",
}
ROUTE_ALIASES = {
    # Compatibility aliases. New tenant-specific names belong in overlays or
    # work-item frontmatter, not as public kernel routes.
    "manual_agent": "direct_work",
    "cold_shot": "expert_review",
    "external_review": "expert_review",
    "second_opinion": "expert_review",
    "big_picture": "synthesis_review",
    "deanchored_synthesis": "synthesis_review",
    "script_or_gpu": "scripted_run",
    "substrate_build": "artifact_build",
    "tenant_loop": "experiment_loop",
    "paper_or_docs": "docs_records",
    "human_work": "joint_work",
    "human_agent": "joint_work",
    "co_work": "joint_work",
    "live_co_drive": "joint_work",
    "live_codrive": "joint_work",
    "rd_live": "joint_work",
}


@dataclass(frozen=True)
class ExecutionRoute:
    route: str
    confidence: str
    rationale: str
    tenant_loop_allowed: bool
    experiment_loop_allowed: bool
    artifact_build_allowed: bool
    substrate_build_allowed: bool
    live_api_allowed: bool
    gpu_allowed: bool
    required_first_artifact: str
    escalation: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "tenant_loop_allowed": self.tenant_loop_allowed,
            "experiment_loop_allowed": self.experiment_loop_allowed,
            "artifact_build_allowed": self.artifact_build_allowed,
            "substrate_build_allowed": self.substrate_build_allowed,
            "live_api_allowed": self.live_api_allowed,
            "gpu_allowed": self.gpu_allowed,
            "required_first_artifact": self.required_first_artifact,
            "escalation": self.escalation,
        }


def _bool_frontmatter(fm: dict[str, Any], key: str, default: bool) -> bool:
    if key not in fm:
        return default
    value = fm.get(key)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _explicit_route(fm: dict[str, Any]) -> str | None:
    for key in ("execution_route", "route_hint", "recommended_route"):
        value = str(fm.get(key) or "").strip()
        if value:
            value = ROUTE_ALIASES.get(value, value)
            if value not in ROUTES:
                raise ValueError(
                    f"unknown execution route {value!r}; expected one of {sorted(ROUTES)}"
                )
            return value
    return None


def infer_execution_route(
    *,
    frontmatter: dict[str, Any] | None = None,
    body: str = "",
    role_id: str = "manager",
) -> ExecutionRoute:
    """Infer the cheapest safe execution route for a task.

    Explicit frontmatter wins. Heuristics are intentionally conservative:
    absent a stable contract, default to direct role-office work rather than
    launching a loop, paid API, or external compute.
    """
    fm = dict(frontmatter or {})
    text = f"{body}\n{fm}".lower()
    explicit = _explicit_route(fm)
    _ = role_id  # Kept for API compatibility; role authority is checked elsewhere.

    if explicit:
        route = explicit
        confidence = "frontmatter"
        rationale = f"task frontmatter selected {route}"
    elif any(
        k in text
        for k in (
            "architecture review",
            "compare approaches",
            "design review",
            "big picture",
            "10k view",
            "10000-foot",
            "10,000-foot",
            "literature review",
            "meta pattern",
            "root cause",
            "synthesis",
        )
    ):
        route = "synthesis_review"
        confidence = "medium"
        rationale = "task asks for synthesis or architectural review before execution"
    elif any(k in text for k in ("artifact", "schema", "template", "contract", "harness")) and any(
        k in text for k in ("build", "generate", "scaffold", "create", "author")
    ):
        route = "artifact_build"
        confidence = "medium"
        rationale = "task asks for a reusable artifact, schema, contract, or harness"
    elif any(
        k in text
        for k in (
            "experiment loop",
            "experiment-loop",
            "ab test",
            "a/b test",
            "many candidates",
            "candidate search",
            "mutator",
            "gate_harness",
            "bandit",
        )
    ):
        route = "experiment_loop"
        confidence = "medium"
        rationale = "task names a repeatable gated experiment or candidate-search loop"
    elif any(k in text for k in ("gpu", "jax", "nohup", "ssh", "solver", "simulation", "batch")):
        route = "scripted_run"
        confidence = "medium"
        rationale = "task requires one-off scripted or external-compute orchestration"
    elif any(
        k in text
        for k in (
            "expert review",
            "adversarial review",
            "second opinion",
            "external model",
            "external reviewer",
            "gemini",
            "gpt-5",
            "llm api",
        )
    ):
        route = "expert_review"
        confidence = "medium"
        rationale = "task calls for expert, adversarial, or external-model review"
    elif any(k in text for k in ("human work", "joint work", "needs human", "human must")):
        route = "joint_work"
        confidence = "medium"
        rationale = "task requires bounded human work alongside a role office"
    elif any(k in text for k in ("paper", "ssrn", "readme", "docs", "ledger", "manual")):
        route = "docs_records"
        confidence = "medium"
        rationale = "task is primarily prose, public/private sync, or recording"
    else:
        route = "direct_work"
        confidence = "low"
        rationale = "no stable execution contract detected; use operator-agent/manual exploration first"

    # Frontmatter can narrow permissions. Defaults are route-derived and remain
    # intentionally conservative for paid, mutating, or contaminating work.
    experiment_loop_allowed = route == "experiment_loop"
    tenant_loop_allowed = experiment_loop_allowed
    artifact_build_allowed = route == "artifact_build"
    substrate_allowed = artifact_build_allowed
    live_api_allowed = route == "expert_review"
    gpu_allowed = route == "scripted_run"

    experiment_loop_allowed = _bool_frontmatter(fm, "experiment_loop_allowed", experiment_loop_allowed)
    tenant_loop_allowed = _bool_frontmatter(fm, "tenant_loop_allowed", tenant_loop_allowed)
    artifact_build_allowed = _bool_frontmatter(fm, "artifact_build_allowed", artifact_build_allowed)
    substrate_allowed = _bool_frontmatter(fm, "substrate_build_allowed", substrate_allowed)
    live_api_allowed = _bool_frontmatter(fm, "live_api_allowed", live_api_allowed)
    gpu_allowed = _bool_frontmatter(fm, "gpu_allowed", gpu_allowed)

    first_artifact = str(fm.get("required_first_artifact") or "").strip()
    if not first_artifact:
        first_artifact = {
            "route_only": "workspace/execution_route_decision.md",
            "direct_work": "workspace/execution_route_decision.md",
            "expert_review": "workspace/expert_review_packet.md",
            "synthesis_review": "workspace/deanchored_synthesis_checkpoint.md",
            "scripted_run": "workspace/run_packet.md",
            "artifact_build": "workspace/artifact_build_spec.md",
            "joint_work": "workspace/human_work_session.md",
            "experiment_loop": "workspace/preflight_substrate_audit.md",
            "docs_records": "workspace/doc_edit_plan.md",
        }[route]

    escalation = str(fm.get("route_escalation") or "").strip()
    if not escalation:
        if route == "experiment_loop":
            escalation = "If preflight fails or no sealed gates exist, do not launch; write an artifact_build task."
        elif route == "artifact_build":
            escalation = "Implementation must be assigned to an actor with mandate, lease, and policy authority for the artifact."
        elif route == "synthesis_review":
            escalation = "Write the synthesis checkpoint before recommending paid API/GPU or another experiment-loop iteration."
        elif route in {"expert_review", "scripted_run"}:
            escalation = "Escalate before live spend above the task budget cap or if static replay can answer the question."
        else:
            escalation = "Escalate if the task requires paid API/GPU, substrate mutation, or tenant-loop launch not explicitly allowed."

    return ExecutionRoute(
        route=route,
        confidence=confidence,
        rationale=rationale,
        tenant_loop_allowed=tenant_loop_allowed,
        experiment_loop_allowed=experiment_loop_allowed,
        artifact_build_allowed=artifact_build_allowed,
        substrate_build_allowed=substrate_allowed,
        live_api_allowed=live_api_allowed,
        gpu_allowed=gpu_allowed,
        required_first_artifact=first_artifact,
        escalation=escalation,
    )


def render_route_contract(route: ExecutionRoute) -> str:
    """Render a compact prompt block for spawned role agents."""
    return (
        "EXECUTION ROUTE CONTRACT\n"
        f"- route: {route.route}\n"
        f"- confidence: {route.confidence}\n"
        f"- rationale: {route.rationale}\n"
        f"- experiment_loop_allowed: {str(route.experiment_loop_allowed).lower()}\n"
        f"- tenant_loop_allowed: {str(route.tenant_loop_allowed).lower()}\n"
        f"- artifact_build_allowed: {str(route.artifact_build_allowed).lower()}\n"
        f"- substrate_build_allowed: {str(route.substrate_build_allowed).lower()}\n"
        f"- live_api_allowed: {str(route.live_api_allowed).lower()}\n"
        f"- gpu_allowed: {str(route.gpu_allowed).lower()}\n"
        f"- required_first_artifact: {route.required_first_artifact}\n"
        f"- escalation: {route.escalation}\n"
        "- rule: prefer an existing repo command or Python entrypoint before authoring a new one.\n"
        "- rule: write or update the required_first_artifact before executing the route.\n"
        "- rule: if you disagree with the inferred route, write the override rationale first; do not silently switch modes.\n"
    )
