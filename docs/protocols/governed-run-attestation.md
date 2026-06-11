# Governed Run Attestation Bundle

**Status:** export view shipped.
**Module:** `cognitive_firm.orchestration.artifact_bundle`
**Tests:** `tests/test_governed_run_attestation_bundle.py`

The governed-run attestation bundle is a portable audit packet for one run.
It joins existing kernel records; it is not a new ledger and it does not prove
that the run's output is correct.

## What It Answers

Given one `run_id`, the bundle answers:

```text
What happened, what machine-side evidence exists, what formal certificates
say, what production work was claimed and completed, what human work was
requested, what outcome evidence is linked, and whether accountability was
closed?
```

This makes a governed run inspectable without asking a reviewer to understand
every JSONL file in the kernel.

## Included Surfaces

| Surface | Included as | Why |
|---|---|---|
| Run checkpoints | `run` | lifecycle state, checkpoints, pause/failure reason, side-effect keys |
| Action attestations | `action_attestations` | machine-side provenance and verification state |
| Formal verifications | `formal_verifications` | certificate-backed checks and formal verdicts |
| Human work sessions | `human_work_sessions` | bounded human work, receipts, and runtime resume refs |
| Outcome links | `outcome_links` | tenant verdicts on whether the governed change improved a measured outcome |
| Accountability cases | `accountability_cases` | residual-risk ownership, recourse, and closure evidence |
| Work items | `work_items` | claimable production work tied to the run, including claim status, bounded exit, producer, verifier, and artifacts |
| Leases | `leases` | time-bounded mutation claims linked to the run or referenced by action attestations |
| Approval events | `approval_events` | governance-change approval events linked to the run or referenced by action attestations |
| Evidence hashes | `evidence_hashes` | portable record-set, subject, input/output, provider, and authority-contract hashes derived from embedded evidence |
| Observability refs | `observability_refs` | OpenTelemetry span projection handle, checkpoint event ids, payload refs, side-effect keys, and external trace/span refs from action attestations |
| Authority snapshot | `authority_snapshot` | owner role file digest, mandate file digest, and authorization-relevant mandate hash when local files are present |

The bundle matches outcome links and accountability cases only when they
explicitly reference the run through `run:<run_id>`, `<run_id>`, or metadata
such as `cognitive_run_id`.

Work items are included when a run or linked record explicitly references
`work_item:<work_id>`, stores `work_id` / `work_item_id` in metadata, or when
the work item's own metadata or artifact refs mention the run. If an
attestation or closure record references a missing work item, the bundle is
`incomplete`. If linked production work is still queued, claimed, running, or
retired, the bundle is `incomplete`. If linked production work failed or
dead-lettered, the bundle is `failed`.

Leases are included when their metadata references the run, or when a linked
action attestation explicitly records a `lease_id` in metadata. If an action
attestation claims a lease id but the lease record is not found, the bundle is
`incomplete`.

Governance approval events are included when a linked action attestation
records a governance approval reference, such as
`governance_change:gcp_...`, `gcp_...`, or the approval event id. If the
attestation claims a governance approval and no matching
`governance_change.approved` event is found in the transition log, the bundle
is `incomplete`. Generic human-review strings are not treated as governance
approvals.

Observability references are exported from the records that already define the
run. The bundle includes the run's OpenTelemetry span projection handle,
checkpoint event ids, checkpoint payload refs, checkpoint side-effect keys,
action-attestation `runtime_ref` values, and explicit trace/span refs recorded
in action-attestation metadata. Missing external traces do not change the
verdict; this field is a review index over observability evidence, not a new
trace store.

Evidence hashes are also derived from existing records. The bundle includes
record-set digests for the run projection and each embedded evidence family,
action-attestation subject digests, `sha256:` input/output refs, known
formal-provider evidence digests when present in metadata, and role/mandate
contract hashes from the authority snapshot. These hashes make a bundle easier
to hand to another verifier or runtime without claiming that the hashes are a
new authorization gate.

## Export

From an installed package:

```bash
cognitive-firm-governed-run-bundle <run_id>
```

For a first-pass review:

```bash
cognitive-firm-governed-run-bundle <run_id> --summary
```

From a checkout:

```bash
PYTHONPATH=src python -m cognitive_firm.orchestration.artifact_bundle <run_id>
```

