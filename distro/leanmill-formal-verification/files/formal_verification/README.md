# LeanMill Formal Verification Overlay

This overlay installs org-owned policy for accepting LeanMill
`formal-verification-provider/v1` payloads as governed-run evidence.

It does not install a LeanMill binary. The adapter can live in LeanMill, a
separate integration package, or a local deployment. The only contract is the
payload it emits:

```bash
cognitive-firm-formal-verification create-from-provider-payload \
  --payload-json leanmill_payload.json \
  --authority-root .
```

The installed policy requires verified LeanMill rows to include:

- `metadata.provider_payload_signature`
- non-empty `checker_evidence_refs`
- non-empty `faithfulness_refs`

Before using the overlay as trusted evidence, configure the LeanMill adapter's
public key:

```bash
cognitive-firm-formal-verification trust-provider \
  --provider leanmill \
  --public-key-file leanmill.pub \
  --public-key-ref leanmill://keys/current \
  --authority-root .
```

Without that key, governed-run bundles keep LeanMill rows incomplete instead of
trusting a provider name.

The governed-run bundle exporter reports an incomplete bundle when those
requirements are missing.

The overlay also installs `adapter_conformance/leanmill-formal-verification.json`.
That file declares the no-cost fixture and evidence paths an organization can
use before treating a LeanMill adapter as supported. Validate the package before
review:

```bash
cognitive-firm-distro lint leanmill-formal-verification
```
