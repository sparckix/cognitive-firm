"""``cognitive-firm-userland`` — the terminal carrier of the userland.

A parallel lane to the graphical surfaces: the same L1/L2/L4 userland models,
served to a participant through a console. Every verb is a thin projection —
it calls a kernel route or a userland read model, then prints the governance
interpretation. It holds no state and reaches into no kernel internals.

Verbs:

- ``needs-me <actor_id>``  — the operator's escalation queue (L1 + L2).
- ``inbox <actor_id>``     — a member-human's bounded work queue (L2).
- ``vocabulary``           — the shared L4 glossary every surface speaks.
- ``commands <query>``     — discover canonical repo commands for a task.
- ``status``               — a plain-language read of overall org health.
- ``resolve <gate_id>``    — act on a pending gate the operator saw in ``needs-me``.
- ``proposals``            — governance changes awaiting an accountable actor decision.
- ``proposal <id>``        — inspect one governance proposal's evidence.
- ``proposal-packet <id>`` — export a proposal review handoff packet.
- ``proposal-template``    — print an evidence-complete proposal skeleton.
- ``proposal-from-candidate`` — promote a learning candidate into a proposal.
- ``learning-candidates``  — inspect observer-only learning-transition candidates.
- ``lease-acquire``       — acquire a mutation lease for a guarded write.
- ``leases``              — list mutation leases visible to the service.
- ``lease-release``       — release a mutation lease held by the actor.
- ``decision-profiles``    — list reusable evidence-only decision procedures.
- ``decision-cases``       — inspect decision aggregation evidence cases.
- ``decision-open``        — open a decision aggregation evidence case.
- ``decision-position``    — record one eligible position on a decision case.
- ``decision-compute``     — compute a decision aggregation recommendation.
- ``decision-route-escalation`` — route an escalated decision case into learning review.
- ``work-context``         — read learning context before a role starts work.
- ``context-packet-verify`` — verify a captured work-context packet digest.
- ``composition-packet``   — check a governed action proof-chain matrix.
- ``human-pressure``       — inspect repeated A2H human-work pressure.
- ``speed-envelope``       — classify accountable human/agent work speed.
- ``receipt``              — record a structured human-work receipt.
- ``learning-use``         — record an auditable learning-use receipt.
- ``learning-loop``        — inspect one learning event's compounding loop.
- ``approve <id>``         — approve a governance change (an attested event).
- ``decline <id>``         — decline a governance change (an attested event).
- ``timeline``             — read the provenance timeline for a run/ref/scope.
- ``graph``                — read the projection-only provenance graph.
- ``provenance-report``    — export a portable provenance handoff report.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from cognitive_firm.kernel_service import dispatch_kernel_request
from cognitive_firm.userland import work_inbox
from cognitive_firm.userland.attention_router import RoutedSignal
from cognitive_firm.userland.needs_me import build_needs_me


_PROVENANCE_SELECTOR_HELP = (
    "--run-id, --ref, --tenant-id, or --tenant-id with --project-id"
)


def _validate_provenance_scope_args(
    args: argparse.Namespace,
    command_name: str,
) -> bool:
    """Return whether a provenance projection has a tenant-safe selector."""
    if not any([args.run_id, args.ref, args.tenant_id, args.project_id]):
        print(
            f"ERROR: {command_name} requires {_PROVENANCE_SELECTOR_HELP}",
            file=sys.stderr,
        )
        return False
    if args.project_id and not args.tenant_id and not args.run_id:
        print(
            (
                f"ERROR: {command_name} --project-id requires --tenant-id "
                "unless --run-id anchors scope"
            ),
            file=sys.stderr,
        )
        return False
    return True


def _add_lease_args(parser: argparse.ArgumentParser) -> None:
    """Add optional mutation-lease evidence to a write command."""
    parser.add_argument(
        "--lease-id",
        default=None,
        help="Optional active mutation lease id for leased kernel deployments.",
    )
    parser.add_argument(
        "--fencing-token",
        type=int,
        default=None,
        help="Fencing token paired with --lease-id.",
    )


def _attach_lease_args(body: dict[str, Any], args: argparse.Namespace) -> None:
    lease_id = getattr(args, "lease_id", None)
    fencing_token = getattr(args, "fencing_token", None)
    if lease_id:
        body["lease_id"] = lease_id
    if fencing_token is not None:
        body["fencing_token"] = fencing_token


def _cmd_needs_me(args: argparse.Namespace) -> int:
    """Print the operator's ``needs-me`` queue for one participant."""
    response = dispatch_kernel_request(
        "GET", f"/kernel/attention/{args.actor_id}"
    )
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    signals = [
        RoutedSignal(**entry)
        for entry in response.payload.get("signals", [])
    ]
    view = build_needs_me(actor_id=args.actor_id, signals=signals)
    print(view.waiting_line)
    for group in view.groups:
        print()
        print(f"[{group.label}] ({len(group.items)})")
        for item in group.items:
            print(f"  - {item.headline}")
            print(f"    action: {item.primary_action}")
    return 0


def _cmd_inbox(args: argparse.Namespace) -> int:
    """Print a member-human's bounded work inbox."""
    items = work_inbox.list_inbox(
        actor_id=args.actor_id, log_path=args.human_work_log
    )
    if not items:
        print(f"{args.actor_id} has no open work.")
        return 0
    print(f"{args.actor_id} — {len(items)} open task(s):")
    for item in items:
        print()
        print(f"  [{item.state}] {item.objective}")
        print(f"    deliverable: {item.human_deliverable or '(none specified)'}")
        print(f"    deadline:    {item.deadline_utc or '(none)'}")
    return 0


def _cmd_vocabulary(_args: argparse.Namespace) -> int:
    """Print the shared L4 userland glossary."""
    response = dispatch_kernel_request("GET", "/kernel/vocabulary")
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    terms = response.payload.get("terms", [])
    print(f"userland vocabulary — {len(terms)} term(s):")
    for term in terms:
        print()
        print(f"  {term['label']}")
        print(f"    {term['definition']}")
    return 0


def _cmd_commands(args: argparse.Namespace) -> int:
    """Print read-only command-surface matches for a task description."""
    params = {"query": args.query}
    if args.role_id:
        params["role_id"] = args.role_id
    query = urlencode(params)
    response = dispatch_kernel_request("GET", f"/kernel/command-surface?{query}")
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    matches = response.payload.get("matches", [])
    print(f"command surface - {len(matches)} match(es)")
    print(f"query: {response.payload.get('query')}")
    print("read-only: true")
    if not matches:
        print(response.payload.get("hint", "No exact repo command matched."))
        return 0
    for match in matches:
        print()
        print(f"  {match.get('command')}")
        print(f"    kind: {match.get('command_kind')}")
        print("    executes: false")
        guidance = match.get("operator_guidance") or {}
        if guidance:
            optional = "optional" if guidance.get("optional") else "required"
            print(
                "    operator path: "
                f"{guidance.get('path_id')} "
                f"step {guidance.get('step')}/{guidance.get('total_steps')} "
                f"({optional})"
            )
            print(f"      {guidance.get('description')}")
        effects = match.get("authority_effects") or []
        if effects:
            print("    authority effects:")
            for effect in effects:
                resolution = effect.get("authority_resolution") or {}
                scope = _format_command_effect_scope(effect)
                print(
                    f"      - {effect.get('effect_id')}: {scope}; "
                    f"resolution={resolution.get('status', 'unknown')}"
                )
                source_escalation = effect.get("source_role_escalation")
                if source_escalation:
                    path = source_escalation.get("escalation_path") or []
                    path_text = (
                        " -> ".join(f"role.{role_id}" for role_id in path)
                        if path
                        else "unresolved"
                    )
                    print(
                        "        source role escalation: "
                        f"{source_escalation.get('status')}; {path_text}"
                    )
            issues = (match.get("authority_effect_validation") or {}).get(
                "issues"
            ) or []
            for issue in issues:
                print(f"        issue: {issue}")
    return 0


def _cmd_operator_path(args: argparse.Namespace) -> int:
    """Print a named operator path as read-only command guidance."""
    query = urlencode({"path_id": args.path_id})
    response = dispatch_kernel_request("GET", f"/kernel/operator-path?{query}")
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    path = response.payload.get("operator_path") or {}
    steps = path.get("steps") or []
    print(
        "operator path - "
        f"{path.get('path_id')} ({len(steps)} step(s)), read-only"
    )
    print(f"label: {path.get('path_label')}")
    if path.get("purpose"):
        print(f"purpose: {path.get('purpose')}")
    if path.get("use_when"):
        print(f"use when: {path.get('use_when')}")
    print("projection-only: true")
    print("executes: false")
    boundary = path.get("boundary") or {}
    if boundary:
        parts = []
        if boundary.get("does_not_execute_commands"):
            parts.append("no command execution")
        if boundary.get("does_not_schedule_work"):
            parts.append("no scheduling")
        if boundary.get("does_not_mutate_kernel_state"):
            parts.append("no state mutation")
        if boundary.get("does_not_approve_adoption"):
            parts.append("no adoption approval")
        if parts:
            print("boundary: " + "; ".join(parts))
    if path.get("not_a"):
        print("not a: " + ", ".join(str(item) for item in path["not_a"]))
    for step in steps:
        optional = "optional" if step.get("optional") else "required"
        print()
        print(
            f"  {step.get('step')}/{step.get('total_steps')} "
            f"{step.get('command')} ({optional})"
        )
        print(f"    {step.get('description')}")
    return 0


def _format_command_effect_scope(effect: dict) -> str:
    parts = []
    if effect.get("decision_class"):
        parts.append(f"decision_class={effect['decision_class']}")
    if effect.get("resource_class"):
        parts.append(f"resource_class={effect['resource_class']}")
    return ", ".join(parts) if parts else "unscoped"


def _cmd_status(_args: argparse.Namespace) -> int:
    """Print a plain-language read of overall org health."""
    response = dispatch_kernel_request("GET", "/kernel/org-surface")
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    surface = response.payload.get("surface", {})
    counts = surface.get("counts", {})

    active_runs = counts.get("active_runs", 0)
    failed_runs = counts.get("failed_runs", 0)
    active_work = counts.get("active_human_work_sessions", 0)
    waiting_work = counts.get("waiting_human_work_sessions", 0)
    a2h_waiting = counts.get("a2h_waiting_on_human_sessions", 0)
    blocked_obligations = counts.get("blocked_obligations", 0)
    blocking_gaps = counts.get("blocking_evidence_gaps", 0)
    pending_gov = counts.get("pending_governance_changes", 0)
    open_cases = counts.get("open_accountability_cases", 0)
    damage = counts.get("recent_damage_signals", 0)

    blocked_total = (
        blocked_obligations + blocking_gaps + a2h_waiting + waiting_work
    )

    print("org status")
    print()
    if active_runs or active_work:
        print(
            f"  running: {active_runs} active run(s), "
            f"{active_work} open human-work session(s)."
        )
    else:
        print("  running: nothing is currently in flight.")

    if blocked_total:
        print(
            f"  blocked: {blocked_total} thing(s) waiting on someone — "
            f"{waiting_work} human-work session(s), "
            f"{a2h_waiting} agent request(s) waiting on a human, "
            f"{blocked_obligations} blocked obligation(s), "
            f"{blocking_gaps} blocking evidence gap(s)."
        )
    else:
        print("  blocked: nothing is blocked.")

    if failed_runs:
        print(f"  attention: {failed_runs} run(s) have failed.")
    if damage:
        print(f"  attention: {damage} recent damage signal(s).")

    print(
        f"  governance: {pending_gov} pending change(s), "
        f"{open_cases} open accountability case(s)."
    )
    return 0