Use explicit log paths when exporting from a fixture, tenant workspace, or
runtime adapter smoke:

```bash
cognitive-firm-governed-run-bundle run_123 \
  --transition-log-path workspace/transitions.jsonl \
  --action-attestation-log-path workspace/action_attestations.jsonl \
  --formal-verification-log-path workspace/formal_verifications.jsonl \
  --human-work-log-path workspace/human_work.jsonl \
  --outcome-links-log-path workspace/outcome_links.jsonl \
  --accountability-cases-log-path workspace/accountability_cases.jsonl \
  --work-items-log-path workspace/work_items.jsonl \
  --leases-log-path workspace/leases.jsonl \
  --trusted-formal-provider alloy-adapter \
  --authority-root .
```

The command prints the full bundle JSON to stdout unless `--summary` is set.
Summary mode reports verdict, caveats, counts, linked record ids, and the
authority snapshot without expanding every row. It includes an
`evidence_hashes` count so reviewers can tell whether portable hash evidence
was exported.

Formal-verification provider trust is org policy. A verified provider row is
clean evidence only when `formal_verification/trusted_providers.json` recognizes
the provider and the row carries the evidence that policy requires. If the
policy requires signatures, the row must include
`metadata.provider_payload_signature_verified: true`, created during provider
payload ingestion against the installed provider key. The bundled
`leanmill-formal-verification` overlay installs LeanMill policy requiring signed,
re-runnable, and faithfulness-backed payload evidence. Other providers remain
supported, but verified rows from them produce an `incomplete` caveat unless the
org installs a trust policy for that provider or the exporter opts in with
`--trusted-formal-provider <provider>`. Refuted or invalid formal verification
rows fail the bundle regardless of provider.

Validate an existing bundle JSON before handing it to another system:

```bash
cognitive-firm-governed-run-bundle --validate-json bundle.json
```

Validation uses `schemas/governed-run-attestation.v1.schema.json` for the
portable shape and recomputes `bundle_digest` in Python. Passing validation
means the packet has the expected interchange shape and digest; it does not
upgrade the bundle's verdict or prove the run output correct.

## Authority Snapshot

The bundle includes a review snapshot for the run owner:

```json
{
  "owner_role": "role.manager",
  "status": "resolved",
  "role_ref": "org/roles/manager.yaml",
  "role_digest": "sha256:...",
  "mandate_ref": "org/mandates/manager_mandate.md",
  "mandate_digest": "sha256:...",
  "mandate_hash": "..."
}
```

`mandate_hash` reuses the same authorization-relevant digest used by the deploy
gate: role id, authorized and forbidden paths, authorized model/tool surfaces,
delegation/escalation, budget caps, and mandate text. If the role or mandate
file is not present, the snapshot reports that status but does not change the
bundle verdict. This keeps fixture and tenant-export bundles portable while
still preserving authority evidence when it exists.

## Verdict

The bundle verdict is intentionally conservative:

| Verdict | Meaning |
|---|---|
| `passed` | run completed, linked action attestations are verified or not-applicable, linked formal verifications are verified, required human receipts are present, linked outcome links have verdicts, and linked accountability cases are closed or risk-accepted |
| `incomplete` | evidence exists but at least one caveat remains |
| `failed` | the run failed/cancelled, a linked action attestation failed, a linked formal verification is refuted/invalid, or linked production work failed/dead-lettered |

The `caveats` list is part of the contract. It names unresolved evidence such
as unverified attestations, missing human receipts, outcome links awaiting
verdict, inconclusive formal verifications, accountability cases that are not
closed, referenced work items that are missing or incomplete, explicitly
referenced lease records that are missing, or referenced governance approvals
that are missing.

## Boundary

The bundle is an export over canonical state:

- it does not create authority;
- it does not authorize the run after the fact;
- it does not compute tenant metrics;
- it does not decide accountability outcomes;
- it does not make derived evidence hashes a new authorization source;
- it does not turn schema validation into a correctness proof;
- it does not replace OpenTelemetry or deployment observability storage;
- it does not replace run checkpoints, action attestations, formal
  verifications, work items, human work, outcome links, or accountability cases.

Use it when a reviewer, adopter, or external runtime integration needs one
compact packet for a governed run.
