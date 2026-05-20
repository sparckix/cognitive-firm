# Action Attestation

**Status:** T1 filesystem adapter.
**Module:** `cognitive_firm.orchestration.action_attestation`
**Tests:** `tests/test_action_attestation.py`

Action attestations are compact provenance rows for machine-side work: agent
actions, runtime events, tool calls, prompts, datasets, and generated
artifacts.

They are the counterpart to human work receipts. A human work session records
bounded human work and, when appropriate, a bounded human claim. An action
attestation records what an agent/runtime/tool produced, under which policy,
from which inputs, with which digest and verification state.

## Why This Exists

The kernel should not rely on prose such as "the agent updated the file" or
"the tool call succeeded." When an action matters, the organization needs a
small reviewable row:

- who or what produced the subject;
- what kind of subject it is;
- how to identify it;
- which inputs and outputs were involved;
- which runtime/tool/policy was in force;
- whether the subject has been verified;
- where signatures or transparency records live if a tenant enables them.

This is intentionally narrower than a full supply-chain system. T1 records are
local filesystem rows. T2 tenants can attach signatures, transparency-log
references, and stricter verification policy.

## Record Shape

```json
{
  "attestation_id": "aat_<id>",
  "created_at_utc": "...",
  "subject_kind": "artifact | action | runtime_event | tool_call | dataset | prompt",
  "subject_ref": "workspace/report.md",
  "subject_digest": "sha256:...",
  "producer": "role.researcher",
  "action_type": "write_artifact",
  "runtime_ref": "codex-cli",
  "tool_ref": "apply_patch",
  "policy_ref": "mandates/researcher.yaml",
  "input_refs": ["workspace/source.md"],
  "output_refs": ["workspace/report.md"],
  "signature_ref": null,
  "transparency_ref": null,
  "verification_status": "unverified | verified | failed | not_applicable",
  "verification_summary": null,
  "tenant_id": "optional",
  "project_id": "optional",
  "run_id": "optional",
  "metadata": {}
}
```

## CLI Examples

Digest a subject:

```bash
python -m cognitive_firm.orchestration.action_attestation digest-file workspace/report.md
```

Create an attestation:

```bash
python -m cognitive_firm.orchestration.action_attestation create \
  --subject-kind artifact \
  --subject-ref workspace/report.md \
  --subject-digest sha256:... \
  --producer role.researcher \
  --action-type write_artifact \
  --runtime-ref codex-cli \
  --tool-ref apply_patch \
  --policy-ref org/mandates/researcher.yaml \
  --input-ref workspace/source.md \
  --output-ref workspace/report.md
```

List attestations needing verification:

```bash
python -m cognitive_firm.orchestration.action_attestation list \
  --verification-status unverified
```

## Boundary

Action attestations do not prove correctness. They prove that a specific
subject is tied to a specific producer, runtime/tool context, digest, and
verification state.

For human work, use `HumanWorkSession`. For non-digitized human contact with
the world, use a human work session with bounded receipt fields rather than
forcing private work into machine-style provenance.
