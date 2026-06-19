# Changelog

## v0.4.0 - 2026-06-18

Highlights:

- New service surfaces cover bounded human-work receipts, human-work pressure
  groups, learning context projection, learning-use receipts, provenance
  timelines/graphs, and governance-change request templates.
- The self-evolving organization demo now carries workload-probe summaries as
  first-class planner and reviewer evidence refs. `score_totals` exposes
  firm-visible capability scores through
  `reports/workload-probes/workload-probe-summary.json`; `withheld` explicitly
  blocks proposals from citing operator-only scores, making score-feedback vs.
  no-feedback comparisons easier to audit.
- Governed-run operator summaries can now include `learning_closure` rows, a
  read-only projection that joins approved learning, learning-use receipts,
  changed context refs, future replay cues, outcome reviews, routine reviews,
  and evidence refs. The self-evolving org runbook uses it so the v0.4 demo
  answers the compounding-learning audit without adding memory, scheduling, or
  workflow state.
- The self-evolving organization demo now writes reusable provenance handoff
  reports for accepted mutation runs under `reports/provenance/` through the
  same read-only `GET /kernel/provenance-report?run_id=...` route exposed to
  userland. The bespoke demo timeline remains a visualization aid, not a
  parallel provenance model.
- The same demo now writes reusable governance-change review handoff packets
  for accepted and blocked proposals under `reports/proposals/` through
  `GET /kernel/governance-changes/{proposal_id}/review-packet`, exercising the
  v0.4 proposal-review UX surface without bypassing proposal status,
  invariants, provenance, or decision routes.
- Provenance reports and governance-change review packets now include a
  read-only `follow_through` summary over selected records. Proposal packets can
  distinguish proposal-only evidence, observed decisions, and closed-loop
  evidence from outcome links, routine reviews, or learning-use receipts without
  adding a workflow runner or proposal lifecycle.
- The optional Orbit provenance pane now consumes the same portable provenance
  report and renders the report-derived follow-through status next to the
  timeline, keeping visualization surfaces downstream of reusable kernel
  projections.
- `scripts/kernel_service_smoke.py` now proves the provenance follow-through
  contract in the service-level adoption path: it seeds a measured outcome,
  routine review, approved learning event, and learning-use receipt that cite
  the smoke run, then requires the exported provenance report to classify the
  run as `closed_loop_observed`.
- The same demo now exercises the v0.4 learning-context seam end to end: after
  outcome and routine-review records exist, each accepted mutation obtains a
  future work-discovery context packet, verifies it through
  `POST /kernel/work-discovery/context-packet/verify`, and records a
  learning-use receipt tied to that verified packet. This keeps the demo current
  with the kernel primitives without adding a memory store, scheduler, or BPM
  layer.
- Self-evolving demo reports now expose aggregate v0.4 evidence counters for
  learning-use receipts, context packets, verified context packets, provenance
  reports, proposal review packets, and proposal follow-through with closed-loop
  evidence. The optional
  `bounded_live_agent_run` adoption row now expects those counters when a
  reviewer attaches a live self-evolving report, so thin live-agent JSON is
  marked partial and zero-count live reports fail that optional row and block
  the on-ramp collector from reporting `ok: true` instead of looking equally
  reviewable.
- Approved learning events can shape future work through an explicit pre-work
  context packet and a later learning-use receipt. The packet is a read-only
  projection over matching learning events, outcome links, routine-review
  state, and work-discovery candidates; applying or ignoring the learning
  remains an auditable event rather than hidden memory.
- One approved learning unit can now be inspected through a read-only
  compounding-loop projection (`GET /kernel/learning-events/{id}/loop` and
  `cognitive-firm-userland learning-loop`) joining context-packet refs,
  encounters, outcome links, routine reviews, overdue reviews, and evidence
  refs.
- Captured context packets can now be verified without writing state through
  `POST /kernel/work-discovery/context-packet/verify` and
  `cognitive-firm-userland context-packet-verify`, which recompute the digest
  from the embedded basis and check the `ctx_...` id without replaying logs or
  creating a memory store.
- Learning-use receipts can optionally submit the captured `context_packet`
  object (`cognitive-firm-userland learning-use --context-packet-json ...`);
  the service verifies the packet and rejects the receipt unless the packet
  basis contains the target learning event, then records a verification marker
  and digest in the encounter metadata.
- Scripts and adapters can now reuse
  `verify_learning_event_context_packet_use(...)` for the same read-only
  packet-integrity and learning-event-basis check without replaying logs,
  authorizing work, or creating a memory store.
