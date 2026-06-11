from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cognitive_firm.common.paths import PROJECTS_DIR, REPO_ROOT
from cognitive_firm.orchestration.action_attestation import (
    action_attestation_summary,
    list_action_attestations,
)
from cognitive_firm.orchestration.accountability_cases import (
    accountability_case_summary,
    list_accountability_cases,
)
from cognitive_firm.orchestration.human_work import list_human_work_sessions
from cognitive_firm.orchestration.leases import lease_summary, list_leases
from cognitive_firm.orchestration.outcome_links import list_outcome_links
from cognitive_firm.orchestration.run_checkpoints import get_run
from cognitive_firm.orchestration.work_items import list_work_items
from cognitive_firm.orchestration.formal_verification import (
    PROVIDER_PAYLOAD_SIGNATURE_KEY,
    PROVIDER_PAYLOAD_SIGNATURE_VERIFIED_KEY,
    formal_verification_summary,
    list_formal_verifications,
    trusted_provider_entry,
)
from cognitive_firm.orchestration.kernel_events import list_kernel_events
from cognitive_firm.orchestration.eu_ai_act_deploy_gate import compute_mandate_hash

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - bare Python product path.
    yaml = None


GOVERNED_RUN_BUNDLE_VERSION = "governed-run-attestation/v1"
GOVERNED_RUN_BUNDLE_SCHEMA_PATH = REPO_ROOT / "schemas" / "governed-run-attestation.v1.schema.json"
GOVERNED_RUN_BUNDLE_SCHEMA: dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://example.com/cognitive-firm/schemas/governed-run-attestation.v1.schema.json",
    "title": "Governed Run Attestation Bundle v1",
    "type": "object",
    "required": [
        "bundle_id",
        "bundle_version",
        "created_at_utc",
        "verifier",
        "run",
        "action_attestations",
        "formal_verifications",
        "human_work_sessions",
        "outcome_links",
        "accountability_cases",
        "work_items",
        "leases",
        "approval_events",
        "evidence_hashes",
        "observability_refs",
        "authority_snapshot",
        "verdict",
        "caveats",
        "bundle_digest",
    ],
    "additionalProperties": False,
    "properties": {
        "bundle_id": {"type": "string", "pattern": "^gab_.+"},
        "bundle_version": {"type": "string", "const": GOVERNED_RUN_BUNDLE_VERSION},
        "created_at_utc": {"type": "string", "minLength": 1},
        "verifier": {"type": "string", "minLength": 1},
        "run": {
            "type": "object",
            "required": ["run_id", "owner_role", "objective", "state", "checkpoints"],
            "additionalProperties": True,
            "properties": {
                "run_id": {"type": "string", "minLength": 1},
                "owner_role": {"type": "string", "minLength": 1},
                "objective": {"type": "string"},
                "state": {
                    "type": "string",
                    "enum": ["running", "paused", "completed", "failed", "cancelled"],
                },
                "checkpoints": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": True,
                        "properties": {
                            "step_id": {"type": ["string", "null"]},
                            "status": {"type": ["string", "null"]},
                            "summary": {"type": ["string", "null"]},
                            "payload_ref": {"type": ["string", "null"]},
                            "side_effect_key": {"type": ["string", "null"]},
                            "event_id": {"type": ["string", "null"]},
                            "ts": {"type": ["string", "null"]},
                        },
                    },
                },
            },
        },
        "action_attestations": {"type": "array", "items": {"type": "object"}},
        "formal_verifications": {"type": "array", "items": {"type": "object"}},
        "human_work_sessions": {"type": "array", "items": {"type": "object"}},
        "outcome_links": {"type": "array", "items": {"type": "object"}},
        "accountability_cases": {"type": "array", "items": {"type": "object"}},
        "work_items": {"type": "array", "items": {"type": "object"}},
        "leases": {"type": "array", "items": {"type": "object"}},
        "approval_events": {"type": "array", "items": {"type": "object"}},
        "evidence_hashes": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["kind", "source", "ref", "algorithm", "digest"],
                "additionalProperties": True,
                "properties": {
                    "kind": {"type": "string", "minLength": 1},
                    "source": {"type": "string", "minLength": 1},
                    "ref": {"type": "string", "minLength": 1},
                    "algorithm": {"type": "string", "minLength": 1},
                    "digest": {"type": "string", "minLength": 1},
                },
            },
        },
        "observability_refs": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["kind", "source", "ref"],
                "additionalProperties": True,
                "properties": {
                    "kind": {"type": "string", "minLength": 1},
                    "source": {"type": "string", "minLength": 1},
                    "ref": {"type": "string", "minLength": 1},
                },
            },
        },
        "authority_snapshot": {
            "type": "object",
            "required": ["owner_role", "status"],
            "additionalProperties": True,
            "properties": {
                "owner_role": {"type": ["string", "null"]},
                "status": {"type": "string", "minLength": 1},
            },
        },
        "verdict": {"type": "string", "enum": ["passed", "incomplete", "failed"]},
        "caveats": {"type": "array", "items": {"type": "string"}},
        "bundle_digest": {"type": "string", "pattern": "^sha256:[0-9a-f]{64}$"},
    },
}


@dataclass
class BundleArtifact:
    kind: str
    path: str
    exists: bool
    note: str | None = None


@dataclass
class DebateBundle:
    task_id: str
    project: str
    run_id: str | None
    stage: str | None
    stage_verdict: str | None
    summary: str
    artifacts: list[BundleArtifact]
    context: dict[str, Any]


