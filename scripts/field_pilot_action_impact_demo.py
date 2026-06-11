#!/usr/bin/env python3
"""Field-pilot action-impact demo.

This fixture connects the field-pilot pack to the learned-policy path. It
creates a small pilot folder, writes an action-impact summary in the pilot
folder, validates the pilot with that machine-readable evidence, then produces
a candidate route, offline evaluation, and governance review packet.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from cognitive_firm.orchestration.action_impact import (
    append_policy_evaluation,
    append_policy_promotion_packet,
    build_policy_promotion_packet,
    evaluate_offline_policy_candidate,
    load_summary_from_json,
)
from cognitive_firm.orchestration.business_function_bandit import propose_business_function_policy

from field_pilot_validate import validate_pilot


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT / "docs" / "templates" / "field-pilot"


def _pilot_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx in range(24):
        specialist = idx % 2 == 0
        rows.append(
            {
                "action_id": f"approval-{idx}",
                "action_ref": f"field-pilot://product-requirement-approval/{idx}",
                "actor": "role.requirements_router",
                "objective_metric": "approval_quality",
                "status": "measured",
                "context_features": {"decision_class": "customer_facing_requirement"},
                "action_arm": "specialist_review" if specialist else "general_review",
                "logging_policy_probability": 0.5,
                "counterfactual_action": "general_review" if specialist else "specialist_review",
                "reward": 0.86 if specialist else 0.62,
                "guardrail_metrics": {"review_hours": 3.0 if specialist else 1.5},
                "externalities": {"team_burden": 0.0},
                "requires_human_review": False,
                "measurement_ref": f"metrics-table.md#approval-{idx}",
            }
        )
    for idx in range(10):
        auto = idx % 2 == 0
        rows.append(
            {
                "action_id": f"low-risk-{idx}",
                "action_ref": f"field-pilot://low-risk-copy/{idx}",
                "actor": "role.requirements_router",
                "objective_metric": "throughput",
                "status": "measured",
                "context_features": {"decision_class": "low_risk_copy_change"},
                "action_arm": "auto_approve" if auto else "light_review",
                "logging_policy_probability": 0.5,
                "counterfactual_action": "light_review" if auto else "auto_approve",
                "reward": 0.95 if auto else 0.55,
                "negative_externality_tags": ["customer_confusion"] if auto else [],
                "requires_human_review": auto,
                "guardrail_metrics": {"complaint_rate": 0.06 if auto else 0.01},
                "measurement_ref": f"metrics-table.md#low-risk-{idx}",
            }
        )
    return rows


def _scaffold_completed_pilot(root: Path) -> dict[str, Path]:
    root.mkdir(parents=True, exist_ok=True)
    for source in TEMPLATE_DIR.glob("*.md"):
        shutil.copyfile(source, root / source.name)
    _complete_scope(root / "pilot-scope.md")
    _fill_blank_table_cells(root)
    action_impact = root / "action-impact-summary.json"
    action_impact.write_text(
        json.dumps({"records": _pilot_rows()}, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    authority_diff = root / "authority-diff-specialist-review.json"
    authority_diff.write_text(
        json.dumps(
            {
                "change": "route customer-facing requirements to specialist review",
                "authority_change": "none",
                "review_surface": "role.product_governance",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return {
        "pilot": root,
        "action_impact": action_impact,
        "authority_diff": authority_diff,
        "evaluations": root / "policy-evaluations.jsonl",
        "packets": root / "policy-promotion-packets.jsonl",
    }


def _complete_scope(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = text.replace("Workflow name:", "Workflow name: Product requirement approval")
    text = text.replace("Baseline window:", "Baseline window: prior 30 days")
    text = text.replace("Pilot window:", "Pilot window: next 60 days")
    text = text.replace(
        "The pilot passes if:\n\n- ",
        "The pilot passes if:\n\n- approval error rate falls without increased human coordination burden\n",
    )
    path.write_text(text, encoding="utf-8")


def _fill_blank_table_cells(root: Path) -> None:
    for path in root.glob("*.md"):
        lines = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if _has_blank_table_cells(line):
                cells = [cell.strip() for cell in line.strip("|").split("|")]
                line = "|" + "|".join([f" {cell or 'example'} " for cell in cells]) + "|"
            lines.append(line)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _has_blank_table_cells(line: str) -> bool:
    if not line.startswith("|"):
        return False
    cells = [cell.strip() for cell in line.strip("|").split("|")]
    if len(cells) < 3:
        return False
    if set(cells[1]) <= {"-"}:
        return False
    return any(cell == "" for cell in cells[1:])


def run_demo(root: Path) -> dict[str, Any]:
    logs = _scaffold_completed_pilot(root)
    validation = validate_pilot(
        logs["pilot"],
        require_action_impact=True,
        min_action_impact_records=30,
    )
    summary = load_summary_from_json(logs["action_impact"])
    proposal = propose_business_function_policy(
        summary.records,
        candidate_policy_id="policy.field_pilot.specialist_requirement_review",
        objective_metric="approval_quality",
        context_keys=["decision_class"],
        min_context_rows=20,
        min_arm_rows=10,
        evidence_refs=[str(logs["action_impact"])],
        metadata={"demo": "field_pilot_action_impact"},
    )
    safe_report = evaluate_offline_policy_candidate(
        summary.records,
        candidate_policy_id=proposal.candidate_policy_id,
        candidate_policy_ref="policy://field-pilot/specialist-requirement-review",
        candidate_action_by_context=proposal.candidate_action_by_context,
        context_keys=proposal.context_keys,
        objective_metric=proposal.objective_metric,
        min_matched=10,
        min_support_coverage=0.4,
        evidence_refs=[str(logs["action_impact"])],
        metadata={"demo": "field_pilot_action_impact"},
    )
    append_policy_evaluation(safe_report, log_path=logs["evaluations"])
    packet = build_policy_promotion_packet(
        safe_report,
        proposed_by="role.product_governance",
        authority_diff_ref=str(logs["authority_diff"]),
        title="Review field-pilot specialist-review routing policy",
        evidence_refs=[str(logs["pilot"] / "metrics-table.md")],
    )
    append_policy_promotion_packet(packet, log_path=logs["packets"])
    return {
        "demo": "field_pilot_action_impact",
        "fictional_firm": "Kettle & Compass Field Kits",
        "no_external_calls": True,
        "pilot_validation": validation,
        "candidate_proposal": {
            "status": proposal.status,
            "contexts": len(proposal.candidate_action_by_context),
            "selected_arms": [arm.as_dict() for arm in proposal.selected_arms],
            "rejected_contexts": len(proposal.rejected_contexts),
        },
        "policy_evaluation": {
            "status": safe_report.status,
            "delta_mean_reward": safe_report.delta_mean_reward,
            "support_coverage": safe_report.support_coverage,
            "promotion_allowed": safe_report.promotion_allowed,
        },
        "promotion_packet": {
            "status": packet.status,
            "review_blockers": packet.review_blockers,
            "candidate_policy_id": packet.candidate_policy_id,
        },
        "summary": {
            "action_impact_records": len(summary.records),
            "validation_ok": bool(validation["ok"]),
            "packet_status": packet.status,
            "verdict": "passed"
            if validation["ok"]
            and proposal.status == "candidate"
            and safe_report.status == "promotable"
            and packet.status == "review_ready"
            else "failed",
        },
        "log_paths": {name: str(path) for name, path in logs.items()},
    }


def _compact(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "demo": payload["demo"],
        "fictional_firm": payload["fictional_firm"],
        "no_external_calls": payload["no_external_calls"],
        "candidate_proposal": payload["candidate_proposal"],
        "policy_evaluation": payload["policy_evaluation"],
        "promotion_packet": payload["promotion_packet"],
        "summary": payload["summary"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a field-pilot action-impact replay demo.",
    )
    parser.add_argument("--workdir", type=Path)
    parser.add_argument("--full-json", action="store_true")
    args = parser.parse_args(argv)

    if args.workdir:
        payload = run_demo(args.workdir)
    else:
        with tempfile.TemporaryDirectory(prefix="cf-field-pilot-action-impact-") as raw:
            payload = run_demo(Path(raw))
    output = payload if args.full_json else _compact(payload)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0 if payload["summary"]["verdict"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
