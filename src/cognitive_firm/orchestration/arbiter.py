from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _findings_by_id(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    findings = report.get("findings") or []
    result: dict[str, dict[str, Any]] = {}
    for finding in findings:
        finding_id = finding.get("id")
        if finding_id:
            result[finding_id] = finding
    return result


def merge_critic_reports(task_id: str, reports: dict[str, dict[str, Any]]) -> dict[str, Any]:
    indexed = {critic: _findings_by_id(report) for critic, report in reports.items()}
    all_ids = sorted({finding_id for per_critic in indexed.values() for finding_id in per_critic})

    agreements: list[dict[str, Any]] = []
    disagreements: list[dict[str, Any]] = []
    unilateral: list[dict[str, Any]] = []
    action_items: list[str] = []
    do_not_change: list[str] = []
    requires_human_review = False

    for report in reports.values():
        for item in report.get("do_not_change") or []:
            if item not in do_not_change:
                do_not_change.append(item)

    for finding_id in all_ids:
        entries = {
            critic: findings[finding_id]
            for critic, findings in indexed.items()
            if finding_id in findings
        }
        if len(entries) == 1:
            critic, finding = next(iter(entries.items()))
            unilateral.append({"critic": critic, "finding": finding})
            if finding.get("severity") in {"high", "critical"}:
                requires_human_review = True
            continue

        critics = sorted(entries)
        first = entries[critics[0]]
        same_fix = all(
            entries[c].get("proposed_fix", "").strip() == first.get("proposed_fix", "").strip()
            for c in critics[1:]
        )
        same_claim = all(
            entries[c].get("claim", "").strip() == first.get("claim", "").strip()
            for c in critics[1:]
        )
        if same_fix and same_claim:
            agreements.append(
                {
                    "id": finding_id,
                    "claim": first.get("claim"),
                    "proposed_fix": first.get("proposed_fix"),
                    "critics": critics,
                    "severity": first.get("severity"),
                }
            )
            if first.get("proposed_fix"):
                action_items.append(first["proposed_fix"])
        else:
            disagreements.append(
                {
                    "id": finding_id,
                    "entries": entries,
                }
            )
            requires_human_review = True

    for report in reports.values():
        next_action = report.get("next_action")
        if next_action and next_action not in action_items:
            action_items.append(next_action)
        if report.get("requires_human_review") is True:
            requires_human_review = True

    decision = "blocked" if disagreements else "actionable"
    if not agreements and unilateral:
        decision = "needs_review"
        requires_human_review = True

    return {
        "task_id": task_id,
        "decision": decision,
        "requires_human_review": requires_human_review,
        "agreements": agreements,
        "disagreements": disagreements,
        "unilateral_findings": unilateral,
        "do_not_change": do_not_change,
        "action_items": action_items,
    }


def render_markdown(bundle: dict[str, Any], merged: dict[str, Any], critic_names: list[str]) -> str:
    lines = [
        f"# Debate Report: {bundle['task_id']}",
        "",
        f"- Project: `{bundle['project']}`",
        f"- Run: `{bundle.get('run_id') or 'none'}`",
        f"- Stage: `{bundle.get('stage') or 'unknown'}`",
        f"- Critics: {', '.join(critic_names)}",
        f"- Decision: `{merged['decision']}`",
        f"- Requires human review: `{merged['requires_human_review']}`",
        "",
        "## Summary",
        bundle["summary"],
        "",
    ]
    if merged["agreements"]:
        lines.extend(["## Agreements", ""])
        for item in merged["agreements"]:
            lines.append(f"- `{item['id']}`: {item['claim']}")
            if item.get("proposed_fix"):
                lines.append(f"  Fix: {item['proposed_fix']}")
    if merged["disagreements"]:
        lines.extend(["", "## Disagreements", ""])
        for item in merged["disagreements"]:
            lines.append(f"- `{item['id']}`")
            for critic, finding in item["entries"].items():
                lines.append(f"  - {critic}: {finding.get('claim')} | fix: {finding.get('proposed_fix')}")
    if merged["unilateral_findings"]:
        lines.extend(["", "## Unilateral Findings", ""])
        for item in merged["unilateral_findings"]:
            finding = item["finding"]
            lines.append(f"- {item['critic']}: `{finding.get('id')}` -> {finding.get('claim')}")
    if merged["do_not_change"]:
        lines.extend(["", "## Do Not Change", ""])
        for item in merged["do_not_change"]:
            lines.append(f"- {item}")
    if merged["action_items"]:
        lines.extend(["", "## Action Items", ""])
        for item in merged["action_items"]:
            lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)

