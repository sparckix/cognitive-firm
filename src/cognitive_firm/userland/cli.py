"""``cognitive-firm-userland`` — the terminal carrier of the userland.

A parallel lane to the graphical surfaces: the same L1/L2/L4 userland models,
served to a participant through a console. Every verb is a thin projection —
it calls a kernel route or a userland read model, then prints the governance
interpretation. It holds no state and reaches into no kernel internals.

Verbs:

- ``needs-me <actor_id>``  — the operator's escalation queue (L1 + L2).
- ``inbox <actor_id>``     — a member-human's bounded work queue (L2).
- ``vocabulary``           — the shared L4 glossary every surface speaks.
- ``status``               — a plain-language read of overall org health.
- ``resolve <gate_id>``    — act on a pending gate the operator saw in ``needs-me``.
- ``proposals``            — governance changes awaiting a human decision.
- ``approve <id>``         — approve a governance change (an attested event).
- ``decline <id>``         — decline a governance change (an attested event).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cognitive_firm.kernel_service import dispatch_kernel_request
from cognitive_firm.userland import work_inbox
from cognitive_firm.userland.attention_router import RoutedSignal
from cognitive_firm.userland.needs_me import build_needs_me


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
    """List governance changes awaiting a human decision."""
    response = dispatch_kernel_request(
        "GET", "/kernel/governance-changes?status=review_ready"
    )
    if response.status != 200:
        error = response.payload.get("error", "unknown error")
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    proposals = response.payload.get("proposals", [])
    if not proposals:
        print("No governance changes are awaiting review.")
        return 0
    print(f"{len(proposals)} governance change(s) awaiting review:")
    for proposal in proposals:
        print()
        print(f"  [{proposal['change_kind']}] {proposal['title']}")
        print(f"    id:       {proposal['proposal_id']}")
        print(f"    proposed: {proposal['proposed_by']}")
        if proposal.get("expected_behavior_change"):
            print(f"    effect:   {proposal['expected_behavior_change']}")
        if proposal.get("risk_summary"):
            print(f"    risk:     {proposal['risk_summary']}")
        if proposal.get("rollback_plan"):
            print(f"    rollback: {proposal['rollback_plan']}")
        print(f"    decide:   cognitive-firm-userland approve {proposal['proposal_id']}")
    return 0


def _cmd_decide(args: argparse.Namespace, decision: str) -> int:
    """Record an attested approve/decline decision on a governance change."""
    body: dict[str, str] = {"decision": decision}
    if args.reason:
        body["reason"] = args.reason
    if getattr(args, "actor", None):
        body["decided_by"] = args.actor
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
        help="List governance changes awaiting a human decision.",
    )
    p_proposals.set_defaults(func=_cmd_proposals)

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
        p_decide.set_defaults(func=func)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