- `GET /kernel/learning-events/{id}/loop` and `learning-loop` now surface
  verified context-packet refs separately from bare packet refs.
- `governed_run_recipes` now includes
  `build_governed_action_composition_packet(...)`, a read-only traceability
  matrix for first-gated-action and learning-loop proof chains. Adoption
  readiness packets embed these matrices so green commands cannot hide missing
  authority, work, human-work, attestation, outcome, bundle, context-packet, or
  learning-use links. The same checker is exposed through read-only
  `POST /kernel/governed-action-composition` and
  `cognitive-firm-userland composition-packet` for adopter-built surfaces and
  terminal preflights.
- Adoption readiness rows now report expected, present, and missing evidence
  fields plus `evidence_quality`. A required check that passes command
  expectations but omits expected evidence fields is a review-quality blocker,
  so a green command cannot become adoption-ready with a thin payload.
- Adoption readiness packets now include a read-only `reviewer_path` section
  derived from command-surface guidance. The Markdown handoff shows the first
  serious review sequence (`make smoke-public`, `make adoption-onramp-packet`,
  `make adoption-readiness-packet`) without becoming a runner, scheduler, or
  workflow plan.
- `make adoption-onramp-packet` now runs a fixed, no-cost first-review proof
  set with per-command timeouts, captures observed JSON outputs plus command
  logs, and renders `adoption-readiness-packet.json` /
  `adoption-readiness-packet.md`. It can also cite externally produced JSON
  results with `--result CHECK_ID=path`, so bounded live-agent or release-gate
  proof enters as an artifact instead of being run by the collector. The
  reusable adoption-readiness packet also recognizes adapter-policy preview,
  formal-provider proof-pack, and runtime-adapter proof-pack outputs as
  optional adoption evidence.
- `make adoption-readiness-packet` now re-renders the latest collected
  adoption-on-ramp packet when one exists, while preserving the fresh-clone
  expected/missing projection when no on-ramp run has been collected. The
  script remains read-only: it does not run commands, approve release
  readiness, or write kernel state.
- `make adoption-onramp-replay` now stages the public repo surface into an
  isolated copy, excludes `internal/`, local run state, virtualenvs, and `.env`,
  then runs the core adoption-on-ramp collector from that copy. This gives
  release review a clone-replayable adoption proof without adding a scheduler,
  workflow engine, external-agent runner, or durable-state writer.
- `make adoption-onramp-full-replay` runs that same clean-copy replay with the
  full no-cost collector, including adapter-policy preview, formal-provider
  proof-pack, runtime-adapter proof-pack, agent-fleet, and field-pilot evidence
  rows. It is a portability proof for the default on-ramp, not a new runner or
  release approver.
- `make smoke-public` now includes `make adoption-onramp-full-replay`, so the
  tag-candidate gate proves the stronger clean-copy adoption path instead of
  leaving that portability check as optional release evidence.
- `make agent-fleet-review-packet` now gives the agent-fleet audit wedge a
  one-command persistent review path, writing the local/subscription agent
  invocation receipt, governed-run bundle, operator-burden summary, and
  Markdown runbook under `.cognitive-firm-runs/agent-fleet-audit` without
  calling an external runtime.
- `make langgraph-adapter-policy-preview` now proves the bundled
  `langgraph-runtime-adapter` policy overlay previews as authority-neutral
  against a temporary starter org while validating the adapter manifest and
  conformance declaration. It does not install LangGraph, execute a graph,
  apply the overlay, or write a governance proposal.
- The terminal userland gained practical operator verbs for `proposal`,
  `proposal-packet`, `proposal-template`, `proposal-from-candidate`,
  `work-context`, `context-packet-verify`, `composition-packet`,
  `human-pressure`,
  `learning-candidates`, `receipt`, `learning-use`, `learning-loop`, and
  `timeline` / `graph`, all backed by kernel service routes rather than direct
  JSONL writes.
- `GET /kernel/command-surface` and `cognitive-firm-userland commands` now
  expose read-only `operator_guidance` for the first serious review path.
  Querying `first serious review` returns `make smoke-public`, `make
  adoption-onramp-packet`, and `make adoption-readiness-packet` as ranked
  metadata, not as a runner, scheduler, or new workflow layer.
- `GET /kernel/operator-path?path_id=first_review` and
  `cognitive-firm-userland operator-path first_review` now expose that named
  path directly for adopter-built dashboards and custom visualizations that do
  not want fuzzy command matching. The path now carries purpose/use-when text
  plus explicit `not_a` boundaries so surfaces can present it as review
  guidance without implying command execution or workflow ownership.