def _cmd_resolve(args: argparse.Namespace) -> int:
    """Resolve one pending gate with the operator's option and reason."""
    body: dict[str, str] = {"chosen_option": args.option}
    if args.reason:
        body["reason"] = args.reason
    try:
        response = dispatch_kernel_request(
            "POST", f"/kernel/gates/{args.gate_id}/resolve", body
        )
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    result = response.payload.get("result", {})
    if result.get("already_resolved"):
        print(f"gate {args.gate_id} was already resolved.")
    else:
        print(f"gate {args.gate_id} resolved with option '{args.option}'.")
        event_id = result.get("transition_event_id")
        if event_id:
            print(f"  transition: {event_id}")
    path = result.get("path")
    if path:
        print(f"  record: {path}")
    return 0


def _cmd_proposals(_args: argparse.Namespace) -> int:
    """List governance changes awaiting an accountable actor decision."""
    response = dispatch_kernel_request(
        "GET", "/kernel/governance-changes?status=review_ready&view=review"
    )
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    proposals = [
        p for p in response.payload.get("proposals", [])
        if not p.get("decided")
    ]
    if not proposals:
        print("No governance changes are awaiting review.")
        return 0
    print(f"{len(proposals)} governance change(s) awaiting review:")
    for proposal in proposals:
        print()
        print(f"  [{proposal['change_kind']}] {proposal['title']}")
        print(f"    id:       {proposal['proposal_id']}")
        print(f"    proposed: {proposal['proposed_by']}")
        print(f"    review:   {proposal.get('review_state', proposal.get('status'))}")
        if proposal.get("expected_behavior_change"):
            print(f"    effect:   {proposal['expected_behavior_change']}")
        if proposal.get("risk_summary"):
            print(f"    risk:     {proposal['risk_summary']}")
        if proposal.get("rollback_plan"):
            print(f"    rollback: {proposal['rollback_plan']}")
        evidence_status = proposal.get("evidence_status")
        evidence_ref_count = proposal.get("evidence_ref_count")
        if evidence_status:
            print(
                f"    evidence: {evidence_status}"
                + (
                    f" ({evidence_ref_count} refs)"
                    if evidence_ref_count is not None
                    else ""
                )
            )
        failed = proposal.get("failed_invariants") or []
        missing = proposal.get("missing_evidence") or []
        if failed:
            print(f"    failed invariants: {', '.join(str(item) for item in failed)}")
        if missing:
            print(f"    missing evidence:  {', '.join(str(item) for item in missing)}")
        print(f"    decide:   cognitive-firm-userland approve {proposal['proposal_id']}")
    return 0


def _cmd_proposal(args: argparse.Namespace) -> int:
    """Print one governance proposal's evidence and invariant status."""
    response = dispatch_kernel_request(
        "GET", f"/kernel/governance-changes/{args.proposal_id}"
    )
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    proposal = response.payload.get("proposal", {})
    print(f"governance proposal {proposal.get('proposal_id')}")
    print(f"  status:   {proposal.get('status')}")
    print(f"  kind:     {proposal.get('change_kind')}")
    print(f"  title:    {proposal.get('title')}")
    print(f"  target:   {proposal.get('target_ref')}")
    print(f"  proposed: {proposal.get('proposed_by')}")
    if proposal.get("owner_role"):
        print(f"  owner:    {proposal.get('owner_role')}")
    if proposal.get("decided"):
        print("  decision: already decided")

    print()
    print("  evidence")
    for ref in proposal.get("source_refs") or []:
        print(f"    source:   {ref}")
    if proposal.get("expected_behavior_change"):
        print(f"    effect:   {proposal.get('expected_behavior_change')}")
    if proposal.get("risk_summary"):
        print(f"    risk:     {proposal.get('risk_summary')}")
    if proposal.get("rollback_plan"):
        print(f"    rollback: {proposal.get('rollback_plan')}")
    predicted = proposal.get("predicted_effect") or {}
    if predicted:
        metric = predicted.get("metric_name") or predicted.get("metric")
        direction = predicted.get("expected_direction") or predicted.get("direction")
        window = predicted.get("expected_window") or predicted.get("window")
        prediction_bits = [
            str(item) for item in (metric, direction, window) if item
        ]
        if prediction_bits:
            print(f"    prediction: {', '.join(prediction_bits)}")

    sufficiency = proposal.get("evidence_sufficiency") or {}
    if sufficiency:
        print()
        print(
            f"  evidence sufficiency: {sufficiency.get('status')} - "
            f"{sufficiency.get('rationale')}"
        )
        missing = sufficiency.get("missing") or []
        if missing:
            print(f"    missing: {', '.join(str(item) for item in missing)}")

    checks = proposal.get("invariant_checks") or []
    if checks:
        print()
        print("  invariants")
        for check in checks:
            print(
                f"    [{check.get('status')}] {check.get('invariant')}: "
                f"{check.get('rationale')}"
            )
            refs = check.get("evidence_refs") or []
            if refs:
                print(f"      refs: {', '.join(str(ref) for ref in refs)}")
    return 0


def _cmd_proposal_packet(args: argparse.Namespace) -> int:
    """Print a portable proposal-review handoff packet."""
    params = {"event_limit": args.event_limit}
    query = urlencode({key: value for key, value in params.items() if value is not None})
    path = f"/kernel/governance-changes/{args.proposal_id}/review-packet"
    if query:
        path = f"{path}?{query}"
    response = dispatch_kernel_request("GET", path)
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    packet = response.payload.get("packet", {})
    if args.markdown:
        markdown = str(packet.get("markdown") or "").rstrip()
        if markdown:
            print(markdown)
        return 0

    review = packet.get("review") or {}
    print(f"proposal review packet {packet.get('proposal_id')}")
    print("  read-only projection")
    print(f"  state:    {review.get('review_state')} ({review.get('status')})")
    print(f"  kind:     {review.get('change_kind')}")
    print(f"  target:   {review.get('target_ref')}")
    print(f"  title:    {review.get('title')}")
    if review.get("expected_behavior_change"):
        print(f"  effect:   {review.get('expected_behavior_change')}")
    if review.get("risk_summary"):
        print(f"  risk:     {review.get('risk_summary')}")
    if review.get("rollback_plan"):
        print(f"  rollback: {review.get('rollback_plan')}")
    print(f"  decide:   {packet.get('decision_route')}")

    follow_through = packet.get("follow_through") or {}
    if follow_through:
        print(
            "  follow:   "
            f"{follow_through.get('status')} "
            f"(decisions={follow_through.get('decision_events', 0)}, "
            f"outcomes={follow_through.get('outcome_links', 0)}, "
            f"reviews={follow_through.get('routine_reviews', 0)}, "
            f"learning_use={follow_through.get('learning_use_receipts', 0)})"
        )

    missing = review.get("missing_evidence") or []
    failed = review.get("failed_invariants") or []
    unknown = review.get("unknown_invariants") or []
    if missing:
        print(f"  missing:  {', '.join(str(item) for item in missing[:6])}")
    if failed:
        print(f"  failed:   {', '.join(str(item) for item in failed[:6])}")
    if unknown:
        print(f"  unknown:  {', '.join(str(item) for item in unknown[:6])}")

    provenance = packet.get("provenance_report") or {}
    if provenance:
        summary = provenance.get("summary") or {}
        coverage = provenance.get("coverage") or {}
        print(
            "  provenance: "
            f"{summary.get('event_count', 0)} event(s), "
            f"coverage={coverage.get('status')}"
        )
        for caveat in provenance.get("caveats", [])[:3]:
            print(f"  caveat:   {caveat}")

    questions = packet.get("review_questions") or []
    if questions:
        print()
        print("  review questions:")
        for question in questions[:5]:
            print(f"    - {question}")

    refs = packet.get("evidence_refs") or []
    if refs:
        ref_limit = max(0, int(args.ref_limit))
        print()
        print("  evidence refs:")
        for row in refs[:ref_limit]:
            sources = ",".join(row.get("sources") or [])
            invariants = ",".join(row.get("invariants") or [])
            suffix = f" [{sources}]"
            if invariants:
                suffix = f"{suffix} invariants={invariants}"
            print(f"    - {row.get('ref')}{suffix}")
        if len(refs) > ref_limit:
            print(f"    ... {len(refs) - ref_limit} more ref(s)")
    return 0


def _cmd_proposal_template(args: argparse.Namespace) -> int:
    """Print a service-generated governance proposal request template."""
    params = {
        "change_kind": args.change_kind,
        "title": args.title,
        "proposed_by": args.proposed_by,
        "target_ref": args.target_ref,
        "tenant_id": args.tenant_id,
        "project_id": args.project_id,
    }
    query = urlencode({key: value for key, value in params.items() if value})
    path = "/kernel/governance-change-template"
    if query:
        path = f"{path}?{query}"
    response = dispatch_kernel_request("GET", path)
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    print(json.dumps(response.payload.get("template", {}), indent=2, sort_keys=True))
    return 0


def _cmd_timeline(args: argparse.Namespace) -> int:
    """Print a read-only provenance timeline for a run, ref, or scope."""
    if not _validate_provenance_scope_args(args, "timeline"):
        return 2
    params = {
        "run_id": args.run_id,
        "ref": args.ref,
        "tenant_id": args.tenant_id,
        "project_id": args.project_id,
    }
    query = urlencode({key: value for key, value in params.items() if value})
    path = "/kernel/provenance-timeline"
    if query:
        path = f"{path}?{query}"
    response = dispatch_kernel_request("GET", path)
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    timeline = response.payload.get("timeline", {})
    events = timeline.get("events", [])
    print(f"provenance timeline - {len(events)} event(s), read-only")

    query_payload = timeline.get("query", {})
    query_bits = [
        f"{key}={value}"
        for key, value in query_payload.items()
        if value is not None
    ]
    if query_bits:
        print(f"  query: {', '.join(query_bits)}")

    counts = timeline.get("counts", {})
    if counts:
        count_bits = [f"{key}={counts[key]}" for key in sorted(counts)]
        print(f"  counts: {', '.join(count_bits)}")

    for caveat in timeline.get("caveats", []):
        print(f"  caveat: {caveat}")

    for event in events:
        print()
        print(
            f"  [{event.get('occurred_at_utc')}] "
            f"{event.get('event_kind')} ({event.get('source')})"
        )
        print(f"    object:  {event.get('object_ref')}")
        actor = event.get("actor")
        if actor:
            print(f"    actor:   {actor}")
        summary = event.get("summary")
        if summary:
            print(f"    summary: {summary}")
        refs = event.get("related_refs") or []
        if refs:
            rendered_refs = ", ".join(str(ref) for ref in refs[:5])
            print(f"    refs:    {rendered_refs}")
    return 0