@dataclass(frozen=True)
class GovernedRunAttestationBundle:
    """Portable audit summary for one governed run.

    The bundle is an export view over existing logs. It is not a second ledger
    and it does not assert that the run's output is correct.
    """

    bundle_id: str
    bundle_version: str
    created_at_utc: str
    verifier: str
    run: dict[str, Any]
    action_attestations: list[dict[str, Any]]
    formal_verifications: list[dict[str, Any]]
    human_work_sessions: list[dict[str, Any]]
    outcome_links: list[dict[str, Any]]
    accountability_cases: list[dict[str, Any]]
    work_items: list[dict[str, Any]]
    leases: list[dict[str, Any]]
    approval_events: list[dict[str, Any]]
    evidence_hashes: list[dict[str, Any]]
    observability_refs: list[dict[str, Any]]
    authority_snapshot: dict[str, Any]
    verdict: str
    caveats: list[str]
    bundle_digest: str


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _maybe_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return _read_json(path)
    except Exception:
        return None


def _artifact(path: Path, note: str | None = None) -> BundleArtifact:
    try:
        rel = path.relative_to(REPO_ROOT)
        path_str = str(rel)
    except ValueError:
        path_str = str(path)
    return BundleArtifact(
        kind=path.suffix.lstrip(".") or "file",
        path=path_str,
        exists=path.exists(),
        note=note,
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_digest(payload: dict[str, Any]) -> str:
    return _stable_value_digest(payload)


def _stable_value_digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")

    return "sha256:" + hashlib.sha256(encoded).hexdigest()


_ROLE_REF_RE = re.compile(r"^(?:role\.)?[A-Za-z0-9_-]+$")


def _file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _display_path(path: Path, *, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def _role_slug(owner_role: str | None) -> str | None:
    if not owner_role:
        return None
    text = str(owner_role).strip()
    if not _ROLE_REF_RE.fullmatch(text):
        return None
    return text.removeprefix("role.")


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if yaml is None:
        return {}
    data = yaml.safe_load(text) or {}
    return data if isinstance(data, dict) else {}


def _resolve_authority_path(repo_root: Path, ref: str | None) -> Path | None:
    if ref is None or not str(ref).strip():
        return None
    path = Path(str(ref))
    return path if path.is_absolute() else repo_root / path


def build_authority_snapshot(
    owner_role: str | None,
    *,
    authority_root: Path | None = None,
) -> dict[str, Any]:
    """Return role/mandate evidence for a run owner when local files exist.

    This is a snapshot for review, not a new authorization gate. Missing role
    files are reported in the snapshot but do not change bundle verdict.
    """
    repo_root = authority_root or REPO_ROOT
    slug = _role_slug(owner_role)
    snapshot: dict[str, Any] = {
        "owner_role": owner_role,
        "status": "unresolved",
        "role_ref": None,
        "role_digest": None,
        "mandate_ref": None,
        "mandate_digest": None,
        "mandate_hash": None,
        "notes": [],
    }
    if slug is None:
        snapshot["status"] = "invalid_or_missing_owner_role"
        snapshot["notes"].append("owner_role is absent or not a simple role reference")
        return snapshot

    role_path = repo_root / "org" / "roles" / f"{slug}.yaml"
    snapshot["role_ref"] = _display_path(role_path, repo_root=repo_root)
    if not role_path.exists():
        snapshot["status"] = "role_missing"
        snapshot["notes"].append("role file was not found under org/roles")
        return snapshot

    role_yaml = _load_yaml_mapping(role_path)
    snapshot["role_digest"] = _file_digest(role_path)
    mandate_ref = role_yaml.get("mandate_path")
    if mandate_ref is None:
        mandate_ref = f"org/mandates/{slug}_mandate.md"
    mandate_path = _resolve_authority_path(repo_root, str(mandate_ref))
    if mandate_path is not None:
        snapshot["mandate_ref"] = _display_path(mandate_path, repo_root=repo_root)
    if mandate_path is None or not mandate_path.exists():
        snapshot["status"] = "mandate_missing"
        snapshot["notes"].append("mandate file was not found")
        snapshot["mandate_hash"] = compute_mandate_hash(role_yaml, "")
        return snapshot

    mandate_text = mandate_path.read_text(encoding="utf-8")
    snapshot["mandate_digest"] = _file_digest(mandate_path)
    snapshot["mandate_hash"] = compute_mandate_hash(role_yaml, mandate_text)
    snapshot["status"] = "resolved"
    return snapshot


def _metadata_mentions_run(metadata: dict[str, Any], run_id: str) -> bool:
    run_refs = {
        run_id,
        f"run:{run_id}",
        f"cognitive_run:{run_id}",
    }
    for key in ("run_id", "cognitive_run_id", "run_ref", "cognitive_run_ref"):
        if str(metadata.get(key) or "") in run_refs:
            return True
    for value in metadata.values():
        if isinstance(value, str) and value in run_refs:
            return True
        if isinstance(value, list) and any(str(item) in run_refs for item in value):
            return True
    return False


def _formal_verification_provider(row: dict[str, Any]) -> str | None:
    provider = (row.get("metadata") or {}).get("provider")
    if isinstance(provider, str) and provider.strip():
        return provider.strip()
    return None


def _formal_verification_trust_caveat(
    row: dict[str, Any],
    *,
    authority_root: Path | None,
    extra_trusted: set[str] | None,
) -> str | None:
    provider = _formal_verification_provider(row)
    if provider is None:
        return None
    entry = trusted_provider_entry(
        provider,
        authority_root=authority_root,
        extra_trusted=extra_trusted,
    )
    verification_id = str(row.get("verification_id") or "<unknown>")
    if entry is None:
        return f"{verification_id} provider {provider!r} is not trusted"
    metadata = row.get("metadata") or {}
    if not isinstance(metadata, dict):
        return f"{verification_id} provider metadata is malformed"
    missing: list[str] = []
    if entry.get("requires_payload_signature"):
        if not metadata.get(PROVIDER_PAYLOAD_SIGNATURE_KEY):
            missing.append(PROVIDER_PAYLOAD_SIGNATURE_KEY)
        if not entry.get("public_key_pem"):
            missing.append("trusted_provider_public_key")
        if metadata.get(PROVIDER_PAYLOAD_SIGNATURE_VERIFIED_KEY) is not True:
            missing.append(PROVIDER_PAYLOAD_SIGNATURE_VERIFIED_KEY)
    if entry.get("requires_reverification_refs"):
        checker_refs = metadata.get("checker_evidence_refs") or []
        if not isinstance(checker_refs, list) or not checker_refs:
            missing.append("checker_evidence_refs")
    if entry.get("requires_faithfulness_refs"):
        faithfulness_refs = metadata.get("faithfulness_refs") or []
        if not isinstance(faithfulness_refs, list) or not faithfulness_refs:
            missing.append("faithfulness_refs")
    if missing:
        return f"{verification_id} missing trusted-provider evidence: {', '.join(missing)}"
    return None


def _ref_mentions_run(value: str | None, run_id: str) -> bool:
    if not value:
        return False
    return value in {
        run_id,
        f"run:{run_id}",
        f"cognitive_run:{run_id}",
    }


def _work_item_ref(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    if text.startswith("work_item:"):
        work_id = text.split(":", 1)[1].strip()
        return work_id or None
    return None


def _collect_work_item_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"work_id", "work_item_id"} and isinstance(item, str) and item.strip():
                refs.add(item.strip())
            if isinstance(item, str):
                ref = _work_item_ref(item)
                if ref is not None:
                    refs.add(ref)
            refs.update(_collect_work_item_refs(item))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                ref = _work_item_ref(item)
                if ref is not None:
                    refs.add(ref)
            else:
                refs.update(_collect_work_item_refs(item))
    elif isinstance(value, str):
        ref = _work_item_ref(value)
        if ref is not None:
            refs.add(ref)
    return refs


def _artifact_refs_mention_run(artifact_refs: Any, run_id: str) -> bool:
    if not isinstance(artifact_refs, list):
        return False
    for item in artifact_refs:
        if isinstance(item, str) and _ref_mentions_run(item, run_id):
            return True
        if isinstance(item, dict):
            for key in ("path", "ref", "run_id"):
                value = item.get(key)
                if isinstance(value, str) and _ref_mentions_run(value, run_id):
                    return True
    return False


def _collect_ref_values(value: Any, keys: set[str]) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in keys and isinstance(item, str) and item.strip():
                refs.add(item.strip())
            refs.update(_collect_ref_values(item, keys))
    elif isinstance(value, list):
        for item in value:
            refs.update(_collect_ref_values(item, keys))
    return refs


def _collect_governance_approval_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(item, str) or not item.strip():
                refs.update(_collect_governance_approval_refs(item))
                continue
            text = item.strip()
            if key in {"governance_change_id", "proposal_id"}:
                refs.add(text)
            elif key == "approval_event_id" and text.startswith("kevt_"):
                refs.add(text)
            elif key == "approval_ref" and (
                text.startswith("governance_change:")
                or text.startswith("gcp_")
                or text.startswith("kevt_")
            ):
                refs.add(text)
            refs.update(_collect_governance_approval_refs(item))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                text = item.strip()
                if text.startswith("governance_change:") or text.startswith("gcp_"):
                    refs.add(text)
            else:
                refs.update(_collect_governance_approval_refs(item))
    return refs


def _approval_ref_matches_event(ref: str, event: dict[str, Any]) -> bool:
    if ref == event.get("event_id"):
        return True
    object_ref = str(event.get("object_ref") or "")
    if ref == object_ref:
        return True
    if ref.startswith("gcp_") and object_ref == f"governance_change:{ref}":
        return True
    return False


_OBSERVABILITY_KEYS = {
    "observability_ref",
    "observability_refs",
    "trace_ref",
    "trace_refs",
    "trace_id",
    "trace_ids",
    "span_ref",
    "span_refs",
    "span_id",
    "span_ids",
    "otel_trace_id",
    "otel_trace_ids",
    "otel_span_id",
    "otel_span_ids",
}


def _collect_observability_ref_values(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _OBSERVABILITY_KEYS:
                if isinstance(item, str) and item.strip():
                    refs.add(item.strip())
                elif isinstance(item, list):
                    refs.update(
                        entry.strip()
                        for entry in item
                        if isinstance(entry, str) and entry.strip()
                    )
            refs.update(_collect_observability_ref_values(item))
    elif isinstance(value, list):
        for item in value:
            refs.update(_collect_observability_ref_values(item))
    return refs


def _observability_refs_for_run(run: dict[str, Any]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = [
        {
            "kind": "otel_span_projection",
            "source": "run",
            "ref": f"cognitive_firm.run:{run.get('run_id')}",
            "run_id": run.get("run_id"),
        }
    ]
    for checkpoint in run.get("checkpoints") or []:
        event_id = checkpoint.get("event_id")
        payload_ref = checkpoint.get("payload_ref")
        side_effect_key = checkpoint.get("side_effect_key")
        if event_id:
            refs.append(
                {
                    "kind": "checkpoint_event",
                    "source": "run_checkpoint",
                    "ref": str(event_id),
                    "step_id": checkpoint.get("step_id"),
                    "status": checkpoint.get("status"),
                }
            )
        if payload_ref:
            refs.append(
                {
                    "kind": "payload_ref",
                    "source": "run_checkpoint",
                    "ref": str(payload_ref),
                    "step_id": checkpoint.get("step_id"),
                }
            )
        if side_effect_key:
            refs.append(
                {
                    "kind": "side_effect_key",
                    "source": "run_checkpoint",
                    "ref": str(side_effect_key),
                    "step_id": checkpoint.get("step_id"),
                }
            )
    return refs


def _observability_refs_for_attestations(
    attestations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for row in attestations:
        attestation_id = row.get("attestation_id")
        runtime_ref = row.get("runtime_ref")
        if runtime_ref:
            refs.append(
                {
                    "kind": "runtime_ref",
                    "source": "action_attestation",
                    "ref": str(runtime_ref),
                    "attestation_id": attestation_id,
                }
            )
        for ref in sorted(_collect_observability_ref_values(row.get("metadata") or {})):
            refs.append(
                {
                    "kind": "external_trace_ref",
                    "source": "action_attestation",
                    "ref": ref,
                    "attestation_id": attestation_id,
                }
            )
    return refs


def _dedupe_observability_refs(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str | None, str | None]] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        key = (
            str(row.get("kind") or ""),
            str(row.get("ref") or ""),
            str(row.get("source")) if row.get("source") is not None else None,
            str(row.get("attestation_id")) if row.get("attestation_id") is not None else None,
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _evidence_hash_row(
    *,
    kind: str,
    source: str,
    ref: str,
    digest: str,
    algorithm: str = "sha256",
    **extra: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "kind": kind,
        "source": source,
        "ref": ref,
        "algorithm": algorithm,
        "digest": digest,
    }
    row.update({key: value for key, value in extra.items() if value is not None})
    return row


def _record_set_hash(
    *,
    source: str,
    ref: str,
    rows: Any,
    count: int | None = None,
) -> dict[str, Any]:
    if count is None:
        count = len(rows) if isinstance(rows, list) else 1
    return _evidence_hash_row(
        kind="record_set_digest",
        source=source,
        ref=ref,
        digest=_stable_value_digest(rows),
        count=count,
    )


def _build_evidence_hashes(
    *,
    run_id: str,
    run: dict[str, Any],
    action_attestations: list[dict[str, Any]],
    formal_verifications: list[dict[str, Any]],
    human_work_sessions: list[dict[str, Any]],
    outcome_links: list[dict[str, Any]],
    accountability_cases: list[dict[str, Any]],
    work_items: list[dict[str, Any]],
    leases: list[dict[str, Any]],
    approval_events: list[dict[str, Any]],
    authority_snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build portable hashes over embedded evidence and contract refs.

    These hashes are derived from the rows already included in the bundle.
    They are a review index, not a second source of truth.
    """
    rows: list[dict[str, Any]] = [
        _record_set_hash(source="run", ref=run_id, rows=run),
        _record_set_hash(
            source="run_checkpoints",
            ref=run_id,
            rows=run.get("checkpoints") or [],
        ),
        _record_set_hash(
            source="action_attestations",
            ref=run_id,
            rows=action_attestations,
        ),
        _record_set_hash(
            source="formal_verifications",
            ref=run_id,
            rows=formal_verifications,
        ),
        _record_set_hash(
            source="human_work_sessions",
            ref=run_id,
            rows=human_work_sessions,
        ),
        _record_set_hash(source="outcome_links", ref=run_id, rows=outcome_links),
        _record_set_hash(
            source="accountability_cases",
            ref=run_id,
            rows=accountability_cases,
        ),
        _record_set_hash(source="work_items", ref=run_id, rows=work_items),
        _record_set_hash(source="leases", ref=run_id, rows=leases),
        _record_set_hash(source="approval_events", ref=run_id, rows=approval_events),
    ]

    role_digest = authority_snapshot.get("role_digest")
    if isinstance(role_digest, str) and role_digest:
        rows.append(
            _evidence_hash_row(
                kind="authority_contract_digest",
                source="authority_snapshot",
                ref=str(authority_snapshot.get("role_ref") or authority_snapshot.get("owner_role")),
                digest=role_digest,
            )
        )
    mandate_digest = authority_snapshot.get("mandate_digest")
    if isinstance(mandate_digest, str) and mandate_digest:
        rows.append(
            _evidence_hash_row(
                kind="authority_contract_digest",
                source="authority_snapshot",
                ref=str(authority_snapshot.get("mandate_ref") or authority_snapshot.get("owner_role")),
                digest=mandate_digest,
            )
        )
    mandate_hash = authority_snapshot.get("mandate_hash")
    if isinstance(mandate_hash, str) and mandate_hash:
        rows.append(
            _evidence_hash_row(
                kind="authority_contract_hash",
                source="authority_snapshot",
                ref=str(authority_snapshot.get("mandate_ref") or authority_snapshot.get("owner_role")),
                algorithm="cognitive_firm_mandate_hash",
                digest=mandate_hash,
            )
        )

    for row in action_attestations:
        subject_ref = row.get("subject_ref")
        subject_digest = row.get("subject_digest")
        if isinstance(subject_ref, str) and isinstance(subject_digest, str) and subject_digest:
            rows.append(
                _evidence_hash_row(
                    kind="subject_digest",
                    source="action_attestation",
                    ref=subject_ref,
                    digest=subject_digest,
                    attestation_id=row.get("attestation_id"),
                    subject_kind=row.get("subject_kind"),
                )
            )
        for ref in list(row.get("input_refs") or []) + list(row.get("output_refs") or []):
            if isinstance(ref, str) and ref.startswith("sha256:"):
                rows.append(
                    _evidence_hash_row(
                        kind="input_output_ref_digest",
                        source="action_attestation",
                        ref=ref,
                        digest=ref,
                        attestation_id=row.get("attestation_id"),
                    )
                )

    for row in formal_verifications:
        metadata = row.get("metadata") or {}
        if not isinstance(metadata, dict):
            continue
        for key in (
            "provider_payload_digest",
            "certificate_digest",
            "checker_evidence_digest",
            "faithfulness_digest",
        ):
            value = metadata.get(key)
            if isinstance(value, str) and value.startswith("sha256:"):
                rows.append(
                    _evidence_hash_row(
                        kind=key,
                        source="formal_verification",
                        ref=str(row.get("verification_id") or value),
                        digest=value,
                    )
                )

    seen: set[tuple[str, str, str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        key = (
            str(row.get("kind") or ""),
            str(row.get("source") or ""),
            str(row.get("ref") or ""),
            str(row.get("algorithm") or ""),
            str(row.get("digest") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def build_governed_run_attestation_bundle(
    run_id: str,
    *,
    transition_log_path: Path | None = None,
    action_attestation_log_path: Path | None = None,
    human_work_log_path: Path | None = None,
    outcome_links_log_path: Path | None = None,
    accountability_cases_log_path: Path | None = None,
    work_items_log_path: Path | None = None,
    formal_verification_log_path: Path | None = None,
    leases_log_path: Path | None = None,
    authority_root: Path | None = None,
    trusted_formal_verification_providers: set[str] | None = None,
) -> GovernedRunAttestationBundle:
    """Build an audit export for one run from the existing kernel logs.

    The bundle collects the run projection, matching action attestations,
    matching formal-verification records, matching human-work sessions, outcome
    links, and accountability cases. It intentionally reports caveats instead
    of upgrading provenance into a correctness claim.
    """
    projection = get_run(run_id, log_path=transition_log_path)
    attestations = [
        action_attestation_summary(row)
        for row in list_action_attestations(
            run_id=run_id,
            log_path=action_attestation_log_path,
        )
    ]
    if formal_verification_log_path is None and action_attestation_log_path is not None:
        formal_verification_log_path = action_attestation_log_path.with_name(
            "formal_verifications.jsonl"
        )
    formal_verifications = [
        formal_verification_summary(row)
        for row in list_formal_verifications(
            run_id=run_id,
            log_path=formal_verification_log_path,
        )
    ]
    human_sessions = [
        asdict(session)
        for session in list_human_work_sessions(log_path=human_work_log_path)
        if session.metadata.get("cognitive_run_id") == run_id
        or run_id in session.artifact_refs
        or session.agent_followup_ref == run_id
    ]
    outcome_links = [
        link.as_dict()
        for link in list_outcome_links(log_path=outcome_links_log_path)
        if _ref_mentions_run(link.change_ref, run_id)
        or _metadata_mentions_run(link.metadata, run_id)
    ]
    accountability_cases = [
        accountability_case_summary(case)
        for case in list_accountability_cases(log_path=accountability_cases_log_path)
        if _ref_mentions_run(case.trigger_ref, run_id)
        or _ref_mentions_run(case.authority_envelope_ref, run_id)
        or run_id in case.closure_evidence_refs
        or _metadata_mentions_run(case.metadata, run_id)
    ]
    explicit_work_item_ids: set[str] = set()
    idempotency_key = str(projection.idempotency_key or "")
    if idempotency_key.startswith("work:"):
        work_id = idempotency_key.split(":", 1)[1].strip()
        if work_id:
            explicit_work_item_ids.add(work_id)
    for row in attestations:
        explicit_work_item_ids.update(_collect_work_item_refs(row))
    for row in human_sessions:
        explicit_work_item_ids.update(_collect_work_item_refs(row))
    for row in outcome_links:
        explicit_work_item_ids.update(_collect_work_item_refs(row))
    for row in accountability_cases:
        explicit_work_item_ids.update(_collect_work_item_refs(row))
    work_items = [
        item.as_dict()
        for item in list_work_items(log_path=work_items_log_path)
        if item.work_id in explicit_work_item_ids
        or _metadata_mentions_run(item.metadata, run_id)
        or _artifact_refs_mention_run(item.artifact_refs, run_id)
    ]
    found_work_item_ids = {str(row.get("work_id")) for row in work_items}
    explicit_lease_ids: set[str] = set()
    for row in attestations:
        explicit_lease_ids.update(_collect_ref_values(row.get("metadata") or {}, {"lease_id"}))
        explicit_lease_ids.update(
            _collect_ref_values(
                {
                    "input_refs": row.get("input_refs") or [],
                    "output_refs": row.get("output_refs") or [],
                },
                {"lease_id"},
            )
        )
    lease_rows = list_leases(log_path=leases_log_path)
    lease_evidence = [
        lease_summary(lease)
        for lease in lease_rows
        if lease.lease_id in explicit_lease_ids
        or _metadata_mentions_run(lease.metadata, run_id)
        or _ref_mentions_run(lease.purpose, run_id)
    ]
    found_lease_ids = {str(row.get("lease_id")) for row in lease_evidence}
    explicit_approval_refs: set[str] = set()
    for row in attestations:
        explicit_approval_refs.update(
            _collect_governance_approval_refs(row.get("metadata") or {})
        )
        explicit_approval_refs.update(
            _collect_governance_approval_refs(row.get("input_refs") or [])
        )
        explicit_approval_refs.update(
            _collect_governance_approval_refs(row.get("output_refs") or [])
        )
    approval_events = [
        event.as_dict()
        for event in list_kernel_events(log_path=transition_log_path)
        if event.verb == "governance_change.approved"
        and (
            any(_approval_ref_matches_event(ref, event.as_dict()) for ref in explicit_approval_refs)
            or _metadata_mentions_run(event.payload, run_id)
        )
    ]
    matched_approval_refs = {
        ref
        for ref in explicit_approval_refs
        if any(_approval_ref_matches_event(ref, event) for event in approval_events)
    }
    authority_snapshot = build_authority_snapshot(
        projection.owner_role,
        authority_root=authority_root,
    )
    observability_refs = _dedupe_observability_refs(
        _observability_refs_for_run(projection.as_dict())
        + _observability_refs_for_attestations(attestations)
    )
    evidence_hashes = _build_evidence_hashes(
        run_id=run_id,
        run=projection.as_dict(),
        action_attestations=attestations,
        formal_verifications=formal_verifications,
        human_work_sessions=human_sessions,
        outcome_links=outcome_links,
        accountability_cases=accountability_cases,
        work_items=work_items,
        leases=lease_evidence,
        approval_events=approval_events,
        authority_snapshot=authority_snapshot,
    )

    caveats: list[str] = []
    if projection.state != "completed":
        caveats.append(f"run state is {projection.state!r}, not 'completed'")
    if not attestations:
        caveats.append("no action attestations are linked to this run")
    failed_attestations = [
        row["attestation_id"]
        for row in attestations
        if row.get("verification_status") == "failed"
    ]
    unverified_attestations = [
        row["attestation_id"]
        for row in attestations
        if row.get("verification_status") == "unverified"
    ]
    if failed_attestations:
        caveats.append("failed action attestations: " + ", ".join(failed_attestations))
    if unverified_attestations:
        caveats.append("unverified action attestations: " + ", ".join(unverified_attestations))
    failed_formal_verifications = [
        row["verification_id"]
        for row in formal_verifications
        if row.get("verdict") in {"refuted", "invalid"}
    ]
    inconclusive_formal_verifications = [
        row["verification_id"]
        for row in formal_verifications
        if row.get("verdict") == "inconclusive"
    ]
    formal_provider_trust_caveats = [
        issue
        for row in formal_verifications
        if row.get("verdict") == "verified"
        for issue in [
            _formal_verification_trust_caveat(
                row,
                authority_root=authority_root,
                extra_trusted=trusted_formal_verification_providers,
            )
        ]
        if issue is not None
    ]
    if failed_formal_verifications:
        caveats.append(
            "failed formal verifications: " + ", ".join(failed_formal_verifications)
        )
    if inconclusive_formal_verifications:
        caveats.append(
            "inconclusive formal verifications: "
            + ", ".join(inconclusive_formal_verifications)
        )
    if formal_provider_trust_caveats:
        caveats.append(
            "verified formal verifications with trust caveats: "
            + "; ".join(formal_provider_trust_caveats)
        )
    missing_receipts = [
        row["session_id"]
        for row in human_sessions
        if row.get("receipt_required") and not row.get("receipt")
    ]
    if missing_receipts:
        caveats.append("human-work sessions missing receipts: " + ", ".join(missing_receipts))
    unresolved_outcome_links = [
        row["outcome_link_id"]
        for row in outcome_links
        if row.get("status") != "verdict_recorded"
    ]
    if unresolved_outcome_links:
        caveats.append("outcome links awaiting verdict: " + ", ".join(unresolved_outcome_links))
    unresolved_accountability_cases = [
        row["case_id"]
        for row in accountability_cases
        if row.get("status") not in {"accepted_risk", "closed"}
    ]
    if unresolved_accountability_cases:
        caveats.append(
            "accountability cases not closed: " + ", ".join(unresolved_accountability_cases)
        )
    missing_referenced_leases = sorted(explicit_lease_ids - found_lease_ids)
    if missing_referenced_leases:
        caveats.append(
            "referenced leases not found: " + ", ".join(missing_referenced_leases)
        )
    missing_work_item_refs = sorted(explicit_work_item_ids - found_work_item_ids)
    if missing_work_item_refs:
        caveats.append(
            "referenced work items not found: " + ", ".join(missing_work_item_refs)
        )
    failed_work_items = [
        str(row.get("work_id"))
        for row in work_items
        if row.get("status") in {"failed", "dead_letter"}
    ]
    incomplete_work_items = [
        str(row.get("work_id"))
        for row in work_items
        if row.get("status") not in {"done", "failed", "dead_letter"}
    ]
    if failed_work_items:
        caveats.append("failed work items: " + ", ".join(failed_work_items))
    if incomplete_work_items:
        caveats.append("work items not completed: " + ", ".join(incomplete_work_items))
    missing_approval_refs = sorted(explicit_approval_refs - matched_approval_refs)
    if missing_approval_refs:
        caveats.append(
            "referenced governance approvals not found: " + ", ".join(missing_approval_refs)
        )

    if (
        failed_attestations
        or failed_formal_verifications
        or failed_work_items
        or projection.state in {"failed", "cancelled"}
    ):
        verdict = "failed"
    elif caveats:
        verdict = "incomplete"
    else:
        verdict = "passed"

    payload_without_digest = {
        "bundle_id": f"gab_{run_id}",
        "bundle_version": GOVERNED_RUN_BUNDLE_VERSION,
        "created_at_utc": _now_iso(),
        "verifier": "cognitive_firm.orchestration.artifact_bundle.build_governed_run_attestation_bundle",
        "run": projection.as_dict(),
        "action_attestations": attestations,
        "formal_verifications": formal_verifications,
        "human_work_sessions": human_sessions,
        "outcome_links": outcome_links,
        "accountability_cases": accountability_cases,
        "work_items": work_items,
        "leases": lease_evidence,
        "approval_events": approval_events,
        "evidence_hashes": evidence_hashes,
        "observability_refs": observability_refs,
        "authority_snapshot": authority_snapshot,
        "verdict": verdict,
        "caveats": caveats,
    }
    return GovernedRunAttestationBundle(
        **payload_without_digest,
        bundle_digest=_stable_digest(payload_without_digest),
    )


def governed_run_bundle_to_dict(bundle: GovernedRunAttestationBundle) -> dict[str, Any]:
    return asdict(bundle)


def _load_governed_run_bundle_schema(schema_path: Path | None = None) -> dict[str, Any]:
    if schema_path is not None:
        return json.loads(schema_path.read_text(encoding="utf-8"))
    if GOVERNED_RUN_BUNDLE_SCHEMA_PATH.exists():
        return json.loads(GOVERNED_RUN_BUNDLE_SCHEMA_PATH.read_text(encoding="utf-8"))
    return GOVERNED_RUN_BUNDLE_SCHEMA


def validate_governed_run_bundle_payload(
    payload: dict[str, Any],
    *,
    schema_path: Path | None = None,
) -> list[str]:
    """Validate a governed-run bundle's interchange shape and digest."""
    if not isinstance(payload, dict):
        return ["bundle payload must be a JSON object"]
    try:
        import jsonschema
        from jsonschema import Draft202012Validator
    except ImportError:  # pragma: no cover - jsonschema is a hard dependency.
        return ["jsonschema is not installed; cannot validate governed-run bundle"]

    try:
        schema = _load_governed_run_bundle_schema(schema_path)
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(payload), key=lambda err: list(err.absolute_path))
    except (json.JSONDecodeError, OSError) as exc:
        return [f"governed-run bundle schema could not be read: {exc}"]
    except jsonschema.exceptions.SchemaError as exc:
        return [f"governed-run bundle schema is invalid: {exc.message}"]

    messages: list[str] = []
    for err in errors:
        location = "/".join(str(part) for part in err.absolute_path)
        prefix = f"payload.{location}: " if location else ""
        messages.append(f"{prefix}{err.message}")

    digest = payload.get("bundle_digest")
    if isinstance(digest, str):
        payload_without_digest = dict(payload)
        payload_without_digest.pop("bundle_digest", None)
        expected = _stable_digest(payload_without_digest)
        if digest != expected:
            messages.append(f"bundle_digest mismatch: expected {expected}, got {digest}")
    return messages


def governed_run_bundle_summary(bundle: GovernedRunAttestationBundle) -> dict[str, Any]:
    """Return the compact review surface for a governed-run bundle."""
    return {
        "bundle_id": bundle.bundle_id,
        "run_id": bundle.run.get("run_id"),
        "run_state": bundle.run.get("state"),
        "owner_role": bundle.run.get("owner_role"),
        "tenant_id": bundle.run.get("tenant_id"),
        "project_id": bundle.run.get("project_id"),
        "objective": bundle.run.get("objective"),
        "verdict": bundle.verdict,
        "caveats": bundle.caveats,
        "counts": {
            "checkpoints": len(bundle.run.get("checkpoints") or []),
            "action_attestations": len(bundle.action_attestations),
            "formal_verifications": len(bundle.formal_verifications),
            "human_work_sessions": len(bundle.human_work_sessions),
            "outcome_links": len(bundle.outcome_links),
            "accountability_cases": len(bundle.accountability_cases),
            "work_items": len(bundle.work_items),
            "leases": len(bundle.leases),
            "approval_events": len(bundle.approval_events),
            "evidence_hashes": len(bundle.evidence_hashes),
            "observability_refs": len(bundle.observability_refs),
        },
        "authority_snapshot": {
            "status": bundle.authority_snapshot.get("status"),
            "owner_role": bundle.authority_snapshot.get("owner_role"),
            "role_ref": bundle.authority_snapshot.get("role_ref"),
            "mandate_ref": bundle.authority_snapshot.get("mandate_ref"),
            "mandate_hash": bundle.authority_snapshot.get("mandate_hash"),
        },
        "ids": {
            "action_attestations": [
                str(row.get("attestation_id"))
                for row in bundle.action_attestations
                if row.get("attestation_id")
            ],
            "formal_verifications": [
                str(row.get("verification_id"))
                for row in bundle.formal_verifications
                if row.get("verification_id")
            ],
            "human_work_sessions": [
                str(row.get("session_id"))
                for row in bundle.human_work_sessions
                if row.get("session_id")
            ],
            "outcome_links": [
                str(row.get("outcome_link_id"))
                for row in bundle.outcome_links
                if row.get("outcome_link_id")
            ],
            "accountability_cases": [
                str(row.get("case_id"))
                for row in bundle.accountability_cases
                if row.get("case_id")
            ],
            "work_items": [
                str(row.get("work_id"))
                for row in bundle.work_items
                if row.get("work_id")
            ],
            "leases": [
                str(row.get("lease_id"))
                for row in bundle.leases
                if row.get("lease_id")
            ],
            "approval_events": [
                str(row.get("event_id"))
                for row in bundle.approval_events
                if row.get("event_id")
            ],
            "evidence_hashes": [
                f"{row.get('kind')}:{row.get('source')}:{row.get('ref')}"
                for row in bundle.evidence_hashes
                if row.get("kind") and row.get("source") and row.get("ref")
            ],
            "observability_refs": [
                str(row.get("ref"))
                for row in bundle.observability_refs
                if row.get("ref")
            ],
        },
        "bundle_digest": bundle.bundle_digest,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build or validate a governed-run attestation bundle.",
    )
    parser.add_argument("run_id", nargs="?", help="Cognitive-firm run id to export.")
    parser.add_argument(
        "--validate-json",
        type=Path,
        help="Validate an existing governed-run bundle JSON file instead of building one.",
    )
    parser.add_argument(
        "--schema-path",
        type=Path,
        help="Optional JSON Schema path for --validate-json.",
    )
    parser.add_argument(
        "--transition-log-path",
        type=Path,
        help="Path to runtime transition JSONL. Defaults to the kernel path.",
    )
    parser.add_argument(
        "--action-attestation-log-path",
        type=Path,
        help="Path to action attestation JSONL. Defaults to the kernel path.",
    )
    parser.add_argument(
        "--formal-verification-log-path",
        type=Path,
        help="Path to formal verification JSONL. Defaults to the kernel path.",
    )
    parser.add_argument(
        "--human-work-log-path",
        type=Path,
        help="Path to human work JSONL. Defaults to the kernel path.",
    )
    parser.add_argument(
        "--outcome-links-log-path",
        type=Path,
        help="Path to outcome links JSONL. Defaults to the kernel path.",
    )
    parser.add_argument(
        "--accountability-cases-log-path",
        type=Path,
        help="Path to accountability cases JSONL. Defaults to the kernel path.",
    )
    parser.add_argument(
        "--work-items-log-path",
        type=Path,
        help="Path to work items JSONL. Defaults to the kernel path.",
    )
    parser.add_argument(
        "--leases-log-path",
        type=Path,
        help="Path to leases JSONL. Defaults to the kernel path.",
    )
    parser.add_argument(
        "--authority-root",
        type=Path,
        help="Repository root containing org/roles and org/mandates. Defaults to this repo.",
    )
    parser.add_argument(
        "--trusted-formal-provider",
        action="append",
        default=[],
        help="Additional formal-verification provider to trust for this bundle export.",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print a compact review summary instead of the full bundle JSON.",
    )
    args = parser.parse_args(argv)

    if args.validate_json:
        payload = json.loads(args.validate_json.read_text(encoding="utf-8"))
        errors = validate_governed_run_bundle_payload(payload, schema_path=args.schema_path)
        print(json.dumps({"ok": not errors, "errors": errors}, indent=2, sort_keys=True))
        return 0 if not errors else 1
    if not args.run_id:
        parser.error("run_id is required unless --validate-json is supplied")

    bundle = build_governed_run_attestation_bundle(
        args.run_id,
        transition_log_path=args.transition_log_path,
        action_attestation_log_path=args.action_attestation_log_path,
        formal_verification_log_path=args.formal_verification_log_path,
        human_work_log_path=args.human_work_log_path,
        outcome_links_log_path=args.outcome_links_log_path,
        accountability_cases_log_path=args.accountability_cases_log_path,
        work_items_log_path=args.work_items_log_path,
        leases_log_path=args.leases_log_path,
        authority_root=args.authority_root,
        trusted_formal_verification_providers=set(args.trusted_formal_provider),
    )
    payload = governed_run_bundle_summary(bundle) if args.summary else governed_run_bundle_to_dict(bundle)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def infer_stage1_run_id(project: str) -> str | None:
    evidence_path = PROJECTS_DIR / project / "stage1_benchmark_evidence.json"
    data = _maybe_json(evidence_path)
    if not data:
        return None
    runs = data.get("evidence_runs") or []
    if not runs:
        return None
    latest = runs[-1]
    return latest.get("run_id")


def build_stage1_fail_bundle(project: str, run_id: str | None = None) -> DebateBundle:
    project_dir = PROJECTS_DIR / project
    run_id = run_id or infer_stage1_run_id(project)

    state_data = _maybe_json(project_dir / "meta_runner_state.json") or {}
    evidence_data = _maybe_json(project_dir / "stage1_benchmark_evidence.json") or {}
    forensic_data = _maybe_json(project_dir / "forensic_report.json") or {}

    artifacts = [
        _artifact(project_dir / "thesis.md", "Active stage-1 thesis"),
        _artifact(project_dir / "current_iteration.md", "Current iteration snapshot"),
        _artifact(project_dir / "test_model.py", "Stage-1 local harness"),
        _artifact(project_dir / "stage1_benchmark_evidence.json", "Promotion evidence"),
        _artifact(project_dir / "forensic_report.json", "Auto-generated fail triage"),
        _artifact(project_dir / "meta_runner_plan.json", "Stage queue"),
        _artifact(project_dir / "meta_runner_state.json", "Current stage verdict"),
    ]

    if run_id:
        run_root = REPO_ROOT / "benchmarks" / "constraint_memory" / "runs" / run_id
        artifacts.extend(
            [
                _artifact(run_root / "metrics_summary.json", "Benchmark summary"),
                _artifact(
                    run_root / "t2_ai_inference" / "B_deterministic_gates" / "eval_results.json",
                    "Target case under B",
                ),
                _artifact(
                    run_root / "t2_ai_inference" / "C_gates_plus_primitives" / "eval_results.json",
                    "Target case under C",
                ),
                _artifact(
                    run_root / "deterministic_score_contract" / "B_deterministic_gates" / "eval_results.json",
                    "Failed good control under B",
                ),
                _artifact(
                    run_root / "fail_closed_test_status" / "C_gates_plus_primitives" / "eval_results.json",
                    "Failed good control under C",
                ),
            ]
        )

    stage = None
    current_stage_idx = state_data.get("current_stage")
    plan = _maybe_json(project_dir / "meta_runner_plan.json") or {}
    queue = plan.get("queue") or []
    if isinstance(current_stage_idx, int) and 0 <= current_stage_idx < len(queue):
        stage = queue[current_stage_idx].get("name")

    summary = (
        "Stage-1 benchmark failed promotion: target case improved, but good controls regressed. "
        "Use this bundle to separate gate overreach from legitimate thesis falsification."
    )

    context = {
        "run_id": run_id,
        "meta_runner_state": state_data,
        "stage1_benchmark_evidence": evidence_data,
        "forensic_report": forensic_data,
        "required_outputs": {
            "finding_fields": ["id", "severity", "claim", "evidence", "proposed_fix", "confidence"],
            "decision_fields": ["do_not_change", "next_action", "requires_human_review"],
        },
    }

    task_id = f"{project}_{stage or 'stage'}_{run_id or 'no_run'}"
    return DebateBundle(
        task_id=task_id,
        project=project,
        run_id=run_id,
        stage=stage,
        stage_verdict=state_data.get("last_verdict"),
        summary=summary,
        artifacts=artifacts,
        context=context,
    )


def bundle_to_dict(bundle: DebateBundle) -> dict[str, Any]:
    return {
        "task_id": bundle.task_id,
        "project": bundle.project,
        "run_id": bundle.run_id,
        "stage": bundle.stage,
        "stage_verdict": bundle.stage_verdict,
        "summary": bundle.summary,
        "artifacts": [asdict(item) for item in bundle.artifacts],
        "context": bundle.context,
    }


if __name__ == "__main__":
    raise SystemExit(main())
