"""Action and artifact attestations for agent/runtime provenance.

Human work sessions record bounded human work and receipts. Action
attestations are the machine-side counterpart: a compact provenance row for an
agent, runtime, tool, or script action that produced an artifact or side effect.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from cognitive_firm.common.paths import ORG_ROOT_DIR


SubjectKind = Literal["artifact", "action", "runtime_event", "tool_call", "dataset", "prompt"]
VerificationStatus = Literal["unverified", "verified", "failed", "not_applicable"]

DEFAULT_ACTION_ATTESTATION_LOG = ORG_ROOT_DIR / "attestations" / "action_attestations.jsonl"
VALID_SUBJECT_KINDS = {"artifact", "action", "runtime_event", "tool_call", "dataset", "prompt"}
VALID_VERIFICATION_STATUSES = {"unverified", "verified", "failed", "not_applicable"}


@dataclass(frozen=True)
class ActionAttestation:
    attestation_id: str
    created_at_utc: str
    subject_kind: SubjectKind
    subject_ref: str
    subject_digest: str
    producer: str
    action_type: str
    runtime_ref: str | None = None
    tool_ref: str | None = None
    policy_ref: str | None = None
    input_refs: list[str] = field(default_factory=list)
    output_refs: list[str] = field(default_factory=list)
    signature_ref: str | None = None
    transparency_ref: str | None = None
    verification_status: VerificationStatus = "unverified"
    verification_summary: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    run_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate(value: str, allowed: set[str], label: str) -> str:
    if value not in allowed:
        raise ValueError(f"invalid {label} {value!r}; expected one of {sorted(allowed)}")
    return value


def digest_text(value: str) -> str:
    """Return a stable SHA-256 digest for a string subject."""
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def digest_file(path: Path) -> str:
    """Return a SHA-256 digest for a local file."""
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


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


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def create_action_attestation(
    *,
    subject_kind: SubjectKind | str,
    subject_ref: str,
    subject_digest: str,
    producer: str,
    action_type: str,
    runtime_ref: str | None = None,
    tool_ref: str | None = None,
    policy_ref: str | None = None,
    input_refs: list[str] | None = None,
    output_refs: list[str] | None = None,
    signature_ref: str | None = None,
    transparency_ref: str | None = None,
    verification_status: VerificationStatus | str = "unverified",
    verification_summary: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    run_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    attestation_id: str | None = None,
    log_path: Path | None = None,
) -> ActionAttestation:
    """Create a provenance row for an action, tool call, or artifact."""
    if not subject_ref.strip():
        raise ValueError("subject_ref is required")
    if not subject_digest.strip():
        raise ValueError("subject_digest is required")
    if not producer.strip():
        raise ValueError("producer is required")
    if not action_type.strip():
        raise ValueError("action_type is required")

    attestation = ActionAttestation(
        attestation_id=attestation_id or f"aat_{uuid.uuid4().hex[:12]}",
        created_at_utc=_now_iso(),
        subject_kind=_validate(str(subject_kind), VALID_SUBJECT_KINDS, "subject_kind"),  # type: ignore[arg-type]
        subject_ref=subject_ref,
        subject_digest=subject_digest,
        producer=producer,
        action_type=action_type,
        runtime_ref=runtime_ref,
        tool_ref=tool_ref,
        policy_ref=policy_ref,
        input_refs=input_refs or [],
        output_refs=output_refs or [],
        signature_ref=signature_ref,
        transparency_ref=transparency_ref,
        verification_status=_validate(
            str(verification_status),
            VALID_VERIFICATION_STATUSES,
            "verification_status",
        ),  # type: ignore[arg-type]
        verification_summary=verification_summary,
        tenant_id=tenant_id,
        project_id=project_id,
        run_id=run_id,
        metadata=metadata or {},
    )
    _append_jsonl(log_path or DEFAULT_ACTION_ATTESTATION_LOG, asdict(attestation))
    return attestation


def list_action_attestations(
    *,
    subject_ref: str | None = None,
    producer: str | None = None,
    tenant_id: str | None = None,
    project_id: str | None = None,
    run_id: str | None = None,
    verification_status: VerificationStatus | str | None = None,
    log_path: Path | None = None,
) -> list[ActionAttestation]:
    if verification_status is not None:
        verification_status = _validate(
            str(verification_status),
            VALID_VERIFICATION_STATUSES,
            "verification_status",
        )
    out: list[ActionAttestation] = []
    for row in _read_jsonl(log_path or DEFAULT_ACTION_ATTESTATION_LOG):
        attestation = ActionAttestation(**row)
        if subject_ref is not None and attestation.subject_ref != subject_ref:
            continue
        if producer is not None and attestation.producer != producer:
            continue
        if tenant_id is not None and attestation.tenant_id != tenant_id:
            continue
        if project_id is not None and attestation.project_id != project_id:
            continue
        if run_id is not None and attestation.run_id != run_id:
            continue
        if (
            verification_status is not None
            and attestation.verification_status != verification_status
        ):
            continue
        out.append(attestation)
    return out


def action_attestation_summary(attestation: ActionAttestation) -> dict[str, Any]:
    return asdict(attestation)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manage cognitive-firm action attestations.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--subject-ref")
    list_parser.add_argument("--producer")
    list_parser.add_argument("--tenant-id")
    list_parser.add_argument("--project-id")
    list_parser.add_argument("--run-id")
    list_parser.add_argument("--verification-status")
    list_parser.add_argument("--log-path", type=Path)

    digest_text_parser = sub.add_parser("digest-text")
    digest_text_parser.add_argument("value")

    digest_file_parser = sub.add_parser("digest-file")
    digest_file_parser.add_argument("path", type=Path)

    create_parser = sub.add_parser("create")
    create_parser.add_argument("--subject-kind", required=True)
    create_parser.add_argument("--subject-ref", required=True)
    create_parser.add_argument("--subject-digest", required=True)
    create_parser.add_argument("--producer", required=True)
    create_parser.add_argument("--action-type", required=True)
    create_parser.add_argument("--runtime-ref")
    create_parser.add_argument("--tool-ref")
    create_parser.add_argument("--policy-ref")
    create_parser.add_argument("--input-ref", action="append", default=[])
    create_parser.add_argument("--output-ref", action="append", default=[])
    create_parser.add_argument("--signature-ref")
    create_parser.add_argument("--transparency-ref")
    create_parser.add_argument("--verification-status", default="unverified")
    create_parser.add_argument("--verification-summary")
    create_parser.add_argument("--tenant-id")
    create_parser.add_argument("--project-id")
    create_parser.add_argument("--run-id")
    create_parser.add_argument("--log-path", type=Path)

    args = parser.parse_args(argv)
    if args.cmd == "list":
        rows = list_action_attestations(
            subject_ref=args.subject_ref,
            producer=args.producer,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            run_id=args.run_id,
            verification_status=args.verification_status,
            log_path=args.log_path,
        )
        for row in rows:
            print(json.dumps(action_attestation_summary(row), sort_keys=True))
        return 0

    if args.cmd == "digest-text":
        print(digest_text(args.value))
        return 0

    if args.cmd == "digest-file":
        print(digest_file(args.path))
        return 0

    if args.cmd == "create":
        row = create_action_attestation(
            subject_kind=args.subject_kind,
            subject_ref=args.subject_ref,
            subject_digest=args.subject_digest,
            producer=args.producer,
            action_type=args.action_type,
            runtime_ref=args.runtime_ref,
            tool_ref=args.tool_ref,
            policy_ref=args.policy_ref,
            input_refs=args.input_ref,
            output_refs=args.output_ref,
            signature_ref=args.signature_ref,
            transparency_ref=args.transparency_ref,
            verification_status=args.verification_status,
            verification_summary=args.verification_summary,
            tenant_id=args.tenant_id,
            project_id=args.project_id,
            run_id=args.run_id,
            log_path=args.log_path,
        )
        print(json.dumps(action_attestation_summary(row), sort_keys=True))
        return 0

    raise AssertionError(args.cmd)


if __name__ == "__main__":
    raise SystemExit(main())
