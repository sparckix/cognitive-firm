# Formal Verification

**Status:** T1 filesystem primitive.
**Module:** `cognitive_firm.orchestration.formal_verification`
**Tests:** `tests/test_formal_verification.py`,
`tests/test_formal_provider_proof_pack_script.py`

Formal verification records are typed certificate rows from external formal
checkers. The checker may be Lean, SMT, Isabelle, Coq, Alloy, TLA+, or a
tenant-owned verifier. The kernel records the result; it does not run or trust a
checker process directly.

Provider trust is org policy, not a kernel import. The kernel accepts any
syntactically valid `formal-verification-provider/v1` payload as a record, but a
governed-run bundle treats a provider-backed `verified` row as clean evidence
only when the installed org policy recognizes that provider and the row carries
the evidence that policy requires.

## Why This Exists

Some organizational claims can be checked more sharply than an LLM judgment:

- a policy formalization matches labelled boundary cases;
- a schema invariant holds;
- a contract state machine rejects an illegal transition;
- an evidence chain has no missing digest;
- a workflow safety property has no counterexample.

Those checks should become durable kernel records that can be joined to a run,
reviewed, and failed closed when they refute the claim.

## Record Shape

```json
{
  "verification_id": "fver_<id>",
  "created_at_utc": "...",
  "formal_system": "lean | smt | isabelle | coq | alloy | tla | other",
  "verifier_ref": "lean:4.30.0",
  "property_class": "policy | schema | contract | evidence_chain | workflow_safety | math | other",
  "subject_ref": "policy://basel/cet1",
  "subject_digest": "sha256:...",
  "claim_ref": "claim://basel/cet1-threshold",
  "certificate_ref": "proofs/basel_threshold.lean#adequate_iff",
  "certificate_digest": "sha256:...",
  "verdict": "verified | refuted | inconclusive | invalid",
  "verification_summary": "Lean certificate checked labelled boundary cases.",
  "assumption_refs": [],
  "input_refs": [],
  "output_refs": [],
  "counterexample_ref": null,
  "action_attestation_id": "aat_<id>",
  "tenant_id": "optional",
  "project_id": "optional",
  "run_id": "optional",
  "metadata": {}
}
```

## Bundle Semantics

Formal-verification records are included in the governed-run attestation
bundle.

| Formal verdict | Bundle effect |
|---|---|
| `verified` | No caveat by itself |
| `refuted` | Bundle verdict becomes `failed` |
| `invalid` | Bundle verdict becomes `failed` |
| `inconclusive` | Bundle verdict becomes `incomplete` |

When `create_formal_verification(..., create_attestation=True)` is used, the
primitive also creates an action attestation whose `signature_ref` points to
the certificate and whose `transparency_ref` carries the certificate digest.

## Provider Payloads

External checkers can emit a provider-neutral payload instead of calling the
row writer field by field. The current schema version is
`formal-verification-provider/v1`.

```json
{
  "schema_version": "formal-verification-provider/v1",
  "provider": "leanmill",
  "formal_system": "lean",
  "verifier_ref": "leanmill:certify-demo@abc123",
  "property_class": "workflow_safety",
  "subject_ref": "workflow://release-checklist",
  "subject_digest": "sha256:...",
  "claim_ref": "claim://release-requires-review",
  "certificate_ref": "leanmill://certificates/release_requires_review",
  "certificate_digest": "sha256:...",
  "verdict": "verified",
  "verification_summary": "Provider emitted a checked workflow invariant.",
  "assumption_refs": [],
  "input_refs": [],
  "output_refs": [],
  "faithfulness_refs": ["leanmill://faithfulness/release_requires_review"],
  "checker_evidence_refs": ["leanmill://kernel-log/release_requires_review"],
  "metadata": {
    "provider_payload_signature": "ed25519:<signature-over-normalized-payload>"
  }
}
```

Provider evidence is retained in `metadata` and joined into the row's input or
output refs. A `refuted` verdict must include `counterexample_ref`; a `verified`
verdict must not.

Provider trust is deliberately separate from recording. Any syntactically valid
provider payload can be recorded. Trust is installed as org-owned policy under:

```text
formal_verification/trusted_providers.json
```

The bundled `leanmill-formal-verification` overlay installs a policy entry for
LeanMill that requires verified rows to carry:

- `metadata.provider_payload_signature`;
- a configured `public_key_pem` in the installed policy;
- non-empty `checker_evidence_refs`;
- non-empty `faithfulness_refs`.

The same overlay also installs an adapter manifest and conformance config under
`adapters/` and `adapter_conformance/`. Package lint validates that those files
agree on adapter id, protocol, required checks, and evidence paths:

```bash
cognitive-firm-distro lint leanmill-formal-verification
```

The same lint pass validates `formal_verification/trusted_providers.json`
itself: schema version, provider ids, boolean requirement fields, duplicate
providers, and either a configured public key or an explicit public-key
placeholder for overlays that require post-install key configuration.

Provider adapters can preflight their JSON without writing kernel state:

```bash
cognitive-firm-formal-verification validate-provider-payload \
  --payload-json leanmill_payload.json
```

With an org trust policy, the same command checks the signature and the
policy-required evidence refs that decide whether a later `verified` row can
count as clean governed-run evidence:

