# Governed Mutation Proofs

`mutation_proofs` defines a compact audit artifact for an approved state
mutation. It is a projection over existing records, not a new ledger and not an
authorization mechanism.

Use it when a script, adapter, demo, or service route needs to show that a
state change passed through the expected governance path:

```text
run
-> work_item
-> proposal
-> approval
-> mutation
-> attestation
-> learning
-> outcome
-> review
-> bundle
-> commit
```

The implementation lives in
`src/cognitive_firm/orchestration/mutation_proofs.py`.

## Contract

`build_governed_mutation_proof(...)` produces:

- `proof_kind`: always `governed_mutation_proof`;
- `proof_digest`: deterministic SHA-256 digest over the evidence chain and
  bundle/commit references;
- `evidence_carrier_refs`: optional refs to execution evidence that caused or
  supported the proposal, such as capability signals, learning-transition
  candidates, phase execution plans, protocol experiment reports, trace events,
  or attribution packets;
- `valid`: true only when the ordered chain is complete, the governed-run
  bundle passed validation, the bundle verdict is `passed`, the bundle digest
  is present, and the git commit reference is present;
- `validation_errors`: machine-readable reasons when the proof is incomplete.

`validate_governed_mutation_proof_payload(...)` verifies a serialized proof
payload and detects digest tampering.

The local kernel service exposes the same behavior:

```text
POST /kernel/mutation-proofs/build
POST /kernel/mutation-proofs/validate
```

These routes are read-only projections even though they use POST for structured
JSON request bodies.

## Boundary

The proof references existing source records:

- run checkpoints;
- durable work item;
- governance-change proposal and approval event;
- optional execution evidence carriers that support the proposal;
- applied file/artifact ref;
- action attestation;
- approved learning event;
- outcome link;
- routine review;
- governed-run attestation bundle;
- git commit.

It should not duplicate those records or become the system of record. If a
proof is invalid, the fix is to repair the missing underlying evidence or
approval path, not to edit the proof row by hand.

## Demo Use

`demos/self_evolving_org/run.py` uses this primitive to emit
`reports/self-evolving-org-mutation-proofs.json`. The script owns demo
orchestration. The proof shape and validation live in the kernel.

The self-evolving organization demo also performs a replay check before writing
its final report: it rebuilds each proof from persisted step facts through the
same read-only `/kernel/mutation-proofs/build` route and compares the rebuilt
payload with the saved proof row. The report records
`summary.mutation_proofs_reconstructed` and
`summary.mutation_proof_replay_valid` so reviewers can tell whether the proof
export is reproducible from the recorded chain inputs.