- A2H human-work pressure now has a direct observer-only service/userland view
  (`GET /kernel/human-work-pressure` and `cognitive-firm-userland
  human-pressure`) over existing human-work sessions, exposing repeated
  role/bottleneck pressure without automating or rerouting the work. Tenant and
  project selectors scope sessions before pressure is summarized.
- Human-speed envelope guidance is now executable through
  `GET /kernel/human-speed-envelope` and `cognitive-firm-userland
  speed-envelope`. The read-only `human_speed_envelope.v1` projection maps
  risk tier, bottleneck class, deployment class, reversibility, external side
  effects, repeated-similar work, private context, harm, and accepted residual
  risk to agent speed, sampled review, batched human review, gate-before-action,
  or accountable closure without authorizing, dispatching, scheduling, sampling,
  or approving anything. The kernel-service smoke now asserts this route and
  includes `human_speed_envelope_counts` in its adoption evidence JSON.
- Field-pilot action-impact evidence now carries a
  `human_speed_field_pilot_summary.v1` read model. The no-cost field-pilot demo
  writes `human-speed-envelope-summary.json` and reports whether observed speed
  choices matched the envelope, whether sampled-review coverage met the
  expected rate, and whether harm, rework, hidden burden, or open residual risk
  requires review.
- The human-work CLI now has a read-only `followup` view for A2H sessions that
  are ready for role-office integration. The `a2h-command-conformance` fixture
  now proves both ready-for-agent follow-up visibility and
  receipt-before-integration through the public command path.
- Saga compensation now has a tiny command-path surface
  (`python -m cognitive_firm.orchestration.saga_compensation ...`) plus
  `make saga-command-conformance`, proving that a non-terminal obligation
  cannot trigger compensation, a terminal child failure emits a compensation
  request for a fulfilled ancestor, the active saga is visible, and the active
  view clears only after compensation fulfillment.
- `make a2a-h2a-command-conformance` now proves the role-to-role/human-work
  seam through existing public paths: the kernel-service A2A route creates a
  handoff obligation, rejects `pending -> fulfilled`, exposes
  `blocked_input`, links a bounded A2H human-work session by obligation id,
  enforces receipt-before-integration, and closes the A2A obligation only
  after the human receipt is integrated. It is a fixed conformance trace, not a
  scheduler or runtime adapter.
- `make runtime-interrupt-command-conformance` now proves the external-runtime
  interrupt seam through the public `runtime_adapters` CLI: pre-start
  checkpoints and incomplete interrupts are rejected, `started` is idempotent,
  a valid interrupt pauses the run, creates one receipt-required A2H
  human-work request, preserves the runtime resume ref, and reuses that
  request on interrupt replay. It is an adapter-boundary proof, not runtime
  execution or workflow ownership.
- `make a2a-delegation-command-conformance` now proves standalone A2A
  delegation/handoff invariants through the kernel-service routes:
  unauthorized role edges fail closed without writing message envelopes, linked
  handoffs start as pending obligations, envelope acknowledgement does not
  accept work, illegal direct completion is blocked, lifecycle events stay
  ordered, non-obligating `inform` messages cannot be treated as work, and
  thread/depth guards reject unbounded chains. It is role-policy conformance,
  not route synthesis or scheduling.
- `make runtime-adapter-proof-pack` now emits
  `runtime_adapter_proof_pack.v1`, validating the bundled LangGraph adapter
  manifest/config pair and comparing the native kernel demo with the
  LangGraph-style runtime demo against one governed-run summary contract. It
  proves substrate-equivalent authority, human-work, attestation, outcome,
  accountability, and bundle evidence while leaving graph execution and resume
  semantics outside the kernel.
- `make formal-provider-proof-pack` now emits
  `formal_provider_proof_pack.v1`, validating the bundled LeanMill
  formal-provider manifest/config/trust-policy declarations and packaging the
  signed-provider and missing-evidence governed-run bundle paths as one
  adoption receipt. It proves provider evidence can enter the kernel as signed,
  reviewable rows without running LeanMill, approving provider trust, or
  treating certificate success as mandate truth.
- Repeated A2H pressure now also feeds observer-only learning-transition
  candidates through `GET /kernel/learning-transition-candidates?source=human_work`
  and `cognitive-firm-userland learning-candidates --source human_work`, with
  source refs back to human-work sessions and no automatic routing, closure, or
  policy mutation.