```bash
cognitive-firm-formal-verification validate-provider-payload \
  --payload-json leanmill_payload.json \
  --authority-root /path/to/org \
  --require-trusted-provider
```

This command does not append formal-verification rows or action attestations.
It prints the canonical provider-payload digest, trust requirements, signature
status, and any missing evidence. Use it in provider CI before handing payloads
to `create-from-provider-payload`.

Configure the provider key with the CLI; it validates the Ed25519 public key
and writes the org policy file:

```bash
cognitive-firm-formal-verification trust-provider \
  --provider leanmill \
  --public-key-file leanmill.pub \
  --public-key-ref leanmill://keys/current \
  --authority-root /path/to/org
```

The signature is over the normalized provider payload with signature metadata
removed. The Python helper is available to adapter authors:

```python
from cognitive_firm.orchestration.formal_verification import sign_provider_payload

payload["metadata"]["provider_payload_signature"] = sign_provider_payload(
    payload,
    private_key_pem=leanmill_private_key,
)
```

When `--authority-root` is supplied, ingestion verifies the signature against
the installed provider key and records `metadata.provider_payload_signature_verified`.
Governed-run bundle export requires that flag when the provider policy requires
signatures.

Other providers can be trusted for one export with the bundle CLI's
`--trusted-formal-provider` option, or by installing an org policy entry.

## CLI Examples

Create a certificate row from a provider:

```bash
cognitive-firm-formal-verification create \
  --formal-system lean \
  --verifier-ref lean:4.30.0 \
  --property-class policy \
  --subject-ref policy://basel/cet1 \
  --subject-digest sha256:... \
  --claim-ref claim://basel/cet1-threshold \
  --certificate-ref proofs/basel_threshold.lean#adequate_iff \
  --certificate-digest sha256:... \
  --verdict verified \
  --verification-summary "Lean certificate checked labelled boundary cases." \
  --run-id run_123
```

List records for a run:

```bash
cognitive-firm-formal-verification list --run-id run_123
```

Create a row from a provider payload:

```bash
cognitive-firm-formal-verification validate-provider-payload \
  --payload-json leanmill_payload.json \
  --authority-root /path/to/org \
  --require-trusted-provider

cognitive-firm-formal-verification create-from-provider-payload \
  --payload-json leanmill_payload.json \
  --authority-root /path/to/org
```

Kernel-service clients use the same ingestion boundary:

```text
POST /kernel/formal-verifications/provider-payload
GET  /kernel/formal-verifications?run_id=run_123
```

The service records the formal-verification row and, by default, the linked
action attestation. It does not run the provider or decide trust by provider
name; installed org policy and governed-run bundle export still decide whether
a provider-backed verified row is clean evidence or caveated.

No-cost end-to-end demo:

```bash
make formal-provider-bundle-demo
```

The demo creates one signed LeanMill-style provider payload that clears org
trust policy and one missing-evidence provider row that stays caveated in the
governed-run bundle.

## Formal Provider Proof Pack

```bash
make formal-provider-proof-pack
```

The target emits `formal_provider_proof_pack.v1`. It runs the deterministic
formal-provider demo in a temporary workspace, validates the bundled
`leanmill-formal-verification` manifest/config/trust-policy declarations, and
packages one operator receipt for adoption review.

The pack checks six things:

- the adapter manifest declares `family=formal_verification_provider` and
  `protocol=formal_verification_provider_payload`;
- the conformance config includes the signed-payload, forged-signature,
  checker-evidence, faithfulness-ref, and missing-trust caveat checks;
- the installed trust policy requires payload signatures, re-verification refs,
  and faithfulness refs;
- signed trusted evidence clears the governed-run bundle;
- missing provider evidence stays caveated as an incomplete bundle;
- the demo remains surface-neutral and no-external-call.

The proof pack is a reviewer handoff. It does not run LeanMill, install
provider code, approve provider trust, decide whether an informal claim was
faithfully formalized, or mutate durable kernel state.

## Research Anchor

- [Natural Language Specifications in Proof Assistants](https://arxiv.org/abs/2205.07811)
  is the reason this primitive separates certificate success from claim
  faithfulness: a proof assistant can check a formal claim even when the
  informal-to-formal translation is wrong.
- [Evaluating the Robustness of Proof Autoformalization in Lean 4](https://arxiv.org/abs/2606.14867)
  reinforces the same boundary for agent-era provers: proof autoformalizers can
  be brittle under paraphrase and local perturbation, so cognitive-firm records
  explicit `faithfulness_refs` and `checker_evidence_refs` instead of letting a
  verified certificate silently become org truth.

## Boundary

This primitive does not decide whether the natural-language claim was faithfully
formalized. A provider can add a faithfulness firewall, labelled examples,
round-trip checks, or independent review before emitting the certificate. The
kernel stores the certificate record and reports its verdict conservatively.

The provider binary is outside this package. A package/overlay may install the
trust policy and adapter instructions, but executable checker code should come
from the provider's normal distribution path or a separate integration package.
The high-assurance path is signed, re-runnable provider JSON: trust the installed
key and the referenced certificate artifacts, not a provider name alone.
