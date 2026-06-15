"""Governed mutation proof chains.

A governed mutation proof is a compact review artifact over existing kernel
records. It is not a ledger and it does not authorize mutation. Its job is to
make the expected chain for an approved state change explicit and
machine-checkable enough for demos, adapters, and audit exports to share one
shape.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any


GOVERNED_MUTATION_PROOF_KIND = "governed_mutation_proof"
GOVERNED_MUTATION_PROOF_STAGES = (
    "run",
    "work_item",
    "proposal",
    "approval",
    "mutation",
    "attestation",
    "learning",
    "outcome",
    "review",
    "bundle",
    "commit",
)


@dataclass(frozen=True)
class ProofChainItem:
    stage: str
    ref: str


@dataclass(frozen=True)
class GovernedMutationProof:
    proof_kind: str
    proof_digest: str
    valid: bool
    step_id: str
    change_kind: str
    target_ref: str
    evidence_carrier_refs: list[str]
    chain: list[ProofChainItem]
    bundle_digest: str | None
    bundle_verdict: str | None
    commit: str
    validation_errors: list[str]


def build_governed_mutation_proof(
    *,
    step_id: str,
    change_kind: str,
    target_ref: str,
    run_id: str,
    work_id: str,
    proposal_id: str,
    approval_event_id: str,
    mutation_ref: str,
    attestation_id: str,
    learning_event_id: str,
    outcome_link_id: str,
    routine_review_id: str,
    bundle_id: str | None,
    bundle_digest: str | None,
    bundle_verdict: str | None,
    commit_sha: str,
    bundle_validation_errors: list[str] | None = None,
    evidence_carrier_refs: list[str] | None = None,
) -> GovernedMutationProof:
    """Build a deterministic proof row for an approved state mutation."""
    evidence_refs = _dedupe_refs(evidence_carrier_refs or [])
    chain = [
        ProofChainItem("run", f"run:{run_id}"),
        ProofChainItem("work_item", f"work_item:{work_id}"),
        ProofChainItem("proposal", f"governance_change:{proposal_id}"),
        ProofChainItem("approval", f"kernel_event:{approval_event_id}"),
        ProofChainItem("mutation", mutation_ref),
        ProofChainItem("attestation", f"action_attestation:{attestation_id}"),
        ProofChainItem("learning", f"learning_event:{learning_event_id}"),
        ProofChainItem("outcome", f"outcome_link:{outcome_link_id}"),
        ProofChainItem("review", f"routine_review:{routine_review_id}"),
        ProofChainItem("bundle", bundle_id or ""),
        ProofChainItem("commit", f"git:{commit_sha}" if commit_sha else ""),
    ]
    validation_errors = validate_governed_mutation_proof_parts(
        chain=chain,
        bundle_digest=bundle_digest,
        bundle_verdict=bundle_verdict,
        commit_sha=commit_sha,
        bundle_validation_errors=bundle_validation_errors or [],
    )
    payload = {
        "step_id": step_id,
        "change_kind": change_kind,
        "target_ref": target_ref,
        "evidence_carrier_refs": evidence_refs,
        "chain": [asdict(item) for item in chain],
        "bundle_digest": bundle_digest,
        "bundle_verdict": bundle_verdict,
        "commit": commit_sha,
    }
    return GovernedMutationProof(
        proof_kind=GOVERNED_MUTATION_PROOF_KIND,
        proof_digest=_proof_digest(payload),
        valid=not validation_errors,
        step_id=step_id,
        change_kind=change_kind,
        target_ref=target_ref,
        evidence_carrier_refs=evidence_refs,
        chain=chain,
        bundle_digest=bundle_digest,
        bundle_verdict=bundle_verdict,
        commit=commit_sha,
        validation_errors=validation_errors,
    )


def governed_mutation_proof_to_dict(proof: GovernedMutationProof) -> dict[str, Any]:
    return asdict(proof)


def validate_governed_mutation_proof_payload(payload: dict[str, Any]) -> list[str]:
    """Validate a serialized governed mutation proof and its digest."""
    if not isinstance(payload, dict):
        return ["proof payload must be a JSON object"]
    errors: list[str] = []
    if payload.get("proof_kind") != GOVERNED_MUTATION_PROOF_KIND:
        errors.append(f"proof_kind must be {GOVERNED_MUTATION_PROOF_KIND!r}")
    chain_payload = payload.get("chain")
    if not isinstance(chain_payload, list):
        errors.append("chain must be a list")
        chain: list[ProofChainItem] = []
    else:
        chain = []
        for index, item in enumerate(chain_payload):
            if not isinstance(item, dict):
                errors.append(f"chain[{index}] must be an object")
                continue
            stage = str(item.get("stage") or "")
            ref = str(item.get("ref") or "")
            chain.append(ProofChainItem(stage, ref))
    evidence_carrier_refs = payload.get("evidence_carrier_refs", [])
    if not isinstance(evidence_carrier_refs, list):
        errors.append("evidence_carrier_refs must be a list")
        evidence_carrier_refs = []
    else:
        invalid_refs = [
            index
            for index, ref in enumerate(evidence_carrier_refs)
            if not isinstance(ref, str) or not ref.strip()
        ]
        if invalid_refs:
            errors.append(
                "evidence_carrier_refs must contain non-empty strings at indexes: "
                + ", ".join(str(index) for index in invalid_refs)
            )
    errors.extend(
        validate_governed_mutation_proof_parts(
            chain=chain,
            bundle_digest=payload.get("bundle_digest"),
            bundle_verdict=payload.get("bundle_verdict"),
            commit_sha=str(payload.get("commit") or ""),
            bundle_validation_errors=payload.get("validation_errors") or [],
        )
    )
    digest = payload.get("proof_digest")
    if isinstance(digest, str) and digest.startswith("sha256:"):
        digest_payload = {
            "step_id": payload.get("step_id"),
            "change_kind": payload.get("change_kind"),
            "target_ref": payload.get("target_ref"),
            "evidence_carrier_refs": evidence_carrier_refs,
            "chain": chain_payload,
            "bundle_digest": payload.get("bundle_digest"),
            "bundle_verdict": payload.get("bundle_verdict"),
            "commit": payload.get("commit"),
        }
        expected = _proof_digest(digest_payload)
        if digest != expected:
            legacy_payload = dict(digest_payload)
            legacy_payload.pop("evidence_carrier_refs", None)
            legacy_expected = _proof_digest(legacy_payload)
            if digest != legacy_expected:
                errors.append(f"proof_digest mismatch: expected {expected}, got {digest}")
    else:
        errors.append("proof_digest must be a sha256 digest")
    if bool(payload.get("valid")) != (not errors):
        errors.append("valid flag does not match proof validation result")
    return errors


def validate_governed_mutation_proof_parts(
    *,
    chain: list[ProofChainItem],
    bundle_digest: Any,
    bundle_verdict: Any,
    commit_sha: str,
    bundle_validation_errors: list[Any],
) -> list[str]:
    errors: list[str] = []
    stages = [item.stage for item in chain]
    expected = list(GOVERNED_MUTATION_PROOF_STAGES)
    if stages != expected:
        errors.append(f"chain stages must be {expected}; got {stages}")
    missing_refs = [item.stage for item in chain if not item.ref]
    if missing_refs:
        errors.append("chain refs missing for stages: " + ", ".join(missing_refs))
    if bundle_validation_errors:
        errors.append("bundle validation errors present")
    if bundle_verdict != "passed":
        errors.append("bundle verdict must be passed")
    if not isinstance(bundle_digest, str) or not bundle_digest.startswith("sha256:"):
        errors.append("bundle_digest must be a sha256 digest")
    if not commit_sha:
        errors.append("commit is required")
    return errors


def _proof_digest(payload: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _dedupe_refs(refs: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for ref in refs:
        text = str(ref or "").strip()
        if text and text not in seen:
            seen.add(text)
            deduped.append(text)
    return deduped