- The routed L1 attention feed can now be compiled into observer-only
  learning-transition candidates with
  `GET /kernel/learning-transition-candidates?source=attention` and
  `cognitive-firm-userland learning-candidates --source attention`, surfacing
  unrouted signals, stale actionable signals, and repeated role/signal pressure
  without rerouting, paging, assigning, closing, or scheduling work.
- Repeated warning-level damage signals of one kind, or any critical damage
  signal, now compile into observer-only learning-transition candidates through
  the org-surface path. The candidate can ask for mandate, accountability,
  route-policy, routine-retirement, or accepted-risk review without
  quarantining, blocking, rerouting, or creating an accountability case.
- The decision-log replay demo now closes its proof chain with run checkpoints,
  a verified action attestation, an outcome verdict, and a validated
  governed-run attestation bundle over the replayed policy-promotion packets.
  It still only produces review evidence; it does not change live routing
  policy.
- Governed-run operator runbooks can now include an
  `operator_burden_projection.v1` section over existing bundle counts,
  human-work pressure, and action-impact review-burden summaries. The projection
  estimates human touchpoints and review load without assigning work,
  scheduling review, approving policy, or optimizing routes.
- Agent-fleet audit evidence now carries
  `operator_burden_field_pilot_summary.v1`. The no-cost demo reports the
  compact summary and can write `operator-burden-field-pilot-summary.json`,
  comparing baseline and pilot human touchpoints, coordination minutes, rework,
  missing receipts, hidden burden, and projection undercount without assigning
  work or optimizing routes.
- `scripts/field_pilot_operator_burden_compile.py` now compiles measured
  `.csv`, `.json`, or `.jsonl` burden rows into the same
  `operator-burden-field-pilot-summary.json` artifact for real pilot folders.
- Learning-transition candidates can now be promoted from userland with
  `cognitive-firm-userland proposal-from-candidate`, a thin wrapper over
  `POST /kernel/learning-transition-candidates/{id}/governance-change` that
  preserves candidate source refs while leaving the proposal evidence gate in
  force.
- Governance proposal review now has a reusable read-only projection
  (`GET /kernel/governance-changes?view=review`) so first-party or
  adopter-built surfaces can show review state, evidence gaps, invariant gaps,
  and the canonical decision route without reimplementing proposal logic.
- One proposal can now be exported as a portable review packet
  (`GET /kernel/governance-changes/{id}/review-packet` and
  `cognitive-firm-userland proposal-packet`), combining proposal review facts,
  evidence refs, invariant rows, selected provenance, review questions, and a
  Markdown handoff without approving or mutating the proposal.
- Governance proposal review now surfaces read-only formal proof obligations
  for high-risk policy/provider/adapter-shaped changes, separating
  `formal_verification:*` evidence refs from generic evidence without running a
  checker or turning proofs into automatic approvals.
- Authority-domain validation now reuses one role-graph helper for package boot
  checks and `cognitive-firm-authority-domains validate`, proving that
  non-authority `escalates_to` chains terminate at an authority role without
  introducing IAM or workflow state.
- Command-surface suggestions now expose projection-only authority effects for
  selected governance-sensitive commands. `GET /kernel/command-surface` and
  `cognitive-firm-userland commands` report declared `decision_class` /
  `resource_class` effects and resolve them against authority domains or the
  T1 single-authority fallback without executing, scheduling, or approving
  commands; unavailable authority-domain configuration is reported as
  `not_evaluated` rather than silently treated as fallback.
- Residual-right holder lookup now returns a `holder_resolution` read model.
  Explicit residual-right assignments remain canonical; when one is missing,
  the service can project the accountable authority-domain role as
  `source: "authority_domain"` / `projection_only: true` without authorizing a
  residual decision or creating workflow state. The same shape is available
  from `python -m cognitive_firm.orchestration.decision_rights holder
  --resolve-authority`.
- Adoption proof outputs can now be packaged as a read-only readiness handoff
  with `make adoption-readiness-packet` or
  `scripts/adoption_readiness_packet.py`, marking observed, missing, and
  failed checks over existing smokes/demos without running commands, approving
  release readiness, or writing kernel state.
- The shortest deterministic proof scripts now support `--output` evidence
  files: `scripts/native_e2e_demo.py --output ...`,
  `scripts/kernel_service_smoke.py --output ...`,
  `scripts/learning_loop_walkthrough.py --output ...`,
  `scripts/agent_fleet_audit_demo.py --output ...`, and
  `scripts/field_pilot_action_impact_demo.py --output ...` can feed the
  readiness packet directly while still printing JSON to stdout.