def _cmd_human_pressure(args: argparse.Namespace) -> int:
    """Print observer-only A2H human-work pressure groups."""
    params = {
        "agent_counterparty_role": args.agent_counterparty_role,
        "tenant_id": args.tenant_id,
        "project_id": args.project_id,
        "stale_after_hours": args.stale_after_hours,
        "concentration_threshold": args.concentration_threshold,
    }
    query = urlencode({key: value for key, value in params.items() if value is not None})
    path = "/kernel/human-work-pressure"
    if query:
        path = f"{path}?{query}"
    response = dispatch_kernel_request("GET", path)
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    pressure = response.payload.get("pressure", [])
    print(f"human-work pressure - {len(pressure)} group(s), observer-only")
    query_payload = response.payload.get("query", {})
    query_bits = [
        f"{key}={value}"
        for key, value in query_payload.items()
        if value is not None
    ]
    if query_bits:
        print(f"  query: {', '.join(query_bits)}")
    for caveat in response.payload.get("caveats", []):
        print(f"  caveat: {caveat}")

    for group in pressure:
        print()
        print(
            f"  {group.get('agent_counterparty_role')} / "
            f"{group.get('bottleneck_class')}"
        )
        print(
            f"    active: {group.get('active_count')}, "
            f"waiting: {group.get('waiting_count')}, "
            f"missing_receipts: {group.get('missing_receipt_count')}, "
            f"stale: {group.get('stale_count')}"
        )
        print(f"    recommendation: {group.get('recommendation')}")
        session_ids = group.get("session_ids") or []
        if session_ids:
            print(f"    sessions: {', '.join(str(item) for item in session_ids[:5])}")
    return 0


def _cmd_speed_envelope(args: argparse.Namespace) -> int:
    """Print the accountable speed envelope for a proposed work item."""
    params = {
        "risk_tier": args.risk_tier,
        "bottleneck_class": args.bottleneck_class,
        "deployment_class": args.deployment_class,
        "reversible": str(args.reversible).lower(),
        "external_side_effect": str(args.external_side_effect).lower(),
        "repeated_similar": str(args.repeated_similar).lower(),
        "private_context": str(args.private_context).lower(),
        "harm_occurred": str(args.harm_occurred).lower(),
        "residual_risk_accepted": str(args.residual_risk_accepted).lower(),
    }
    query = urlencode({key: value for key, value in params.items() if value is not None})
    response = dispatch_kernel_request("GET", f"/kernel/human-speed-envelope?{query}")
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    envelope = response.payload.get("envelope", {})
    print("human-speed envelope")
    print(f"  class:   {envelope.get('speed_class')}")
    print(f"  cadence: {envelope.get('cadence')}")
    print(f"  record:  {envelope.get('required_record')}")
    print(f"  receipt_required: {str(envelope.get('receipt_required')).lower()}")
    print(f"  sample_for_review: {str(envelope.get('sample_for_review')).lower()}")
    if envelope.get("sample_rate") is not None:
        print(f"  sample_rate: {envelope.get('sample_rate')}")
    print(f"  gate_required: {str(envelope.get('gate_required')).lower()}")
    print(
        "  accountability_case_recommended: "
        f"{str(envelope.get('accountability_case_recommended')).lower()}"
    )
    print(f"  rationale: {envelope.get('rationale')}")
    for question in envelope.get("review_questions", []):
        print(f"  review: {question}")
    for caveat in response.payload.get("caveats", []):
        print(f"  caveat: {caveat}")
    return 0


def _cmd_learning_candidates(args: argparse.Namespace) -> int:
    """Print observer-only learning-transition candidates."""
    params = {
        "source": args.source,
        "include_closed": "true" if args.include_closed else None,
    }
    query = urlencode({key: value for key, value in params.items() if value is not None})
    response = dispatch_kernel_request("GET", f"/kernel/learning-transition-candidates?{query}")
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    candidates = response.payload.get("candidates") or []
    print(
        "learning-transition candidates - "
        f"{len(candidates)} candidate(s), observer-only"
    )
    print(f"  source: {response.payload.get('source')}")
    source_counts = response.payload.get("source_counts") or {}
    if source_counts:
        rendered_counts = ", ".join(
            f"{key}={value}"
            for key, value in sorted(source_counts.items())
            if value
        )
        if rendered_counts:
            print(f"  source_counts: {rendered_counts}")

    limit = max(0, int(args.limit))
    for candidate in candidates[:limit]:
        print()
        print(
            f"  [{candidate.get('severity')}] {candidate.get('candidate_id')} "
            f"{candidate.get('transition_kind')}"
        )
        print(f"    source: {candidate.get('source_kind')}")
        if candidate.get("object_ref"):
            print(f"    object: {candidate.get('object_ref')}")
        if candidate.get("suggested_owner_role"):
            print(f"    owner:  {candidate.get('suggested_owner_role')}")
        if candidate.get("rationale"):
            print(f"    why:    {candidate.get('rationale')}")
        if candidate.get("review_question"):
            print(f"    review: {candidate.get('review_question')}")
        refs = candidate.get("source_refs") or []
        if refs:
            print(f"    refs:   {', '.join(str(ref) for ref in refs[:5])}")
    if len(candidates) > limit:
        print()
        print(f"  ... {len(candidates) - limit} more candidate(s) not shown")
    return 0


def _cmd_lease_acquire(args: argparse.Namespace) -> int:
    """Acquire a mutation lease for a guarded kernel write."""
    body: dict[str, Any] = {
        "resource_ref": args.resource_ref,
        "ttl_seconds": args.ttl_seconds,
    }
    if args.purpose:
        body["purpose"] = args.purpose
    actor_context: dict[str, Any] = {}
    if args.actor:
        actor_context["actor_id"] = args.actor
    if args.role:
        actor_context["role_id"] = args.role
    if actor_context:
        body["actor_context"] = actor_context

    response = dispatch_kernel_request("POST", "/kernel/leases", body)
    if response.status not in {200, 201}:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    lease = response.payload.get("lease") or {}
    print(f"lease {lease.get('lease_id')} acquired")
    print(f"  resource:      {lease.get('resource_ref')}")
    print(f"  holder:        {lease.get('held_by_actor_id')}")
    if lease.get("held_by_role_id"):
        print(f"  role:          {lease.get('held_by_role_id')}")
    print(f"  fencing_token: {lease.get('fencing_token')}")
    print(f"  expires:       {lease.get('expires_at_utc')}")
    print(
        "  use:           "
        f"--lease-id {lease.get('lease_id')} "
        f"--fencing-token {lease.get('fencing_token')}"
    )
    return 0


def _cmd_leases(args: argparse.Namespace) -> int:
    """List mutation leases visible through the kernel service."""
    params = {
        "resource_ref": args.resource_ref,
        "state": args.state,
    }
    query = urlencode({key: value for key, value in params.items() if value})
    path = "/kernel/leases"
    if query:
        path = f"{path}?{query}"
    response = dispatch_kernel_request("GET", path)
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    leases = response.payload.get("leases") or []
    print(f"leases - {len(leases)} lease(s), read-only")
    query_bits = [f"{key}={value}" for key, value in params.items() if value]
    if query_bits:
        print(f"  query: {', '.join(query_bits)}")
    limit = max(0, int(args.limit))
    for lease in leases[:limit]:
        print()
        print(f"  [{lease.get('state')}] {lease.get('lease_id')}")
        print(f"    resource: {lease.get('resource_ref')}")
        print(f"    holder:   {lease.get('held_by_actor_id')}")
        if lease.get("held_by_role_id"):
            print(f"    role:     {lease.get('held_by_role_id')}")
        print(f"    token:    {lease.get('fencing_token')}")
        print(f"    expires:  {lease.get('expires_at_utc')}")
    if len(leases) > limit:
        print()
        print(f"  ... {len(leases) - limit} more lease(s) not shown")
    return 0


def _cmd_lease_release(args: argparse.Namespace) -> int:
    """Release a mutation lease held by the actor."""
    body: dict[str, Any] = {}
    actor_context: dict[str, Any] = {}
    if args.actor:
        actor_context["actor_id"] = args.actor
    if args.role:
        actor_context["role_id"] = args.role
    if actor_context:
        body["actor_context"] = actor_context
    response = dispatch_kernel_request(
        "POST", f"/kernel/leases/{args.lease_id}/release", body
    )
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    lease = response.payload.get("lease") or {}
    print(f"lease {lease.get('lease_id')} released")
    print(f"  resource: {lease.get('resource_ref')}")
    print(f"  state:    {lease.get('state')}")
    print(f"  holder:   {lease.get('held_by_actor_id')}")
    return 0


def _cmd_decision_profiles(_args: argparse.Namespace) -> int:
    """Print built-in decision procedure profiles as read-only recipes."""
    response = dispatch_kernel_request("GET", "/kernel/decision-procedure-profiles")
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    profiles = response.payload.get("decision_procedure_profiles") or []
    print(f"decision procedure profiles - {len(profiles)} profile(s), read-only")
    print("  binding: evidence_only")
    for profile in profiles:
        print()
        print(f"  {profile.get('profile_id')}")
        print(f"    procedure: {profile.get('procedure_kind')}")
        print(f"    quorum:    {profile.get('quorum_rule')}")
        print(f"    binding:   {profile.get('binding_semantics')}")
        print(f"    why:       {profile.get('description')}")
    return 0


def _cmd_decision_cases(args: argparse.Namespace) -> int:
    """Print decision aggregation cases as procedure evidence."""
    params = {
        "status": args.status,
        "procedure_kind": args.procedure_kind,
        "subject_ref": args.subject_ref,
    }
    query = urlencode({key: value for key, value in params.items() if value})
    path = "/kernel/decision-aggregation-cases"
    if query:
        path = f"{path}?{query}"
    response = dispatch_kernel_request("GET", path)
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    cases = response.payload.get("decision_aggregation_cases") or []
    print(
        "decision aggregation cases - "
        f"{len(cases)} case(s), evidence-only"
    )
    query_bits = [f"{key}={value}" for key, value in params.items() if value]
    if query_bits:
        print(f"  query: {', '.join(query_bits)}")
    limit = max(0, int(args.limit))
    for case in cases[:limit]:
        result = case.get("result") or {}
        positions = case.get("positions") or []
        print()
        print(f"  [{case.get('status')}] {case.get('case_id')}")
        print(f"    subject:   {case.get('subject_ref')}")
        print(f"    decision:  {case.get('decision_class')}")
        print(
            f"    procedure: {case.get('procedure_kind')} "
            f"quorum={case.get('quorum')}"
        )
        print(f"    scope:     {case.get('scope_kind')}:{case.get('scope_ref')}")
        print(f"    positions: {len(positions)}")
        if result:
            print(
                f"    result:    {result.get('recommendation')} - "
                f"{result.get('rationale')}"
            )
    if len(cases) > limit:
        print()
        print(f"  ... {len(cases) - limit} more case(s) not shown")
    return 0


