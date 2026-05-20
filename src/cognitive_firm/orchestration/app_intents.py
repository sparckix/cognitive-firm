"""Kernel-owned app intents for local app surfaces.

Orbit and similar local surfaces should ask the kernel to perform governance
mutations instead of reimplementing lifecycle writes in frontend-adjacent code.
This module keeps the local filesystem projection small and explicit while the
same intent boundary can later move behind ``kernel_service`` HTTP routes.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from cognitive_firm.orchestration import chat_handler
from cognitive_firm.orchestration.transition_log import append_transition


_GATE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
_ROLE_ID_RE = re.compile(r"^[A-Za-z0-9_]+$")
_CONTROL_ACTIONS = {"STOP", "PAUSE", "RESUME"}
_AGENT_UTILIZATION_FIELDS = (
    "daily_cap_seconds",
    "daily_cap_output_tokens",
    "daily_cap_turn_count",
    "session_cap_seconds",
    "absolute_ceiling_seconds",
    "warn_threshold_frac",
)


@dataclass(frozen=True)
class AppIntentResult:
    ok: bool
    kind: str
    path: str | None = None
    already_resolved: bool = False
    message: dict[str, Any] | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    transition_event_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "ok": self.ok,
            "kind": self.kind,
            "already_resolved": self.already_resolved,
            "payload": self.payload,
        }
        if self.path is not None:
            out["path"] = self.path
        if self.message is not None:
            out["message"] = self.message
        if self.transition_event_id is not None:
            out["transition_event_id"] = self.transition_event_id
        return out


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_gate_id(gate_id: str) -> None:
    if not _GATE_ID_RE.fullmatch(gate_id):
        raise ValueError("invalid gate_id")


def _validate_role_id(role_id: str, *, field_name: str = "role_id") -> None:
    if not _ROLE_ID_RE.fullmatch(role_id):
        raise ValueError(f"invalid {field_name}")


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


def resolve_gate(
    *,
    gate_id: str,
    chosen_option: str,
    reason: str,
    gates_dir: Path,
    resolved_dir: Path,
    transition_log: Path,
    actor: str = "orbit",
) -> AppIntentResult:
    """Resolve one pending gate and append the canonical transition record."""

    _validate_gate_id(gate_id)
    if not chosen_option:
        raise ValueError("chosen_option is required")

    src_path = gates_dir / f"{gate_id}.json"
    out_path = resolved_dir / f"{gate_id}.json"
    if out_path.exists():
        return AppIntentResult(
            ok=True,
            kind="gate_resolve",
            path=str(out_path),
            already_resolved=True,
            payload={"gate_id": gate_id, "chosen_option": chosen_option},
        )
    if not src_path.exists():
        raise FileNotFoundError("pending gate not found")

    gate = _read_json(src_path)
    resolved_payload = {
        **gate,
        "status": "resolved",
        "resolution": {
            "chosen_option": chosen_option,
            "reason": reason,
            "resolved_by": actor,
            "resolved_utc": _utc_now(),
        },
    }
    _atomic_write_json(out_path, resolved_payload)
    try:
        os.replace(src_path, Path(f"{src_path}.handled"))
    except FileNotFoundError:
        pass

    transition = append_transition(
        event="gate.resolved",
        actor=actor,
        role_id=None,
        surface="orbit",
        subject=f"gate/{gate_id}",
        causality_id=gate_id,
        payload={"gate_id": gate_id, "chosen_option": chosen_option, "reason": reason},
        log_path=transition_log,
    )
    return AppIntentResult(
        ok=True,
        kind="gate_resolve",
        path=str(out_path),
        payload={"gate_id": gate_id, "chosen_option": chosen_option},
        transition_event_id=str(transition["event_id"]),
    )


def issue_directive(
    *,
    target_role: str,
    message: str,
    org_dir: Path,
    transition_log: Path,
    actor: str = "principal",
) -> AppIntentResult:
    """Write a role directive and append the canonical transition record."""

    _validate_role_id(target_role, field_name="target_role")
    message = message.strip()
    if not message or len(message) > 4000:
        raise ValueError("message required (<=4000 chars)")
    created_utc = _utc_now()
    stamp = created_utc.replace(":", "-").replace(".", "-")
    out_path = org_dir / "directives" / f"{stamp}_{target_role}.json"
    payload = {
        "target_role": target_role,
        "message": message,
        "from": actor,
        "created_utc": created_utc,
        "consumed": False,
    }
    _atomic_write_json(out_path, payload)
    transition = append_transition(
        event="directive.issued",
        actor=actor,
        role_id=target_role,
        surface="orbit",
        subject=f"role/{target_role}",
        payload={"target_role": target_role, "path": str(out_path)},
        log_path=transition_log,
    )
    return AppIntentResult(
        ok=True,
        kind="directive",
        path=str(out_path),
        payload={"target_role": target_role},
        transition_event_id=str(transition["event_id"]),
    )


def issue_control(
    *,
    target_role: str,
    action: str,
    org_dir: Path,
    transition_log: Path,
    actor: str = "principal",
) -> AppIntentResult:
    """Write a role control command and append the canonical transition record."""

    _validate_role_id(target_role, field_name="target_role")
    if action not in _CONTROL_ACTIONS:
        raise ValueError("action must be STOP, PAUSE, or RESUME")
    issued_utc = _utc_now()
    out_path = org_dir / "controls" / f"{target_role}.json"
    payload = {
        "action": action,
        "target_role": target_role,
        "issued_by": actor,
        "issued_utc": issued_utc,
    }
    _atomic_write_json(out_path, payload)
    transition = append_transition(
        event="control.issued",
        actor=actor,
        role_id=target_role,
        surface="orbit",
        subject=f"role/{target_role}",
        payload={"target_role": target_role, "action": action, "path": str(out_path)},
        log_path=transition_log,
    )
    return AppIntentResult(
        ok=True,
        kind="control",
        path=str(out_path),
        payload={"target_role": target_role, "action": action},
        transition_event_id=str(transition["event_id"]),
    )


def send_chat_message(
    *,
    role_id: str,
    text: str,
    org_dir: Path,
    transition_log: Path,
    sender: str = "principal",
) -> AppIntentResult:
    """Append a principal chat message and append the canonical transition."""

    _validate_role_id(role_id)
    text = text.strip()
    if not text or len(text) > 4000:
        raise ValueError("text required (<=4000 chars)")

    original_root = chat_handler.SESSIONS_ROOT
    chat_handler.SESSIONS_ROOT = org_dir / "sessions"
    try:
        message = chat_handler.append_message(role_id, sender, text)
    finally:
        chat_handler.SESSIONS_ROOT = original_root

    transition = append_transition(
        event="chat.message.sent",
        actor=sender,
        role_id=role_id,
        surface="orbit",
        subject=f"role/{role_id}",
        payload={"role_id": role_id, "message_id": message["id"], "sender": sender},
        log_path=transition_log,
    )
    return AppIntentResult(
        ok=True,
        kind="chat_send",
        message=message,
        payload={"role_id": role_id},
        transition_event_id=str(transition["event_id"]),
    )


def update_role_agent_utilization(
    *,
    role_id: str,
    caps: dict[str, Any],
    org_dir: Path,
    transition_log: Path,
    actor: str = "principal",
) -> AppIntentResult:
    """Update role utilization caps through the kernel service boundary."""

    _validate_role_id(role_id)
    normalized: dict[str, float | int] = {}
    for field_name in _AGENT_UTILIZATION_FIELDS:
        value = caps.get(field_name)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"missing or non-numeric field: {field_name}")
        normalized[field_name] = value

    role_path = org_dir / "roles" / f"{role_id}.yaml"
    if not role_path.exists():
        raise FileNotFoundError(f"role {role_id} not found")
    data = yaml.safe_load(role_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("role yaml must contain a mapping")
    data["agent_utilization"] = normalized
    tmp_path = role_path.with_suffix(role_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        handle.write(yaml.safe_dump(data, sort_keys=False))
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, role_path)
    transition = append_transition(
        event="role.agent_utilization.updated",
        actor=actor,
        role_id=role_id,
        surface="orbit",
        subject=f"role/{role_id}",
        payload={"role_id": role_id, "agent_utilization": normalized, "path": str(role_path)},
        log_path=transition_log,
    )
    return AppIntentResult(
        ok=True,
        kind="role_agent_utilization",
        path=str(role_path),
        payload={"role_id": role_id, "agent_utilization": normalized},
        transition_event_id=str(transition["event_id"]),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a local app intent.")
    sub = parser.add_subparsers(dest="command", required=True)

    gate = sub.add_parser("gate-resolve")
    gate.add_argument("--gate-id", required=True)
    gate.add_argument("--chosen-option", required=True)
    gate.add_argument("--reason", default="")
    gate.add_argument("--gates-dir", type=Path, required=True)
    gate.add_argument("--resolved-dir", type=Path, required=True)
    gate.add_argument("--transition-log", type=Path, required=True)
    gate.add_argument("--actor", default="orbit")

    directive = sub.add_parser("directive")
    directive.add_argument("--target-role", required=True)
    directive.add_argument("--message", required=True)
    directive.add_argument("--org-dir", type=Path, required=True)
    directive.add_argument("--transition-log", type=Path, required=True)
    directive.add_argument("--actor", default="principal")

    control = sub.add_parser("control")
    control.add_argument("--target-role", required=True)
    control.add_argument("--action", required=True)
    control.add_argument("--org-dir", type=Path, required=True)
    control.add_argument("--transition-log", type=Path, required=True)
    control.add_argument("--actor", default="principal")

    chat = sub.add_parser("chat-send")
    chat.add_argument("--role-id", required=True)
    chat.add_argument("--text", required=True)
    chat.add_argument("--org-dir", type=Path, required=True)
    chat.add_argument("--transition-log", type=Path, required=True)
    chat.add_argument("--sender", default="principal")

    utilization = sub.add_parser("role-agent-utilization")
    utilization.add_argument("--role-id", required=True)
    utilization.add_argument("--caps-json", required=True)
    utilization.add_argument("--org-dir", type=Path, required=True)
    utilization.add_argument("--transition-log", type=Path, required=True)
    utilization.add_argument("--actor", default="principal")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "gate-resolve":
        result = resolve_gate(
            gate_id=args.gate_id,
            chosen_option=args.chosen_option,
            reason=args.reason,
            gates_dir=args.gates_dir,
            resolved_dir=args.resolved_dir,
            transition_log=args.transition_log,
            actor=args.actor,
        )
    elif args.command == "directive":
        result = issue_directive(
            target_role=args.target_role,
            message=args.message,
            org_dir=args.org_dir,
            transition_log=args.transition_log,
            actor=args.actor,
        )
    elif args.command == "control":
        result = issue_control(
            target_role=args.target_role,
            action=args.action,
            org_dir=args.org_dir,
            transition_log=args.transition_log,
            actor=args.actor,
        )
    elif args.command == "chat-send":
        result = send_chat_message(
            role_id=args.role_id,
            text=args.text,
            org_dir=args.org_dir,
            transition_log=args.transition_log,
            sender=args.sender,
        )
    elif args.command == "role-agent-utilization":
        result = update_role_agent_utilization(
            role_id=args.role_id,
            caps=json.loads(args.caps_json),
            org_dir=args.org_dir,
            transition_log=args.transition_log,
            actor=args.actor,
        )
    else:  # pragma: no cover - argparse enforces choices.
        parser.error(f"unknown command: {args.command}")
    print(json.dumps(result.as_dict(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
