#!/usr/bin/env python3
"""No-cost demo for Strategy -> Execution -> Verification phase records."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from cognitive_firm.orchestration.phase_execution import (  # noqa: E402
    phase_execution_plan_resource,
    record_phase_directive,
    record_verification_feedback,
    start_phase_execution_plan,
)
from cognitive_firm.orchestration.resource_envelope import validate_resource  # noqa: E402


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="cf-phase-execution-") as raw:
        log = Path(raw) / "phase_execution.jsonl"
        plan = start_phase_execution_plan(
            objective="repair a handoff protocol using bounded verifier feedback",
            owner_role="role.org_evolver",
            total_budget_units=8,
            max_attempts=3,
            run_id="run_phase_demo",
            work_id="work_phase_demo",
            log_path=log,
        )
        plan = record_phase_directive(
            plan_id=plan.plan_id,
            phase="strategy",
            issued_by="role.org_evolver",
            directive="Identify which handoff evidence rule failed and define acceptance criteria.",
            evidence_refs=["multi_agent_attribution:fatp_demo"],
            budget_units=2,
            log_path=log,
        )
        plan = record_phase_directive(
            plan_id=plan.plan_id,
            phase="execution",
            issued_by="role.executor",
            directive="Draft the handoff evidence rule with source refs and rollback path.",
            output_refs=["artifact://handoff-evidence-rule-draft-v1"],
            budget_units=3,
            log_path=log,
        )
        plan = record_verification_feedback(
            plan_id=plan.plan_id,
            verifier_role="role.evaluator",
            verdict="failed",
            rationale="Draft did not specify how missing source refs block downstream evaluation.",
            evidence_refs=["artifact://handoff-evidence-rule-review-v1"],
            budget_decay=0.5,
            log_path=log,
        )
        plan = record_phase_directive(
            plan_id=plan.plan_id,
            phase="execution",
            issued_by="role.executor",
            directive="Revise the rule so missing source refs force abstention or escalation.",
            output_refs=["artifact://handoff-evidence-rule-draft-v2"],
            budget_units=plan.remaining_budget_units,
            log_path=log,
        )
        plan = record_verification_feedback(
            plan_id=plan.plan_id,
            verifier_role="role.evaluator",
            verdict="passed",
            rationale="Revision includes failure behavior, evidence refs, and rollback path.",
            evidence_refs=["artifact://handoff-evidence-rule-review-v2"],
            log_path=log,
        )
        resource_errors = validate_resource(phase_execution_plan_resource(plan).as_dict())

    payload = {
        "demo": "phase_execution",
        "no_external_calls": True,
        "summary": {
            "plan_status": plan.status,
            "attempts": plan.attempts,
            "directives": len(plan.directives),
            "feedback": len(plan.feedback),
            "remaining_budget_units": plan.remaining_budget_units,
            "budget_after_failed_verification": plan.feedback[0]["retry_budget_after"],
            "resource_schema_ok": not resource_errors,
            "verdict": "passed" if plan.status == "passed" and not resource_errors else "failed",
        },
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["summary"]["verdict"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
