# Audit Integrity

**Status:** lean T2-local audit seam.
**Module:** `cognitive_firm.orchestration.audit_integrity`
**Tests:** `tests/test_audit_integrity.py`

Audit integrity records a tamper-evident chain over a JSONL kernel log. It is
the smallest useful T2 audit step: an adopter can generate a manifest for
`transitions.jsonl`, `org/kernel_events/kernel_events.jsonl`, or another JSONL
state surface and later verify that rows were not changed, removed, inserted,
or reordered.

This is not a full enterprise signing service. It does not provide key
management, identity federation, or legal non-repudiation. The MVP provides
local chain verification, optional HMAC signatures, and external timestamp /
transparency-log references so teams can start testing audit discipline without
a platform rewrite.

## Manifest Shape

```json
{
  "schema_version": 1,
  "created_at_utc": "...",
  "source_ref": "cognitive_firm_workspace/transitions.jsonl",
  "source_row_count": 2,
  "external_timestamps": [
    {
      "provider_id": "rfc3161-tsa",
      "root_digest": "sha256:...",
      "timestamped_at_utc": "...",
      "proof_ref": "s3://audit/transitions.tsr",
      "proof_digest": "sha256:...",
      "metadata": {}
    }
  ],
  "entries": [
    {
      "index": 0,
      "event_id": "event-id-if-present",
      "row_digest": "sha256:...",
      "previous_chain_digest": null,
      "chain_digest": "sha256:...",
      "signature": "hmac-sha256:... or null",
      "signature_algorithm": "hmac-sha256 or null"
    }
  ]
}
```

Each entry hashes the canonical row and chains it to the previous entry. A
single row mutation changes the row digest and every subsequent chain digest.

The `external_timestamps` array records provider-owned proof references over
the manifest root digest. The public kernel does not choose a TSA,
transparency log, object store, or key manager. It records enough structure for
a tenant to bind the local manifest to an external proof.

## CLI

Default make targets:

```bash
make audit-manifest
make audit-verify
```

Override the source, manifest path, or local HMAC key when needed:

```bash
make audit-manifest \
  AUDIT_SOURCE=cognitive_firm_workspace/transitions.jsonl \
  AUDIT_MANIFEST=org/audit/transitions.manifest.json \
  AUDIT_SIGNING_KEY="$COGNITIVE_FIRM_AUDIT_HMAC_KEY"

make audit-verify \
  AUDIT_SOURCE=cognitive_firm_workspace/transitions.jsonl \
  AUDIT_MANIFEST=org/audit/transitions.manifest.json \
  AUDIT_SIGNING_KEY="$COGNITIVE_FIRM_AUDIT_HMAC_KEY"
```

Create a manifest:

```bash
python -m cognitive_firm.orchestration.audit_integrity create \
  --source cognitive_firm_workspace/transitions.jsonl \
  --manifest org/audit/transitions.manifest.json
```

Create a manifest with an HMAC key:

```bash
python -m cognitive_firm.orchestration.audit_integrity create \
  --source cognitive_firm_workspace/transitions.jsonl \
  --manifest org/audit/transitions.manifest.json \
  --signing-key "$COGNITIVE_FIRM_AUDIT_HMAC_KEY"
```

Verify:

```bash
python -m cognitive_firm.orchestration.audit_integrity verify \
  --source cognitive_firm_workspace/transitions.jsonl \
  --manifest org/audit/transitions.manifest.json \
  --signing-key "$COGNITIVE_FIRM_AUDIT_HMAC_KEY"
```

## Boundary

Use audit integrity to prove a local state log still matches a prior manifest.
Use action attestations to bind a specific action/artifact to producer and
runtime context. Use future signed audit/TSA work when a deployment needs
external proof beyond local HMAC verification.

For external timestamping, the stable digest to notarize is:

```python
from cognitive_firm.orchestration.audit_integrity import (
    attach_external_timestamp,
    manifest_root_digest,
)

root = manifest_root_digest(manifest)
# send root to a tenant-selected RFC 3161 TSA, transparency log, or notary
manifest = attach_external_timestamp(
    manifest,
    provider_id="rfc3161-tsa",
    proof_ref="s3://audit/transitions.tsr",
    proof_digest="sha256:...",
)
```