- Command discovery is now exposed through `GET /kernel/command-surface` and
  `cognitive-firm-userland commands`, returning read-only suggestions for
  known Make targets and Python scripts without executing or scheduling them.
- A read-only provenance timeline now joins run/checkpoint events, action
  attestations, human-work sessions and receipts, governance changes,
  approvals, outcome links, routine reviews, approved learning events, and
  learning-use receipts for a run, ref, tenant, or project scope.
- A projection-only provenance graph (`GET /kernel/provenance-graph` and
  `cognitive-firm-userland graph`) exposes the same selected records as
  event/ref nodes and auditable mention edges for adopter-built lineage views.
- A portable provenance handoff report (`GET /kernel/provenance-report` and
  `cognitive-firm-userland provenance-report`) now summarizes timeline/graph
  coverage, high-signal refs, caveats, review questions, and a Markdown export
  without creating a second workflow store.
- Orbit has a first-party read-only provenance timeline pane over the same
  kernel service route. It is an example visualization surface over the
  abstract userland/API boundary, not a new source of truth.

## v0.3.0 - 2026-06-14

This release makes the kernel materially more executable while
keeping runtime orchestration, tenant policy, and workflow/BPM concerns outside
the reusable core.

Highlights:

- Release gates now include public smoke, clean-container smoke, release
  hygiene, public-claim discipline, and broad diff classification.
- Self-evolving organization proof paths now emit readable report JSON,
  operator runbooks, HTML timelines, mutation proofs, future replay proofs,
  planner receipts, and git receipts under gitignored run directories.
- A bounded live Codex planner proof was run outside the deterministic release
  gate: one subscription/local planner call, one governed approval, one valid
  mutation proof, and one replay-valid proof chain.
- Kernel service adoption was hardened so adopter-facing demos route durable
  rows through service routes instead of writing primitive state directly where
  a route exists.
- New service surfaces cover policy decisions, formal-verification provider
  payload ingestion/listing, and accountability-case status updates.
- First-party governance carriers and thin recipes expanded for agent runtime
  invocation receipts, capability signals, decision aggregation,
  multi-agent trace attribution, mutation proofs, phase execution, protocol
  experiments, and governed-run request shaping.
- Deterministic examples now cover agent-fleet audit trail, decision-log
  replay, field-pilot action impact, formal provider bundles, LangGraph-style
  governance projection, multi-actor authority, and governance failure
  fixtures.
- Public docs clarify the T1/T2 boundary: cognitive-firm governs authority,
  evidence, receipts, outcomes, learning, and bounded mutation around runtimes;
  it is not a replacement agent runtime, BPM product, compliance
  certification, or tenant strategy store.
- Public schema and dashboard shell text were cleaned of legacy
  project-specific naming so the reusable kernel stays tenant-neutral.

Verification before release:

- `make smoke-public`
- `make smoke-docker`
- `make release-diff-audit`

## v0.2.0 - 2026-06-11

This release turns the repository from a protocol-heavy kernel into
a more executable governance surface.

Highlights:

- Governed-run attestation bundles with replayable evidence, caveats, formal
  verification records, action attestations, human-work receipts, outcome
  links, work items, leases, and accountability cases.
- Kernel service routes for runs, operating units, work items, learning events,
  governance-change proposals, outcome links, routine reviews, resource
  allocation, and residual decision rights.
- Governance-change proposals now require structural evidence sufficiency, can
  be exposed as resource envelopes, and can be proposed/approved through the
  service boundary.
- Runtime adapter proof paths for native runs and LangGraph-style projection,
  plus adapter conformance fixtures and package entry points.
- Distribution hardening for starter-firm installs, overlay preview, authority
  diffs, governed install proposals, package signing, lockfiles, rollback, and
  clean-container smoke.
- Action-impact and offline policy-promotion tooling, including fixtures that
  reject locally positive policies when externality or review-burden guardrails
  fail.
- Formal-verification provider payload support with trust policy checks and
  governed-run bundle integration.
- Public examples and smoke scripts for adoption, failure benchmarks, decision
  log replay, field-pilot action impact, formal-provider bundles, A2H command
  conformance, and multi-actor authority.

Verification before release:

- `make smoke-public`
- `make smoke-docker`

## v0.1.0 - Initial release

Initial public release of the reusable cognitive-firm governance kernel.