def _cmd_decision_open(args: argparse.Namespace) -> int:
    """Open a decision aggregation evidence case through the service route."""
    body: dict[str, Any] = {
        "subject_ref": args.subject_ref,
        "decision_class": args.decision_class,
        "scope_kind": args.scope_kind,
        "scope_ref": args.scope_ref,
        "eligibility_basis": args.eligibility_basis,
        "eligible_roles": args.eligible_role,
        "eligible_actors": args.eligible_actor,
    }
    if args.procedure_profile:
        body["procedure_profile"] = args.procedure_profile
    else:
        body["procedure_kind"] = args.procedure_kind
    for attr, key in (
        ("opened_by", "opened_by"),
        ("quorum", "quorum"),
        ("tie_breaker_role", "tie_breaker_role"),
        ("downstream_ref", "downstream_ref"),
        ("tenant_id", "tenant_id"),
        ("project_id", "project_id"),
        ("case_id", "case_id"),
    ):
        value = getattr(args, attr)
        if value is not None:
            body[key] = value
    if args.evidence_ref:
        body["evidence_refs"] = args.evidence_ref
    if args.actor:
        body["actor_context"] = {"actor_id": args.actor}
    _attach_lease_args(body, args)

    response = dispatch_kernel_request(
        "POST", "/kernel/decision-aggregation-cases", body
    )
    if response.status not in {200, 201}:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    case = response.payload.get("decision_aggregation_case") or {}
    print(f"decision aggregation case {case.get('case_id')} opened")
    print("  binding:   evidence_only")
    print(f"  subject:   {case.get('subject_ref')}")
    print(f"  decision:  {case.get('decision_class')}")
    print(f"  procedure: {case.get('procedure_kind')} quorum={case.get('quorum')}")
    if case.get("metadata", {}).get("procedure_profile"):
        print(f"  profile:   {case['metadata'].get('procedure_profile')}")
    roles = len(case.get("eligible_roles") or [])
    actors = len(case.get("eligible_actors") or [])
    print(f"  eligible:  roles={roles}, actors={actors}")
    return 0


def _cmd_decision_position(args: argparse.Namespace) -> int:
    """Record one eligible actor/role position on a decision aggregation case."""
    body: dict[str, Any] = {
        "actor_id": args.actor_id,
        "role_id": args.role_id,
        "position": args.position,
        "rationale": args.rationale,
    }
    if args.evidence_ref:
        body["evidence_refs"] = args.evidence_ref
    if args.position_id:
        body["position_id"] = args.position_id
    _attach_lease_args(body, args)

    response = dispatch_kernel_request(
        "POST",
        f"/kernel/decision-aggregation-cases/{args.case_id}/positions",
        body,
    )
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    case = response.payload.get("decision_aggregation_case") or {}
    positions = case.get("positions") or []
    print(f"decision position recorded for {case.get('case_id')}")
    print(f"  actor:     {args.actor_id}")
    print(f"  role:      {args.role_id}")
    print(f"  position:  {args.position}")
    print(f"  positions: {len(positions)}")
    return 0


def _cmd_decision_compute(args: argparse.Namespace) -> int:
    """Compute a deterministic decision aggregation recommendation."""
    body: dict[str, Any] = {}
    if args.actor:
        body["actor_context"] = {"actor_id": args.actor}
    _attach_lease_args(body, args)
    response = dispatch_kernel_request(
        "POST",
        f"/kernel/decision-aggregation-cases/{args.case_id}/compute",
        body,
    )
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    case = response.payload.get("decision_aggregation_case") or {}
    result = case.get("result") or {}
    print(f"decision aggregation case {case.get('case_id')} computed")
    print("  binding:        evidence_only")
    print(f"  status:         {case.get('status')}")
    print(f"  recommendation: {result.get('recommendation')}")
    print(f"  quorum_met:     {str(bool(result.get('quorum_met'))).lower()}")
    print(f"  rationale:      {result.get('rationale')}")
    return 0


def _cmd_decision_route_escalation(args: argparse.Namespace) -> int:
    """Route an escalated decision aggregation case into learning review."""
    body: dict[str, Any] = {
        "summary": args.summary,
        "owner_role": args.owner_role,
        "severity": args.severity,
    }
    for attr, key in (
        ("signal_id", "signal_id"),
        ("signal_kind", "signal_kind"),
        ("tenant_id", "tenant_id"),
        ("project_id", "project_id"),
        ("worker_ref", "worker_ref"),
        ("run_id", "run_id"),
        ("work_id", "work_id"),
        ("recommended_route", "recommended_route"),
        ("route_kind", "route_kind"),
        ("route_target_ref", "route_target_ref"),
        ("route_rationale", "route_rationale"),
        ("proposed_by", "proposed_by"),
        ("actor", "routed_by"),
    ):
        value = getattr(args, attr)
        if value:
            body[key] = value
    if args.evidence_ref:
        body["evidence_refs"] = args.evidence_ref
    if args.actor:
        body["actor_context"] = {"actor_id": args.actor}
    _attach_lease_args(body, args)

    response = dispatch_kernel_request(
        "POST",
        f"/kernel/decision-aggregation-cases/{args.case_id}/route-escalation",
        body,
    )
    if response.status not in {200, 201}:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    candidate = response.payload.get("learning_candidate") or {}
    boundary = response.payload.get("boundary") or {}
    print(f"decision aggregation escalation routed for {args.case_id}")
    print(f"  candidate: {candidate.get('candidate_id')}")
    print(f"  route:     {candidate.get('source_kind')}")
    print(f"  boundary:  resolved_decision={boundary.get('resolved_decision')}")
    print(f"  override:  {boundary.get('overrode_aggregation')}")
    return 0


def _cmd_graph(args: argparse.Namespace) -> int:
    """Print a read-only provenance graph for a run, ref, or scope."""
    if not _validate_provenance_scope_args(args, "graph"):
        return 2
    params = {
        "run_id": args.run_id,
        "ref": args.ref,
        "tenant_id": args.tenant_id,
        "project_id": args.project_id,
    }
    query = urlencode({key: value for key, value in params.items() if value})
    path = "/kernel/provenance-graph"
    if query:
        path = f"{path}?{query}"
    response = dispatch_kernel_request("GET", path)
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    graph = response.payload.get("graph", {})
    counts = graph.get("counts", {})
    print(
        "provenance graph - "
        f"{counts.get('nodes', 0)} node(s), {counts.get('edges', 0)} edge(s), "
        "read-only projection"
    )

    query_payload = graph.get("query", {})
    query_bits = [
        f"{key}={value}"
        for key, value in query_payload.items()
        if value is not None
    ]
    if query_bits:
        print(f"  query: {', '.join(query_bits)}")

    for caveat in graph.get("caveats", []):
        print(f"  caveat: {caveat}")

    nodes = graph.get("nodes", [])
    if nodes:
        event_count = sum(1 for node in nodes if node.get("node_kind") == "event")
        ref_count = sum(1 for node in nodes if node.get("node_kind") == "ref")
        print(f"  nodes: event={event_count}, ref={ref_count}")

    edges = graph.get("edges", [])
    for edge in edges[: args.limit]:
        print()
        print(
            f"  {edge.get('from_ref')} --{edge.get('relation')}--> "
            f"{edge.get('to_ref')}"
        )
        source = edge.get("source")
        if source:
            print(f"    source: {source}")
    if len(edges) > args.limit:
        print(f"\n  ... {len(edges) - args.limit} more edge(s)")
    return 0


def _cmd_provenance_report(args: argparse.Namespace) -> int:
    """Print a portable read-only provenance report for reviewer handoff."""
    if not _validate_provenance_scope_args(args, "provenance-report"):
        return 2
    params = {
        "run_id": args.run_id,
        "ref": args.ref,
        "tenant_id": args.tenant_id,
        "project_id": args.project_id,
        "event_limit": args.event_limit,
    }
    query = urlencode({key: value for key, value in params.items() if value is not None})
    path = "/kernel/provenance-report"
    if query:
        path = f"{path}?{query}"
    response = dispatch_kernel_request("GET", path)
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    report = response.payload.get("report", {})
    if args.markdown:
        markdown = str(report.get("markdown") or "").rstrip()
        if markdown:
            print(markdown)
        return 0

    summary = report.get("summary", {})
    coverage = report.get("coverage", {})
    print(
        "provenance report - "
        f"{summary.get('event_count', 0)} event(s), "
        f"coverage={coverage.get('status')}, read-only projection"
    )
    query_payload = report.get("query", {})
    query_bits = [
        f"{key}={value}"
        for key, value in query_payload.items()
        if value is not None
    ]
    if query_bits:
        print(f"  query: {', '.join(query_bits)}")
    print(f"  refs:  {summary.get('evidence_ref_count', 0)} high-signal ref(s)")
    source_counts = summary.get("source_counts") or {}
    if source_counts:
        count_bits = [f"{key}={source_counts[key]}" for key in sorted(source_counts)]
        print(f"  counts: {', '.join(count_bits)}")

    for caveat in report.get("caveats", []):
        print(f"  caveat: {caveat}")
    for gap in coverage.get("gaps", []):
        print(f"  gap:    {gap}")

    questions = report.get("review_questions") or []
    if questions:
        print()
        print("  review questions:")
        for question in questions[:4]:
            print(f"    - {question}")

    events = report.get("event_excerpt") or []
    if events:
        print()
        print("  timeline excerpt:")
        for event in events:
            print(
                "    - "
                f"{event.get('occurred_at_utc')} "
                f"{event.get('event_kind')} "
                f"({event.get('source')}): "
                f"{event.get('summary')}"
            )

    refs = report.get("evidence_refs") or []
    if refs:
        ref_limit = max(0, int(args.ref_limit))
        print()
        print("  high-signal refs:")
        for row in refs[:ref_limit]:
            print(
                "    - "
                f"{row.get('ref')} "
                f"[{row.get('ref_kind')}, mentions={row.get('mention_count')}]"
            )
        if len(refs) > ref_limit:
            print(f"    ... {len(refs) - ref_limit} more ref(s)")
    return 0


