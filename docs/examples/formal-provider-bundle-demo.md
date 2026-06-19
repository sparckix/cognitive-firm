# Formal Provider Bundle Demo

This no-cost demo shows how an external formal-verification provider becomes
governed-run evidence without making the provider part of the kernel.

Run:

```bash
make formal-provider-bundle-demo
```

The fixture simulates a LeanMill-style provider payload:

```text
signed provider payload
-> formal-verification row
-> action attestation
-> governed-run attestation bundle
```

It produces two runs:

- a trusted provider path where the payload is signed, the org has the provider
  public key, and the row includes checker evidence and faithfulness refs. The
  governed-run bundle passes;
- a missing-evidence path where a provider-backed `verified` row exists, but
  the installed org policy requires signature, checker evidence, and
  faithfulness refs that are absent. The bundle is incomplete and reports the
  trust caveat.

This is the intended provider boundary. A formal checker may live in LeanMill,
SMT, Isabelle, Coq, Alloy, TLA+, or another package. cognitive-firm records the
certificate row, checks org trust policy, and exports bundle evidence. It does
not import or run the checker.

For adoption review, run:

```bash
make formal-provider-proof-pack
```

That command emits `formal_provider_proof_pack.v1`: the same signed-provider
and missing-evidence paths plus the bundled manifest, conformance config, and
trust-policy declarations.
