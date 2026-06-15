# Testing Strategy

The test surface is organized like a kernel test suite: small primitive tests,
command-path selftests, fault fixtures, adapter conformance, and certificate
checks. Each layer asks a different question.

## Layers

| Layer | Question | Examples |
|---|---|---|
| Primitive tests | Does one kernel primitive enforce its local contract? | `tests/test_work_items.py`, `tests/test_formal_verification.py` |
| Property tests | Does a contract hold across generated inputs? | `tests/test_invariants_property_based.py` |
| Command-path selftests | Does the public command exercise the shipped path and expose the intended operator knobs? | `make a2h-command-conformance`, `make adoption-demo`, `make smoke-public`, `tests/test_self_evolving_make_targets.py` |
| Public claim discipline | Do public docs avoid production/compliance/enterprise overclaims and keep required caveats visible? | `make public-claims-check`, `tests/test_public_claims_check.py` |
| Release hygiene | Is private, generated, or local runtime state absent from tracked, staged, and unignored release state? | `make release-hygiene-check`, `tests/test_release_hygiene_check.py` |
| Release diff audit | Is the current broad worktree diff classified into reviewable buckets, with unknown paths visible? | `make release-diff-audit`, `tests/test_release_diff_audit.py` |
| Release candidate gate | Do the public deterministic suite, clean-container boot, and diff audit compose into one tag-candidate command? | `make release-candidate-check` |
| Governance fault fixtures | Does the kernel block, flag, or route expected bad states? | `make governance-failure-benchmark` |
| Decision-log replay | Can saved action-impact logs reconstruct a candidate proposal, evaluation, and review packet? | `make decision-log-replay-demo` |
| Field-pilot action-impact | Can a pilot folder carry measured action-impact rows and produce a review packet? | `make field-pilot-action-impact-demo` |
| Adapter conformance | Does an external runtime or app adapter preserve the kernel boundary? | `tests/test_adapter_conformance.py`, `scripts/app_integration_conformance.py` |
| Formal verification records | Can a certificate from Lean, SMT, Isabelle, Coq, Alloy, TLA+, or another checker be recorded and joined into a governed run? | `formal_verification`, governed-run bundle tests |
| Formal provider bundle | Does signed provider evidence clear the bundle while missing provider trust evidence stays caveated? | `make formal-provider-bundle-demo` |
| Production work execution | Does a governed run carry linked claimable work-item state, including completed, missing, and failed execution cases? | `tests/test_work_items.py`, governed-run bundle tests, `scripts/native_e2e_demo.py` |
| Evidence hashes | Does a governed-run packet carry portable record-set, subject, input/output, provider, and authority-contract hashes without making them a new source of authority? | governed-run bundle tests, `schemas/governed-run-attestation.v1.schema.json` |
| Observability references | Can runtime checkpoints and action attestations expose reviewable trace refs without making traces the source of truth? | `otel_export`, governed-run bundle tests |
| Interchange validation | Can a governed-run packet be validated by schema and digest before another runtime or provider consumes it? | `schemas/governed-run-attestation.v1.schema.json`, governed-run bundle tests |

## Release Checks

`make release-candidate-check` is the tag-candidate command. It composes the
deterministic public suite (`make smoke-public`), the clean-container boot
fixture (`make smoke-docker`), and the broad-diff classifier
(`make release-diff-audit`). Passing it means the public kernel paths still
boot, exercise their documented command surfaces, and expose the changed-path
review buckets; it does not replace a final human review of the diff, release
notes, and generated artifacts.

`make public-claims-check` is a narrow overclaim guard. It scans public docs for
phrases that would imply unsupported production, enterprise, legal, or
compliance guarantees, and it requires the main caveat surfaces to stay present.
It is intentionally not a prose style checker.

`make release-hygiene-check` protects the public/private boundary. It fails when
private tenant paths, local credentials, generated run state, or other
release-inappropriate files are tracked, staged, or unignored. Ignored local
files may still exist on disk during development; the check asks whether the
release state could accidentally carry them.