def _cmd_work_context(args: argparse.Namespace) -> int:
    """Print read-only learning context for a role before work starts."""
    params: dict[str, str | int | None] = {
        "assigned_to": args.assigned_to,
        "tenant_id": args.tenant_id,
        "project_id": args.project_id,
        "cue": args.cue,
        "cue_signature": args.cue_signature,
        "max_per_source": args.max_per_source,
        "learning_only": "true" if args.learning_only else None,
    }
    list_params = {
        "resource_ref": args.resource_ref,
        "topology_ref": args.topology_ref,
    }
    query = urlencode(
        {
            **{key: value for key, value in params.items() if value},
            **{key: value for key, value in list_params.items() if value},
        },
        doseq=True,
    )
    response = dispatch_kernel_request("GET", f"/kernel/work-discovery?{query}")
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    context = response.payload
    learning_rows = context.get("learning_context", [])
    candidates = context.get("work_candidates", [])
    print(
        "work context - "
        f"{len(learning_rows)} learning event(s), "
        f"{len(candidates)} candidate(s), read-only"
    )
    assigned_to = context.get("assigned_to") or "structured query"
    print(f"  assigned_to: {assigned_to}")
    if context.get("tenant_id"):
        print(f"  tenant_id:   {context.get('tenant_id')}")
    if context.get("project_id"):
        print(f"  project_id:  {context.get('project_id')}")
    if context.get("cue"):
        print(f"  cue:         {context.get('cue')}")
    if context.get("cue_signature"):
        print(f"  cue_sig:     {context.get('cue_signature')}")
    if context.get("resource_refs"):
        print("  resources:   " + ", ".join(str(ref) for ref in context["resource_refs"]))
    if context.get("topology_refs"):
        print("  topology:    " + ", ".join(str(ref) for ref in context["topology_refs"]))

    packet = context.get("context_packet", {})
    basis = packet.get("basis", {})
    if packet:
        print(f"  packet:      {packet.get('context_packet_id')}")
        print(f"  digest:      {str(packet.get('digest', ''))[:24]}")
        print(f"  policy:      {packet.get('write_policy')}")
        print(
            "  basis:       "
            f"learning_events={len(basis.get('learning_event_ids', []))}, "
            f"outcome_links={len(basis.get('outcome_link_ids', []))}, "
            f"overdue_reviews={len(basis.get('overdue_review_ids', []))}"
        )
        if basis.get("work_candidates_included") is False and not context.get("assigned_to"):
            print("  candidates:  suppressed for no-role structured query")

    for row in learning_rows:
        event = row.get("learning_event", {})
        print()
        print(
            f"  [{event.get('status')}] "
            f"{event.get('decision_use')}"
        )
        print(f"    id:       {event.get('learning_event_id')}")
        if event.get("future_application_cue"):
            print(f"    cue:      {event.get('future_application_cue')}")
        if row.get("approval_ref"):
            print(f"    approval: {row.get('approval_ref')}")
        if row.get("outcome_links"):
            print(f"    outcomes: {len(row.get('outcome_links'))}")
        if row.get("overdue_review_ids"):
            print(
                "    overdue:  "
                + ", ".join(str(item) for item in row["overdue_review_ids"])
            )

    if candidates:
        print()
        print("  work candidates:")
        for candidate in candidates:
            print(
                f"    - [{candidate.get('severity')}] "
                f"{candidate.get('source')}: {candidate.get('intent')}"
            )
    return 0


