"""``cognitive-firm-userland`` — the terminal carrier of the userland.

A parallel lane to the graphical surfaces: the same L1/L2/L4 userland models,
served to a participant through a console. Every verb is a thin projection —
it calls a kernel route or a userland read model, then prints the governance
interpretation. It holds no state and reaches into no kernel internals.

Verbs:

- ``needs-me <actor_id>``  — the operator's escalation queue (L1 + L2).
- ``inbox <actor_id>``     — a member-human's bounded work queue (L2).
- ``vocabulary``           — the shared L4 glossary every surface speaks.
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

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