`make release-diff-audit` classifies the current changed paths into release
review buckets: kernel code, demos/examples, protocol docs, tests, operator
scripts, org examples, generated indexes, release gates, and repo config. It
fails on unclassified paths so a broad release diff cannot silently introduce a
new surface. It does not decide whether a change is good; it makes the review
surface explicit before staging.

## Governance Fault Fixtures

`make governance-failure-benchmark` is the default no-cost fault suite. It is
not a model-quality benchmark. It verifies that current kernel surfaces catch
or record failures an ordinary runtime trace may leave as prose:

- forbidden-path dispatch;
- failed action provenance;
- missing human receipt;
- unresolved outcome verdict;
- open accountability case;
- formal checker refutation;
- locally higher-reward actions blocked by externality and review-burden
  guardrails;
- weakly evidenced self-modification proposals blocked by governance-change
  evidence sufficiency.

The fixture is acceptable only when it uses shipped primitives and produces an
inspectable record. A fake score table is not enough.

## Decision-Log Replay

`make decision-log-replay-demo` checks the learned-policy path without an
online learner or external calls. It reconstructs a candidate route from
action-impact rows, evaluates it by conservative replay through the kernel
service, and packages the result for governance review through the same service
boundary.

The test is useful only if it keeps both sides:

- one candidate that clears support, reward, externality, and review-burden
  thresholds;
- one locally attractive candidate that is blocked because guardrails fail.

That split keeps the fixture from becoming a reward-only demo.

`make field-pilot-action-impact-demo` applies the same learned-policy path to
the field-pilot folder shape. It validates the pilot pack, requires
machine-readable action-impact rows, and emits a review packet rather than a
live policy change.

## Fixture Quality Bar

A governance fixture is worth keeping only if all of the following are true:

1. It targets an expected kernel property: authority, provenance, receipt,
   outcome, accountability, formal certificate, adapter boundary, or state
   integrity.
2. It uses the same public function or command path an adopter would use.
3. It has an explicit expected signal: blocked dispatch, failed verdict,
   incomplete verdict, caveat, quarantine, or typed record.
4. It fails if the kernel silently accepts the bad state.
5. It leaves a compact review artifact: JSON output, bundle summary, record id,
   or caveat.

This keeps the benchmark closer to a conformance and fault-injection suite than
to a demonstration-only script.

## A2H Command Conformance

`make a2h-command-conformance` checks the A2H receipt rule through the public
`human_work` CLI. It creates an agent-requested human-work session, moves it to
`completed` without a receipt, verifies that `integrated` is rejected, then
integrates successfully only when a receipt is supplied. The fixture also reads
the final session through `list --resource` so the adapter-facing object shape
is part of the command path.

Primitive tests also cover structured human-work receipts. A receipt-required
session can be integrated only after a bounded receipt records the actor,
claim, receipt type/ref, subject refs, and artifact refs that make the claim
reviewable.

## Formal Verification

Formal verification is provider-agnostic. The kernel does not assume Lean,
SMT, Isabelle, Coq, Alloy, or TLA+ as the only backend. It records:

- the subject and digest being checked;
- the claim being checked;
- the checker and formal system;
- the certificate and certificate digest;
- the verdict: `verified`, `refuted`, `inconclusive`, or `invalid`;
- assumptions, inputs, outputs, and optional counterexample reference.

Provider-specific engines can sit outside the kernel. The kernel-owned fact is
the formal-verification record and its join into the governed-run attestation
bundle.

`make formal-provider-bundle-demo` exercises the provider boundary end to end:
signed provider payload, installed trust policy, formal-verification row, action
attestation, and governed-run bundle. It also keeps the negative case: a
provider-backed row without required trust evidence remains an incomplete
bundle, not clean evidence.

## Costly Fixtures

Costly fixtures should be opt-in. Add one only when it answers a question that
the deterministic suite cannot answer, such as:

- whether a live runtime adapter preserves identity across resume;
- whether an external-system receipt can be joined to an action attestation;
- whether a formal-checker service returns stable certificate digests and
  counterexample references;
- whether a human-review surface records receipts before resume.

The default public smoke should remain deterministic and credential-free.