def _cmd_context_packet_verify(args: argparse.Namespace) -> int:
    """Verify a captured work-context packet without writing kernel state."""
    try:
        raw = json.loads(Path(args.packet_json).read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"ERROR: cannot read packet JSON: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"ERROR: cannot parse packet JSON: {exc}", file=sys.stderr)
        return 2

    if isinstance(raw, dict) and "context_packet" in raw:
        packet = raw.get("context_packet")
    elif isinstance(raw, dict):
        packet = raw
    else:
        packet = None
    if not isinstance(packet, dict):
        print(
            "ERROR: context packet JSON must contain an object",
            file=sys.stderr,
        )
        return 2
    response = dispatch_kernel_request(
        "POST",
        "/kernel/work-discovery/context-packet/verify",
        {"context_packet": packet},
    )
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    verification = response.payload.get("verification", {})
    ok = bool(verification.get("ok"))
    print("context packet verification")
    print(f"  ok:          {str(ok).lower()}")
    print(f"  packet:      {verification.get('context_packet_id')}")
    print(f"  expected:    {verification.get('expected_context_packet_id')}")
    digest = str(verification.get("digest") or "")
    expected_digest = str(verification.get("expected_digest") or "")
    if digest:
        print(f"  digest:      {digest[:24]}")
    if expected_digest:
        print(f"  recomputed:  {expected_digest[:24]}")
    print(f"  policy:      {verification.get('verification_policy')}")
    issues = verification.get("issues") or []
    if issues:
        print("  issues:")
        for issue in issues:
            print(f"    - {issue}")
    return 0 if ok else 1


def _cmd_composition_packet(args: argparse.Namespace) -> int:
    """Build a read-only governed-action composition packet."""
    try:
        raw = json.loads(Path(args.observed_json).read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"ERROR: cannot read observed JSON: {exc}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as exc:
        print(f"ERROR: cannot parse observed JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(raw, dict):
        print("ERROR: observed JSON must contain an object", file=sys.stderr)
        return 2
    observed = raw.get("observed_result")
    if observed is None:
        observed = raw.get("result")
    if observed is None:
        observed = raw
    if not isinstance(observed, dict):
        print("ERROR: observed_result must contain an object", file=sys.stderr)
        return 2

    response = dispatch_kernel_request(
        "POST",
        "/kernel/governed-action-composition",
        {
            "action_label": args.action_label,
            "profile": args.profile,
            "observed_result": observed,
            "evidence_refs": args.evidence_ref,
            "metadata": {"source_file": str(Path(args.observed_json))},
        },
    )
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    packet = response.payload.get("composition_packet", {})
    summary = packet.get("summary", {})
    status = str(packet.get("status") or "unknown")
    print("governed action composition")
    print(f"  status:      {status}")
    print(f"  profile:     {packet.get('profile')}")
    print(f"  action:      {packet.get('action_label')}")
    print(f"  read_only:   {str(bool(packet.get('read_only'))).lower()}")
    print(
        "  links:       "
        f"{summary.get('passed_links', 0)}/"
        f"{summary.get('required_links', 0)} required passed"
    )
    print(f"  blockers:    {summary.get('required_blockers', 0)}")

    blockers = [
        row
        for row in packet.get("links", [])
        if row.get("required") and row.get("status") in {"missing", "failed"}
    ]
    if blockers:
        print()
        print("  required blockers:")
        for row in blockers:
            print(
                "    - "
                f"{row.get('link_id')}: {row.get('status')} "
                f"({row.get('label')})"
            )
    questions = packet.get("review_questions") or []
    if questions:
        print()
        print("  review questions:")
        for question in questions[:4]:
            print(f"    - {question}")
    return 0 if status == "ready_for_review" else 1


def _cmd_learning_use(args: argparse.Namespace) -> int:
    """Record that a work surface encountered or used approved learning."""
    body: dict[str, Any] = {
        "learning_event_id": args.learning_event_id,
        "role": args.role,
        "cue": args.cue,
        "outcome": args.outcome,
    }
    if args.context_packet_json:
        try:
            raw = json.loads(Path(args.context_packet_json).read_text(encoding="utf-8"))
        except OSError as exc:
            print(f"ERROR: cannot read context packet JSON: {exc}", file=sys.stderr)
            return 2
        except json.JSONDecodeError as exc:
            print(f"ERROR: cannot parse context packet JSON: {exc}", file=sys.stderr)
            return 2
        if isinstance(raw, dict) and "context_packet" in raw:
            packet = raw.get("context_packet")
        elif isinstance(raw, dict):
            packet = raw
        else:
            packet = None
        if not isinstance(packet, dict):
            print(
                "ERROR: context packet JSON must contain an object",
                file=sys.stderr,
            )
            return 2
        body["context_packet"] = packet
        if (
            isinstance(packet, dict)
            and packet.get("context_packet_id")
            and not args.context_packet_ref
        ):
            body["context_packet_ref"] = str(packet["context_packet_id"])
    for attr, key in (
        ("work_ref", "work_ref"),
        ("tenant_id", "tenant_id"),
        ("project_id", "project_id"),
        ("reason", "reason"),
        ("context_packet_ref", "context_packet_ref"),
        ("idempotency_key", "idempotency_key"),
    ):
        value = getattr(args, attr)
        if value:
            body[key] = value
    if args.evidence_ref:
        body["evidence_refs"] = args.evidence_ref
    _attach_lease_args(body, args)

    response = dispatch_kernel_request(
        "POST", "/kernel/learning-event-encounters", body
    )
    if response.status not in {200, 201}:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    encounter = response.payload.get("encounter", {})
    print(f"learning-use receipt {encounter.get('encounter_id')}")
    print(f"  learning_event: {encounter.get('learning_event_id')}")
    print(f"  role:           {encounter.get('role')}")
    print(f"  outcome:        {encounter.get('outcome')}")
    if encounter.get("work_ref"):
        print(f"  work_ref:       {encounter.get('work_ref')}")
    if encounter.get("context_packet_ref"):
        print(f"  context_packet: {encounter.get('context_packet_ref')}")
    refs = encounter.get("evidence_refs") or []
    if refs:
        print(f"  evidence_refs:  {', '.join(str(ref) for ref in refs)}")
    if encounter.get("reason"):
        print(f"  reason:         {encounter.get('reason')}")
    return 0


def _cmd_learning_loop(args: argparse.Namespace) -> int:
    """Inspect one approved learning event's compounding loop."""
    response = dispatch_kernel_request(
        "GET", f"/kernel/learning-events/{args.learning_event_id}/loop"
    )
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    loop = response.payload.get("learning_loop", {})
    learned = loop.get("learned") or {}
    future = loop.get("future_context") or {}
    print(f"learning loop {loop.get('learning_event_id')}")
    print(f"  state:          {loop.get('loop_state')}")
    print(f"  recommendation: {loop.get('recommendation')}")
    print(f"  learned:        {learned.get('decision_use')}")
    print(f"  cue:            {learned.get('future_application_cue')}")
    if learned.get("owner_role"):
        print(f"  owner:          {learned.get('owner_role')}")
    if learned.get("approved_by"):
        print(f"  approved_by:    {learned.get('approved_by')}")
    if learned.get("approval_ref"):
        print(f"  approval_ref:   {learned.get('approval_ref')}")
    if learned.get("review_after_utc"):
        print(f"  review_after:   {learned.get('review_after_utc')}")

    print()
    print("  future context")
    for label, key in (
        ("cue_signatures", "cue_signatures"),
        ("resource_refs", "resource_refs"),
        ("topology_refs", "topology_refs"),
        ("context_packets", "context_packet_refs"),
        ("verified_packets", "verified_context_packet_refs"),
    ):
        values = future.get(key) or []
        if values:
            print(f"    {label}: {', '.join(str(v) for v in values)}")

    print()
    print("  use and measurement")
    counts = loop.get("encounter_counts") or {}
    print(
        "    encounters: "
        + ", ".join(
            f"{key}={counts.get(key, 0)}"
            for key in ("applied", "deferred", "ignored", "encountered")
        )
    )
    print(f"    outcome_links: {loop.get('outcome_link_count', 0)}")
    print(
        "    verdict_coverage: "
        f"{float(loop.get('outcome_verdict_coverage') or 0):.2f}"
    )
    verdicts = loop.get("outcome_verdict_counts") or {}
    if verdicts:
        print(
            "    verdicts: "
            + ", ".join(f"{key}={value}" for key, value in sorted(verdicts.items()))
        )
    print(f"    routine_reviews: {loop.get('routine_review_count', 0)}")
    overdue = loop.get("overdue_review_ids") or []
    if overdue:
        print(f"    overdue: {', '.join(str(item) for item in overdue)}")

    evidence = loop.get("evidence_refs") or []
    if evidence:
        print()
        print(f"  evidence refs: {len(evidence)}")
        for ref in evidence[:8]:
            print(f"    - {ref}")
        if len(evidence) > 8:
            print(f"    ... {len(evidence) - 8} more")
    return 0


def _cmd_receipt(args: argparse.Namespace) -> int:
    """Record a structured receipt for bounded human work."""
    body: dict[str, Any] = {
        "actor": args.actor,
        "summary": args.summary,
        "receipt_type": args.receipt_type,
        "confidence": args.confidence,
        "observability": args.observability,
        "review_required": args.review_required,
    }
    if args.receipt_ref:
        body["receipt_ref"] = args.receipt_ref
    if args.subject_ref:
        body["subject_refs"] = list(args.subject_ref)
    if args.artifact_ref:
        body["artifact_refs"] = list(args.artifact_ref)

    metadata: dict[str, Any] = {}
    for attr, key in (
        ("agent_output_ref", "agent_output_ref"),
        ("action_attestation_ref", "action_attestation_ref"),
        ("review_decision", "review_decision"),
    ):
        value = getattr(args, attr)
        if value:
            metadata[key] = value
    for ref in (args.agent_output_ref, args.action_attestation_ref):
        if ref:
            body.setdefault("subject_refs", [])
            if ref not in body["subject_refs"]:
                body["subject_refs"].append(ref)
    if metadata:
        body["metadata"] = metadata
    _attach_lease_args(body, args)

    response = dispatch_kernel_request(
        "POST", f"/kernel/human-work/{args.session_id}/receipt", body
    )
    if response.status not in {200, 201}:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    session = response.payload.get("session", {})
    receipts = session.get("work_receipts") or []
    receipt = receipts[-1] if receipts else {}
    print(f"human-work receipt {receipt.get('receipt_id')}")
    print(f"  session:     {session.get('session_id')}")
    print(f"  actor:       {receipt.get('actor')}")
    print(f"  type:        {receipt.get('receipt_type')}")
    print(f"  confidence:  {receipt.get('confidence')}")
    if receipt.get("subject_refs"):
        print("  subjects:    " + ", ".join(str(ref) for ref in receipt["subject_refs"]))
    if receipt.get("artifact_refs"):
        print("  artifacts:   " + ", ".join(str(ref) for ref in receipt["artifact_refs"]))
    if receipt.get("review_required"):
        print("  review:      required")
    print(f"  receipts:    {len(receipts)}")
    return 0


def _cmd_proposal_from_candidate(args: argparse.Namespace) -> int:
    """Create a governance-change proposal from a learning candidate."""
    body: dict[str, Any] = {
        "source": args.source,
        "include_closed": args.include_closed,
        "target_ref": args.target_ref,
    }
    for attr, key in (
        ("proposed_by", "proposed_by"),
        ("change_kind", "change_kind"),
        ("title", "title"),
        ("expected_behavior_change", "expected_behavior_change"),
        ("risk_summary", "risk_summary"),
        ("rollback_plan", "rollback_plan"),
        ("owner_role", "owner_role"),
        ("tenant_id", "tenant_id"),
        ("project_id", "project_id"),
    ):
        value = getattr(args, attr)
        if value:
            body[key] = value
    if args.actor:
        body["actor_context"] = {"actor_id": args.actor}
    if args.invariant_checks_json:
        try:
            body["invariant_checks"] = _load_invariant_checks_json(
                Path(args.invariant_checks_json)
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"ERROR: cannot read invariant checks JSON: {exc}", file=sys.stderr)
            return 2
    _attach_lease_args(body, args)

    response = dispatch_kernel_request(
        "POST",
        f"/kernel/learning-transition-candidates/{args.candidate_id}/governance-change",
        body,
    )
    if response.status not in {200, 201}:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    proposal = response.payload.get("proposal") or {}
    evidence = proposal.get("evidence_sufficiency") or {}
    print(f"governance proposal {proposal.get('proposal_id')} from candidate")
    print(f"  candidate:   {args.candidate_id}")
    print(f"  status:      {proposal.get('status')}")
    print(f"  change_kind: {proposal.get('change_kind')}")
    print(f"  target:      {proposal.get('target_ref')}")
    if evidence:
        print(f"  evidence:    {evidence.get('status')}")
        missing = evidence.get("missing") or []
        if missing:
            print(f"  missing:     {', '.join(str(item) for item in missing[:6])}")
    checks = proposal.get("invariant_checks") or []
    if not checks:
        print("  invariants:  missing checks")
    source_refs = proposal.get("source_refs") or []
    if source_refs:
        print(f"  source_refs: {', '.join(str(ref) for ref in source_refs[:6])}")
    return 0


def _load_invariant_checks_json(path: Path) -> list[Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict):
        payload = payload.get("invariant_checks")
    if not isinstance(payload, list):
        raise ValueError("expected a list or an object with invariant_checks")
    return payload


def _cmd_decide(args: argparse.Namespace, decision: str) -> int:
    """Record an attested approve/decline decision on a governance change."""
    body: dict[str, Any] = {"decision": decision}
    if args.reason:
        body["reason"] = args.reason
    if getattr(args, "actor", None):
        # --actor sets the request's actor context, not a free-text decider:
        # when the kernel runs with authentication, the authenticated subject
        # overrides this, so attribution on a governance decision cannot be
        # forged from the command line.
        body["actor_context"] = {"actor_id": args.actor}
    _attach_lease_args(body, args)
    try:
        response = dispatch_kernel_request(
            "POST",
            f"/kernel/governance-changes/{args.proposal_id}/decision",
            body,
        )
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    result = response.payload.get("result", {})
    print(
        f"governance change {result.get('proposal_id')} {decision}d "
        f"by {result.get('decided_by')}."
    )
    event_id = result.get("event_id")
    if event_id:
        print(f"  attested event: {event_id}")
    return 0


def _cmd_approve(args: argparse.Namespace) -> int:
    return _cmd_decide(args, "approve")


def _cmd_decline(args: argparse.Namespace) -> int:
    return _cmd_decide(args, "decline")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cognitive-firm-userland",
        description="The terminal carrier of the cognitive-firm userland.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_needs_me = sub.add_parser(
        "needs-me", help="Show the operator's escalation queue."
    )
    p_needs_me.add_argument("actor_id", help="The participant to route to.")
    p_needs_me.set_defaults(func=_cmd_needs_me)

    p_inbox = sub.add_parser(
        "inbox", help="Show a member-human's bounded work inbox."
    )
    p_inbox.add_argument("actor_id", help="The member-human to list work for.")
    p_inbox.add_argument(
        "--human-work-log",
        type=Path,
        default=None,
        help="Path to the human-work log (default: the kernel default).",
    )
    p_inbox.set_defaults(func=_cmd_inbox)

    p_vocabulary = sub.add_parser(
        "vocabulary", help="Show the shared userland glossary."
    )
    p_vocabulary.set_defaults(func=_cmd_vocabulary)

    p_commands = sub.add_parser(
        "commands",
        help="Suggest canonical repo commands for a task description.",
    )
    p_commands.add_argument(
        "query",
        help="Task text, proof path, or script/target name to match.",
    )
    p_commands.add_argument(
        "--role-id",
        default=None,
        help=(
            "Optional source role to trace against command authority effects. "
            "This is read-only and does not grant command authority."
        ),
    )
    p_commands.set_defaults(func=_cmd_commands)

    p_operator_path = sub.add_parser(
        "operator-path",
        help="Show a named read-only operator path over existing commands.",
    )
    p_operator_path.add_argument(
        "path_id",
        help="Named path to inspect, for example first_review.",
    )
    p_operator_path.set_defaults(func=_cmd_operator_path)

    p_status = sub.add_parser(
        "status", help="Show a plain-language read of overall org health."
    )
    p_status.set_defaults(func=_cmd_status)

    p_resolve = sub.add_parser(
        "resolve", help="Resolve a pending gate seen in needs-me."
    )
    p_resolve.add_argument("gate_id", help="The pending gate to resolve.")
    p_resolve.add_argument(
        "--option",
        required=True,
        help="The option to choose for this gate.",
    )
    p_resolve.add_argument(
        "--reason",
        default=None,
        help="Why this option was chosen (optional).",
    )
    p_resolve.set_defaults(func=_cmd_resolve)

    p_proposals = sub.add_parser(
        "proposals",
        help="List governance changes awaiting an accountable actor decision.",
    )
    p_proposals.set_defaults(func=_cmd_proposals)

    p_proposal = sub.add_parser(
        "proposal",
        help="Inspect one governance proposal's evidence and invariants.",
    )
    p_proposal.add_argument(
        "proposal_id",
        help="The governance change proposal to inspect.",
    )
    p_proposal.set_defaults(func=_cmd_proposal)

    p_proposal_packet = sub.add_parser(
        "proposal-packet",
        help="Show a portable review handoff for one governance proposal.",
    )
    p_proposal_packet.add_argument(
        "proposal_id",
        help="The governance change proposal to package for review.",
    )
    p_proposal_packet.add_argument(
        "--event-limit",
        type=int,
        default=8,
        help="Maximum provenance events to include in the packet excerpt.",
    )
    p_proposal_packet.add_argument(
        "--ref-limit",
        type=int,
        default=12,
        help="Maximum evidence refs to print in terminal mode.",
    )
    p_proposal_packet.add_argument(
        "--markdown",
        action="store_true",
        help="Print the portable Markdown packet instead of the terminal view.",
    )
    p_proposal_packet.set_defaults(func=_cmd_proposal_packet)

    p_template = sub.add_parser(
        "proposal-template",
        help="Print a governance-change POST body skeleton.",
    )
    p_template.add_argument(
        "--change-kind",
        default="route_policy_change",
        help="Governance change kind for the template.",
    )
    p_template.add_argument(
        "--title",
        default=None,
        help="Optional title to place in the template.",
    )
    p_template.add_argument(
        "--proposed-by",
        default=None,
        help="Optional proposer to place in the template.",
    )
    p_template.add_argument(
        "--target-ref",
        default=None,
        help="Optional target ref to place in the template.",
    )
    p_template.add_argument(
        "--tenant-id",
        default=None,
        help="Optional tenant scope to place in the template.",
    )
    p_template.add_argument(
        "--project-id",
        default=None,
        help="Optional project scope to place in the template.",
    )
    p_template.set_defaults(func=_cmd_proposal_template)

    p_from_candidate = sub.add_parser(
        "proposal-from-candidate",
        help="Promote a learning-transition candidate into a proposal.",
    )
    p_from_candidate.add_argument(
        "candidate_id",
        help="Learning-transition candidate id to promote.",
    )
    p_from_candidate.add_argument(
        "--source",
        default="all",
        choices=[
            "all",
            "org_surface",
            "human_work",
            "attention",
            "execution",
            "attribution",
            "capability",
            "phase_execution",
            "protocol_experiment",
        ],
        help="Candidate source projection to search.",
    )
    p_from_candidate.add_argument(
        "--include-closed",
        action="store_true",
        help="Include closed capability-signal candidates where applicable.",
    )
    p_from_candidate.add_argument(
        "--target-ref",
        required=True,
        help="Concrete governance target the proposal would change.",
    )
    p_from_candidate.add_argument(
        "--proposed-by",
        default=None,
        help="Proposer id to record when no authenticated actor is configured.",
    )
    p_from_candidate.add_argument(
        "--actor",
        default=None,
        help="Actor context for the request.",
    )
    p_from_candidate.add_argument(
        "--change-kind",
        default=None,
        help="Optional governance change kind override.",
    )
    p_from_candidate.add_argument("--title", default=None)
    p_from_candidate.add_argument("--expected-behavior-change", default=None)
    p_from_candidate.add_argument("--risk-summary", default=None)
    p_from_candidate.add_argument("--rollback-plan", default=None)
    p_from_candidate.add_argument("--owner-role", default=None)
    p_from_candidate.add_argument("--tenant-id", default=None)
    p_from_candidate.add_argument("--project-id", default=None)
    p_from_candidate.add_argument(
        "--invariant-checks-json",
        default=None,
        help=(
            "Path to a list of invariant checks, or an object containing "
            "invariant_checks. Omit to let the proposal gate report gaps."
        ),
    )
    _add_lease_args(p_from_candidate)
    p_from_candidate.set_defaults(func=_cmd_proposal_from_candidate)

    p_timeline = sub.add_parser(
        "timeline",
        help="Show a read-only provenance timeline for a run, ref, or scope.",
    )
    p_timeline.add_argument(
        "--run-id",
        default=None,
        help="Governed run id to inspect.",
    )
    p_timeline.add_argument(
        "--ref",
        default=None,
        help="Explicit object/ref to inspect.",
    )
    p_timeline.add_argument(
        "--tenant-id",
        default=None,
        help="Tenant scope for the timeline.",
    )
    p_timeline.add_argument(
        "--project-id",
        default=None,
        help="Project scope; requires --tenant-id unless --run-id anchors scope.",
    )
    p_timeline.set_defaults(func=_cmd_timeline)

    p_human_pressure = sub.add_parser(
        "human-pressure",
        help="Show observer-only repeated A2H human-work pressure.",
    )
    p_human_pressure.add_argument(
        "--agent-counterparty-role",
        default=None,
        help="Optional role whose A2H pressure should be inspected.",
    )
    p_human_pressure.add_argument(
        "--tenant-id",
        default=None,
        help="Optional tenant scope for the pressure projection.",
    )
    p_human_pressure.add_argument(
        "--project-id",
        default=None,
        help="Optional project scope for the pressure projection.",
    )
    p_human_pressure.add_argument(
        "--stale-after-hours",
        type=int,
        default=24,
        help="Hours after which open human work counts as stale.",
    )
    p_human_pressure.add_argument(
        "--concentration-threshold",
        type=int,
        default=3,
        help="Active sessions needed before repeated pressure is surfaced.",
    )
    p_human_pressure.set_defaults(func=_cmd_human_pressure)

    p_speed = sub.add_parser(
        "speed-envelope",
        help="Classify accountable human/agent work speed.",
    )
    p_speed.add_argument(
        "--risk-tier",
        choices=["low", "medium", "high", "irreversible"],
        default="medium",
    )
    p_speed.add_argument(
        "--bottleneck-class",
        choices=[
            "authority",
            "access",
            "taste",
            "relationship",
            "cognition",
            "labor",
            "safety",
            "other",
        ],
        default="other",
    )
    p_speed.add_argument(
        "--deployment-class",
        choices=[
            "local",
            "internal",
            "customer_facing",
            "regulated",
            "physical_world",
            "external_write",
        ],
        default="internal",
    )
    p_speed.add_argument(
        "--reversible",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Whether the proposed action can be reversed within its scope.",
    )
    p_speed.add_argument("--external-side-effect", action="store_true")
    p_speed.add_argument("--repeated-similar", action="store_true")
    p_speed.add_argument("--private-context", action="store_true")
    p_speed.add_argument("--harm-occurred", action="store_true")
    p_speed.add_argument("--residual-risk-accepted", action="store_true")
    p_speed.set_defaults(func=_cmd_speed_envelope)

    p_learning_candidates = sub.add_parser(
        "learning-candidates",
        help="Show observer-only learning-transition candidates.",
    )
    p_learning_candidates.add_argument(
        "--source",
        default="all",
        choices=[
            "all",
            "org_surface",
            "human_work",
            "attention",
            "execution",
            "attribution",
            "capability",
            "phase_execution",
            "protocol_experiment",
        ],
        help="Candidate source projection to inspect.",
    )
    p_learning_candidates.add_argument(
        "--include-closed",
        action="store_true",
        help="Include closed capability-signal candidates where applicable.",
    )
    p_learning_candidates.add_argument(
        "--limit",
        type=int,
        default=12,
        help="Maximum candidates to print.",
    )
    p_learning_candidates.set_defaults(func=_cmd_learning_candidates)

    p_lease_acquire = sub.add_parser(
        "lease-acquire",
        help="Acquire a mutation lease for a guarded kernel write.",
    )
    p_lease_acquire.add_argument(
        "resource_ref",
        help="Mutable resource ref to lease, e.g. governance_change:gcp_1:decision.",
    )
    p_lease_acquire.add_argument(
        "--actor",
        default=None,
        help="Actor acquiring the lease. Defaults to the kernel actor.",
    )
    p_lease_acquire.add_argument(
        "--role",
        default=None,
        help="Optional role id recorded with the lease holder.",
    )
    p_lease_acquire.add_argument(
        "--ttl-seconds",
        type=int,
        default=300,
        help="Lease time to live in seconds.",
    )
    p_lease_acquire.add_argument(
        "--purpose",
        default=None,
        help="Optional purpose string for the lease row.",
    )
    p_lease_acquire.set_defaults(func=_cmd_lease_acquire)

    p_leases = sub.add_parser(
        "leases",
        help="List mutation leases visible to the service.",
    )
    p_leases.add_argument(
        "--resource-ref",
        default=None,
        help="Optional exact leased resource ref filter.",
    )
    p_leases.add_argument(
        "--state",
        default=None,
        choices=["active", "released", "expired"],
        help="Optional effective lease state filter.",
    )
    p_leases.add_argument(
        "--limit",
        type=int,
        default=12,
        help="Maximum leases to print.",
    )
    p_leases.set_defaults(func=_cmd_leases)

    p_lease_release = sub.add_parser(
        "lease-release",
        help="Release a mutation lease held by the actor.",
    )
    p_lease_release.add_argument("lease_id")
    p_lease_release.add_argument(
        "--actor",
        default=None,
        help="Actor releasing the lease. Defaults to the kernel actor.",
    )
    p_lease_release.add_argument(
        "--role",
        default=None,
        help="Optional role id for request actor context.",
    )
    p_lease_release.set_defaults(func=_cmd_lease_release)

    p_decision_profiles = sub.add_parser(
        "decision-profiles",
        help="List reusable evidence-only decision procedure profiles.",
    )
    p_decision_profiles.set_defaults(func=_cmd_decision_profiles)

    p_decision_cases = sub.add_parser(
        "decision-cases",
        help="Show decision aggregation evidence cases.",
    )
    p_decision_cases.add_argument(
        "--status",
        default=None,
        choices=["collecting", "computed", "escalated", "expired"],
        help="Optional case status filter.",
    )
    p_decision_cases.add_argument(
        "--procedure-kind",
        default=None,
        choices=["single_authority", "quorum_majority", "veto", "unanimity"],
        help="Optional procedure kind filter.",
    )
    p_decision_cases.add_argument(
        "--subject-ref",
        default=None,
        help="Optional exact subject ref filter.",
    )
    p_decision_cases.add_argument(
        "--limit",
        type=int,
        default=12,
        help="Maximum cases to print.",
    )
    p_decision_cases.set_defaults(func=_cmd_decision_cases)

    p_decision_open = sub.add_parser(
        "decision-open",
        help="Open a decision aggregation evidence case.",
    )
    p_decision_open.add_argument("--subject-ref", required=True)
    p_decision_open.add_argument("--decision-class", required=True)
    p_decision_open.add_argument("--scope-kind", required=True)
    p_decision_open.add_argument("--scope-ref", required=True)
    profile_group = p_decision_open.add_mutually_exclusive_group(required=True)
    profile_group.add_argument(
        "--procedure-profile",
        choices=["single_authority", "majority", "quorum_majority", "unanimity", "veto_review"],
        help="Built-in evidence-only profile to resolve.",
    )
    profile_group.add_argument(
        "--procedure-kind",
        choices=["single_authority", "quorum_majority", "veto", "unanimity"],
        help="Explicit procedure kind when no profile is used.",
    )
    p_decision_open.add_argument(
        "--opened-by",
        default=None,
        help="Actor or role opening the case; defaults to kernel actor.",
    )
    p_decision_open.add_argument("--actor", default=None)
    p_decision_open.add_argument("--eligibility-basis", required=True)
    p_decision_open.add_argument(
        "--eligible-role",
        action="append",
        default=[],
        help="Eligible role id. Repeatable.",
    )
    p_decision_open.add_argument(
        "--eligible-actor",
        action="append",
        default=[],
        help="Eligible actor id. Repeatable.",
    )
    p_decision_open.add_argument("--quorum", type=int, default=None)
    p_decision_open.add_argument("--tie-breaker-role", default=None)
    p_decision_open.add_argument("--downstream-ref", default=None)
    p_decision_open.add_argument("--tenant-id", default=None)
    p_decision_open.add_argument("--project-id", default=None)
    p_decision_open.add_argument("--case-id", default=None)
    p_decision_open.add_argument(
        "--evidence-ref",
        action="append",
        default=[],
        help="Evidence ref supporting the case. Repeatable.",
    )
    _add_lease_args(p_decision_open)
    p_decision_open.set_defaults(func=_cmd_decision_open)

    p_decision_position = sub.add_parser(
        "decision-position",
        help="Record one eligible position on a decision aggregation case.",
    )
    p_decision_position.add_argument("case_id")
    p_decision_position.add_argument("--actor-id", required=True)
    p_decision_position.add_argument("--role-id", required=True)
    p_decision_position.add_argument(
        "--position",
        required=True,
        choices=["approve", "reject", "abstain", "recuse", "veto"],
    )
    p_decision_position.add_argument("--rationale", required=True)
    p_decision_position.add_argument("--position-id", default=None)
    p_decision_position.add_argument(
        "--evidence-ref",
        action="append",
        default=[],
        help="Evidence ref supporting the position. Repeatable.",
    )
    _add_lease_args(p_decision_position)
    p_decision_position.set_defaults(func=_cmd_decision_position)

    p_decision_compute = sub.add_parser(
        "decision-compute",
        help="Compute a decision aggregation recommendation.",
    )
    p_decision_compute.add_argument("case_id")
    p_decision_compute.add_argument("--actor", default=None)
    _add_lease_args(p_decision_compute)
    p_decision_compute.set_defaults(func=_cmd_decision_compute)

    p_decision_escalate = sub.add_parser(
        "decision-route-escalation",
        help="Route an escalated decision aggregation case into learning review.",
    )
    p_decision_escalate.add_argument("case_id")
    p_decision_escalate.add_argument("--summary", required=True)
    p_decision_escalate.add_argument("--owner-role", required=True)
    p_decision_escalate.add_argument(
        "--severity",
        default="blocking",
        choices=["info", "warning", "blocking"],
    )
    p_decision_escalate.add_argument("--actor", default=None)
    p_decision_escalate.add_argument("--signal-id", default=None)
    p_decision_escalate.add_argument("--signal-kind", default="evidence_gap")
    p_decision_escalate.add_argument("--tenant-id", default=None)
    p_decision_escalate.add_argument("--project-id", default=None)
    p_decision_escalate.add_argument("--worker-ref", default=None)
    p_decision_escalate.add_argument("--run-id", default=None)
    p_decision_escalate.add_argument("--work-id", default=None)
    p_decision_escalate.add_argument("--recommended-route", default=None)
    p_decision_escalate.add_argument("--route-kind", default=None)
    p_decision_escalate.add_argument("--route-target-ref", default=None)
    p_decision_escalate.add_argument("--route-rationale", default=None)
    p_decision_escalate.add_argument("--proposed-by", default=None)
    p_decision_escalate.add_argument(
        "--evidence-ref",
        action="append",
        default=[],
        help="Additional evidence refs for the routed signal. Repeatable.",
    )
    _add_lease_args(p_decision_escalate)
    p_decision_escalate.set_defaults(func=_cmd_decision_route_escalation)

    p_graph = sub.add_parser(
        "graph",
        help="Show a projection-only provenance graph for a run, ref, or scope.",
    )
    p_graph.add_argument(
        "--run-id",
        default=None,
        help="Governed run id to inspect.",
    )
    p_graph.add_argument(
        "--ref",
        default=None,
        help="Explicit object/ref to inspect.",
    )
    p_graph.add_argument(
        "--tenant-id",
        default=None,
        help="Tenant scope for the graph.",
    )
    p_graph.add_argument(
        "--project-id",
        default=None,
        help="Project scope; requires --tenant-id unless --run-id anchors scope.",
    )
    p_graph.add_argument(
        "--limit",
        type=int,
        default=12,
        help="Maximum edges to print.",
    )
    p_graph.set_defaults(func=_cmd_graph)

    p_provenance_report = sub.add_parser(
        "provenance-report",
        help="Show a portable provenance report for reviewer handoff.",
    )
    p_provenance_report.add_argument(
        "--run-id",
        default=None,
        help="Governed run id to inspect.",
    )
    p_provenance_report.add_argument(
        "--ref",
        default=None,
        help="Explicit object/ref to inspect.",
    )
    p_provenance_report.add_argument(
        "--tenant-id",
        default=None,
        help="Tenant scope for the report.",
    )
    p_provenance_report.add_argument(
        "--project-id",
        default=None,
        help="Project scope; requires --tenant-id unless --run-id anchors scope.",
    )
    p_provenance_report.add_argument(
        "--event-limit",
        type=int,
        default=12,
        help="Maximum timeline events to include in the report excerpt.",
    )
    p_provenance_report.add_argument(
        "--ref-limit",
        type=int,
        default=12,
        help="Maximum high-signal refs to print in terminal mode.",
    )
    p_provenance_report.add_argument(
        "--markdown",
        action="store_true",
        help="Print the portable Markdown report instead of the terminal view.",
    )
    p_provenance_report.set_defaults(func=_cmd_provenance_report)

    p_work_context = sub.add_parser(
        "work-context",
        help="Show read-only learning context before a role starts work.",
    )
    p_work_context.add_argument(
        "--assigned-to",
        default=None,
        help=(
            "Role or actor that is about to work, for example role.manager. "
            "May be omitted when exact structured filters are provided."
        ),
    )
    p_work_context.add_argument(
        "--tenant-id",
        default=None,
        help="Tenant scope for the context projection.",
    )
    p_work_context.add_argument(
        "--project-id",
        default=None,
        help="Project scope for the context projection.",
    )
    p_work_context.add_argument(
        "--cue",
        default=None,
        help="Natural-language cue for matching approved learning events.",
    )
    p_work_context.add_argument(
        "--cue-signature",
        default=None,
        help="Exact cue signature to match from learning-event metadata.",
    )
    p_work_context.add_argument(
        "--resource-ref",
        action="append",
        default=[],
        help="Exact resource ref to match from learning-event metadata. Repeatable.",
    )
    p_work_context.add_argument(
        "--topology-ref",
        action="append",
        default=[],
        help="Exact topology ref to match from learning-event metadata. Repeatable.",
    )
    p_work_context.add_argument(
        "--max-per-source",
        type=int,
        default=5,
        help="Maximum rows per source to display.",
    )
    p_work_context.add_argument(
        "--learning-only",
        action="store_true",
        help=(
            "Suppress generic work candidates in role-scoped context; no-role "
            "structured queries are learning-only by default."
        ),
    )
    p_work_context.set_defaults(func=_cmd_work_context)

    p_context_packet_verify = sub.add_parser(
        "context-packet-verify",
        help="Verify a captured work-context packet digest without writing state.",
    )
    p_context_packet_verify.add_argument(
        "packet_json",
        help=(
            "Path to a JSON object containing context_packet, or the "
            "context_packet object itself."
        ),
    )
    p_context_packet_verify.set_defaults(func=_cmd_context_packet_verify)

    p_composition = sub.add_parser(
        "composition-packet",
        help="Check a read-only governed action proof-chain matrix.",
    )
    p_composition.add_argument(
        "--observed-json",
        required=True,
        help="Path to observed command/demo JSON, or a wrapper with observed_result.",
    )
    p_composition.add_argument(
        "--action-label",
        required=True,
        help="Human label for the action being checked.",
    )
    p_composition.add_argument(
        "--profile",
        default="first_gated_action",
        choices=["first_gated_action", "learning_loop"],
        help="Composition profile to apply to the observed output.",
    )
    p_composition.add_argument(
        "--evidence-ref",
        action="append",
        default=[],
        help="Additional evidence ref to include in the matrix. Repeatable.",
    )
    p_composition.set_defaults(func=_cmd_composition_packet)

    p_learning_use = sub.add_parser(
        "learning-use",
        help="Record an auditable learning-use receipt.",
    )
    p_learning_use.add_argument(
        "learning_event_id",
        help="Approved learning event that was encountered or used.",
    )
    p_learning_use.add_argument(
        "--role",
        required=True,
        help="Role or actor whose work encountered the learning.",
    )
    p_learning_use.add_argument(
        "--cue",
        required=True,
        help="Work cue or situation that caused the learning to be considered.",
    )
    p_learning_use.add_argument(
        "--outcome",
        choices=("encountered", "applied", "ignored", "deferred"),
        default="encountered",
        help="How the learning affected the work surface.",
    )
    p_learning_use.add_argument(
        "--work-ref",
        default=None,
        help="Optional concrete work/run/ref affected by the learning.",
    )
    p_learning_use.add_argument(
        "--evidence-ref",
        action="append",
        default=[],
        help="Evidence ref supporting the receipt; may be repeated.",
    )
    p_learning_use.add_argument(
        "--context-packet-ref",
        default=None,
        help="Context packet id from work-context, if applicable.",
    )
    p_learning_use.add_argument(
        "--context-packet-json",
        default=None,
        help=(
            "Path to captured work-context JSON or context_packet JSON. When "
            "provided, the service verifies the packet and learning-event basis."
        ),
    )
    p_learning_use.add_argument(
        "--reason",
        default=None,
        help="Required by the kernel for ignored or deferred outcomes.",
    )
    p_learning_use.add_argument(
        "--tenant-id",
        default=None,
        help="Tenant scope for the receipt.",
    )
    p_learning_use.add_argument(
        "--project-id",
        default=None,
        help="Project scope for the receipt.",
    )
    p_learning_use.add_argument(
        "--idempotency-key",
        default=None,
        help="Optional stable receipt key for replaying the same command.",
    )
    _add_lease_args(p_learning_use)
    p_learning_use.set_defaults(func=_cmd_learning_use)

    p_learning_loop = sub.add_parser(
        "learning-loop",
        help="Inspect one learning event's read-only compounding loop.",
    )
    p_learning_loop.add_argument(
        "learning_event_id",
        help="Approved learning event to inspect.",
    )
    p_learning_loop.set_defaults(func=_cmd_learning_loop)

    p_receipt = sub.add_parser(
        "receipt",
        help="Record a structured receipt for bounded human work.",
    )
    p_receipt.add_argument("session_id", help="Human-work session id.")
    p_receipt.add_argument(
        "--actor",
        required=True,
        help="Human actor recording the receipt.",
    )
    p_receipt.add_argument(
        "--summary",
        required=True,
        help="Bounded claim or review summary.",
    )
    p_receipt.add_argument(
        "--receipt-type",
        default="note",
        choices=["note", "artifact_ref", "external_ref", "witness", "none"],
        help="Receipt evidence type.",
    )
    p_receipt.add_argument(
        "--receipt-ref",
        default=None,
        help="External, artifact, or witness receipt ref.",
    )
    p_receipt.add_argument(
        "--subject-ref",
        action="append",
        default=[],
        help="Subject ref covered by this receipt. Repeatable.",
    )
    p_receipt.add_argument(
        "--artifact-ref",
        action="append",
        default=[],
        help="Artifact ref produced or reviewed by this receipt. Repeatable.",
    )
    p_receipt.add_argument(
        "--agent-output-ref",
        default=None,
        help="Agent output ref reviewed by the human; added as a subject ref.",
    )
    p_receipt.add_argument(
        "--action-attestation-ref",
        default=None,
        help="Action-attestation ref for the agent output; added as a subject ref.",
    )
    p_receipt.add_argument(
        "--review-decision",
        default=None,
        choices=["accepted", "accepted_with_changes", "needs_changes", "rejected"],
        help="Optional human review decision recorded in receipt metadata.",
    )
    p_receipt.add_argument(
        "--confidence",
        default="medium",
        choices=["low", "medium", "high"],
        help="Human confidence in the receipt claim.",
    )
    p_receipt.add_argument(
        "--observability",
        default="human_attested",
        choices=["digital_artifact", "external_system", "human_attested", "unobservable"],
        help="How directly the work can be observed.",
    )
    p_receipt.add_argument(
        "--review-required",
        action="store_true",
        help="Mark this receipt for later sampling/review.",
    )
    _add_lease_args(p_receipt)
    p_receipt.set_defaults(func=_cmd_receipt)

    for verb, func, helptext in (
        ("approve", _cmd_approve, "Approve a governance change."),
        ("decline", _cmd_decline, "Decline a governance change."),
    ):
        p_decide = sub.add_parser(verb, help=helptext)
        p_decide.add_argument(
            "proposal_id", help="The governance change to decide."
        )
        p_decide.add_argument(
            "--reason",
            default=None,
            help="Why this decision was made (optional).",
        )
        p_decide.add_argument(
            "--actor",
            default=None,
            help="The deciding participant (default: the kernel actor).",
        )
        _add_lease_args(p_decide)
        p_decide.set_defaults(func=func)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
