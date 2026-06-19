# Governed Run Recipes

`governed_run_recipes` provides thin client-side composition helpers for common
governed paths. Recipes do not authorize work, approve proposals, mutate files,
write kernel rows, or build proofs. They shape request bodies and artifact refs
so demos, adapters, and starter overlays can call the same kernel service routes
without duplicating lifecycle glue.

Current helper surface:

- `BoundedRunControlInput`: operator-visible bounds for a governed run.
- `build_bounded_run_controls`: produces a normalized control snapshot with
  consumed/remaining budget, simulation-clock state, and a deterministic stop
  receipt when the run ends through a budget limit or stop file.
- `ExecutionEvidenceRouteInput`: an adapter-observed execution issue such as
  abstention, capability gap, verifier block, unavailable tool, or exhausted
  budget.
- `build_execution_evidence_route_packet`: produces a standard route packet
  with service-call shapes for recording a capability signal, routing it,
  listing projected learning-transition candidates, and optionally preparing a
  governance-change request from the candidate.
- `GovernedRunOperatorSummaryInput`: the compact post-run inspection input for
  artifacts, commands, bounded controls, bundle summaries, mutation proofs,
  execution signals, learning candidates, phase plans, learning-closure rows,
  and optional operator-burden evidence.
- `build_governed_run_operator_summary`: produces
  `governed_run_operator_summary.v1`, a stable human/operator review projection
  for demos and adapters. When learning-closure rows are provided, it shows the
  approved learning event, changed context ref, future replay/use cue, outcome
  review, routine review, and evidence refs without creating memory or
  scheduling review. When `operator_burden` is provided, it also emits an
  `operator_burden_projection.v1` section over existing bundle counts,
  human-work pressure groups, and action-impact review-burden summaries.
- `GovernedActionCompositionInput`: observed output from one already-run demo,
  adapter, or operator command.
- `build_governed_action_composition_packet`: produces
  `governed_action_composition_packet.v1`, a read-only traceability matrix over
  the expected authority, run, work, human-work, attestation, outcome, bundle,
  and learning-use evidence links. It reports missing composition links without
  executing commands, calling service routes, scheduling work, approving
  governance, or verifying row existence.
- `summarize_operator_burden_field_pilot`: produces
  `operator_burden_field_pilot_summary.v1`, a read-only pilot measurement over
  baseline and pilot rows. It compares observed human touchpoints,
  coordination minutes, rework, missing receipts, hidden-burden reports, and
  projection undercount without assigning work or optimizing routing.
- `render_governed_run_operator_summary_markdown`: renders that projection as
  a concise runbook.
- `GovernedMutationRecipeInput`: the references required for a governed
  mutation proof request.
- `GovernedMutationEvidenceInput`: common refs used by a governed mutation
  lifecycle, including A2A, reviewer evidence, planner receipts, and trace
  events.
- `PredictedMutationOutcomeInput`: context for opening an outcome link from a
  governance proposal that carries a typed predicted effect.
- `build_predicted_mutation_outcome_link_request`: produces the
  `POST /kernel/outcome-links` body that carries the proposal's prediction into
  outcome-link measurement. Service clients can also use
  `POST /kernel/governance-changes/{proposal_id}/outcome-link` after approval
  when they want the kernel service to perform this composition.
- `PredictedMutationReversalReviewInput`: context for scheduling review after a
  predicted mutation receives a failed prediction review.
- `build_predicted_mutation_reversal_review_request`: produces the
  `POST /kernel/routine-reviews` body for a reversal-candidate review. It does
  not reverse the mutation.
- `build_governed_mutation_evidence_pack`: produces aligned work-completion
  artifact refs and mutation-proof evidence refs from one typed input.
- `validate_governed_mutation_evidence_pack`: preflights the pack shape and
  required evidence-ref prefixes and work-completion artifact kinds before a
  client calls work-completion or proof-build routes. It does not verify that
  referenced kernel rows exist.
- `governed_mutation_evidence_requirements`: returns the standard validation
  profile for governed mutation clients. It keeps adapters from hand-maintaining
  separate evidence and artifact checklists.
- `build_mutation_proof_request`: produces the body for
  `POST /kernel/mutation-proofs/build`.
- `governed_work_completion_artifact_refs`: produces common work-completion
  artifact refs for governance change, learning event, attestation, run, phase
  execution, A2A, reviewer evidence, decision aggregation, planner receipt,
  and trace evidence.
- `governed_mutation_evidence_refs`: produces canonical evidence refs for a
  governed structural mutation, including optional reviewer attestations or
  reviewer artifacts when live reviewer offices are used.

Recommended preflight:

```python
pack = build_governed_mutation_evidence_pack(evidence_input)
requirements = governed_mutation_evidence_requirements(
    require_reviewer_evidence=bool(reviewer_evidence_refs),
)
validation = validate_governed_mutation_evidence_pack(
    pack,
    required_evidence_prefixes=requirements["required_evidence_prefixes"],
    required_artifact_kinds=requirements["required_artifact_kinds"],
)
if not validation["valid"]:
    raise ValueError(validation["errors"])
```

This checks both paths a client must keep aligned:

- the work-item completion artifacts humans inspect;
- the evidence carrier refs later used in mutation proofs.

Governed-action composition preflight:

```python
packet = build_governed_action_composition_packet(
    GovernedActionCompositionInput(
        action_label="first gated action",
        profile="first_gated_action",
        observed_result=first_gated_action_json,
    )
)
if packet["summary"]["required_blockers"]:
    raise ValueError(packet["review_questions"])
```

The composition packet is a traceability matrix, not a workflow. The
`first_gated_action` profile expects the shortest deterministic proof to carry
resolved authority, run id, completed work item, bounded human-work session,
action attestation, outcome link, and governed-run bundle digest. The
`learning_loop` profile expects approved learning, context-packet, verified
context-packet, learning-use receipt, outcome, and routine-review follow-through.
`build_adoption_readiness_packet(...)` embeds these packets for observed
first-gated-action and learning-loop outputs so a green command cannot hide a
disconnected proof chain.

Each adoption-check row also reports `expected_evidence_fields`,
`present_evidence_fields`, `missing_evidence_fields`, and `evidence_quality`.
For required checks, a command can pass its basic expectations and still block
human adoption review when expected evidence fields are absent. This is a
chain-of-custody gate over the reviewer packet, not a command runner or release
approval.
The required `kernel_service_smoke` row expects closed-loop provenance
follow-through (`closed_loop_observed`) with outcome, routine-review,
learning-event, and learning-use counts, so a service smoke that only proves
basic route health remains too thin for v0.4 review.
The packet also embeds a read-only `reviewer_path` derived from the command
surface's first-review guidance, so the Markdown handoff shows `make
smoke-public`, `make adoption-onramp-packet`, and `make
adoption-readiness-packet` in order. This is orientation metadata over existing
commands, not a runner or workflow plan.

Service and userland surfaces:

- `POST /kernel/governed-action-composition` accepts `action_label`,
  `profile`, `observed_result`, optional `evidence_refs`, and returns the same
  `composition_packet`. It is a read-only POST because the observed output can
  be large and structured; it does not require a mutation lease and does not
  read or write canonical rows.
- `cognitive-firm-userland composition-packet --observed-json ...` renders the
  same matrix for terminal preflights. It exits non-zero when required
  composition blockers remain so adopter scripts can fail closed without
  treating the command as an approval gate.

Execution evidence routing recipe:

```python
packet = build_execution_evidence_route_packet(
    ExecutionEvidenceRouteInput(
        signal_kind="capability_gap",
        source_ref="agent_runtime:codex_exec",
        summary="Planner abstained because the role lacked file-edit authority.",
        owner_role="role.org_evolver",
        worker_ref="actor.codex",
        run_id="run_123",
        work_id="work_456",
        evidence_refs=["phase_execution_plan:pex_123", "a2a_message:msg_123"],
        governance_change_target_ref="org/mandates/org_evolver.md",
    )
)
```

The packet is not an executor. It gives adapters a stable sequence of existing
service routes to call:

1. `POST /kernel/capability-signals`;
2. `POST /kernel/capability-signals/{signal_id}/route` when routing is
   requested;
3. `GET /kernel/learning-transition-candidates?source=capability`;
4. optionally
   `POST /kernel/learning-transition-candidates/{candidate_id}/governance-change`.

This closes a common gap for external runtimes: "the agent could not or should
not continue" becomes a typed signal with a path into learning and governance,
without the recipe granting authority or mutating state.

When a client is using the kernel service rather than direct Python calls,
`POST /kernel/execution-evidence/route` executes this same composition against
the normal service routes. It records the capability signal, applies the route,
returns the matching observer-only learning candidate, and can draft a
governance proposal if `governance_change_target_ref` is supplied. The route
still stops before approval, file mutation, or worker execution.

Predicted mutation outcome link recipe:

```python
body = build_predicted_mutation_outcome_link_request(
    PredictedMutationOutcomeInput(
        proposal=proposal_row,
        created_by="role.evaluator",
        learning_event_id="learn_123",
        metadata={"run_id": "run_123"},
    )
)
```

The proposal supplies `proposal_id` and `predicted_effect`; the helper copies
the metric identity, direction, prediction, and proposal metadata into the
outcome-link request. This preserves packet provenance, such as policy
promotion packet ids, while the outcome link keeps its own recipe identity. The
kernel service creates the link through the ordinary outcome-link primitive.
Snapshots and verdicts remain separate calls, and prediction review is derived
only after a verdict.

Failed-prediction review recipe:

```python
body = build_predicted_mutation_reversal_review_request(
    PredictedMutationReversalReviewInput(
        outcome_link=outcome_link_row,
        review_due_utc="2026-06-13T00:00:00+00:00",
        scheduled_by="role.evaluator",
    )
)
```

By default, this helper requires
`outcome_link.metadata.prediction_review.status == "prediction_failed"`. The
request schedules a routine review with `routine_kind: "other"` and metadata
marking the changed governance object as a reversal candidate. The accountable
reviewer still decides whether to amend, retire, or escalate.

Kernel-service clients can call
`POST /kernel/outcome-links/{outcome_link_id}/reversal-review` for the same
composition. The route reads the outcome link, applies this helper, and writes
the normal routine-review row.

Operator summary recipe:

```python
summary = build_governed_run_operator_summary(
    GovernedRunOperatorSummaryInput(
        run_label="my_adapter_run",
        run_ref="run:run_123",
        summary=run_summary,
        operator_controls=bounded_controls,
        artifacts=[
            {
                "label": "viewer",
                "ref": "file://reports/viewer.html",
                "purpose": "Primary inspection surface.",
            }
        ],
        commands=[{"label": "rerun", "command": "make my-adapter-smoke"}],
        bundle_summaries=[bundle_summary],
        mutation_proofs=[proof_row],
        execution_signals=[capability_signal_row],
        learning_candidates=[learning_candidate_row],
        phase_plans=[phase_execution_plan_row],
        learning_closure=[
            {
                "step_id": "step_1",
                "learning_event_id": "learn_1",
                "learning_use_receipt_id": "lenc_1",
                "context_packet_refs": ["ctx_1"],
                "target_ref": "org/mandates/evaluator.md",
                "future_replay_intent": "apply approved learning before matching work",
                "outcome_link_id": "olink_1",
                "outcome_review_status": "prediction_met",
                "routine_review_id": "rrev_1",
                "routine_review_status": "scheduled",
                "evidence_refs": ["learning_event:learn_1", "outcome_link:olink_1"],
            }
        ],
        operator_burden={
            "human_work_pressure": pressure_groups,
            "action_impact_summary": action_impact_summary,
        },
    )
)
markdown = render_governed_run_operator_summary_markdown(summary)
```

This is still only a review projection. The bundle, proof rows, work items,
approval events, and git receipts remain the source of record.
Execution signals, learning candidates, and phase plans are compacted into an
`Execution Health` section so an operator can see unresolved abstentions,
authority gaps, blocked verification loops, and review-ready learning without
opening every JSONL log first. The summary counts open/blocking signals,
blocked phase plans, review candidates, and learning-closure rows. The
`Learning Closure` section is the v0.4 compounding-learning check: what was
learned, what context changed, which verified context packet future work can
inspect, whether outcome review confirmed it, and when routine review can
retire or reaffirm it. It does not close blocked phase plans, choose a route,
or promote memory.

When present, the `Operator Burden` section estimates human touchpoints from
bundle counts, missing receipts, A2H pressure, accountability cases, approval
events, and action-impact rows that require review. It includes review questions
so operators can ask whether governance is reducing hidden coordination or just
moving work onto people. This is still a projection: it does not assign work,
schedule review, approve policy, or optimize routing.

For field pilots, `summarize_operator_burden_field_pilot(...)` compares the
measured baseline and pilot rows in the same read-only style. The output
reports `stable`, `needs_review`, or `insufficient_evidence`; phase summaries;
pilot-vs-baseline deltas; projection-fit rows where actual human touchpoints
exceeded the runbook projection; and review reasons for hidden burden, missing
receipts, stale sessions, burden shift, or increased touchpoints. The summary
is evidence for a human adoption review, not a sampling policy or workload
optimizer.

Research Anchor:

- Cognitive-load theory motivates separating necessary judgment from avoidable
  extraneous load: John Sweller, "Cognitive Load During Problem Solving: Effects
  on Learning," Cognitive Science, 1988,
  <https://doi.org/10.1207/s15516709cog1202_4>.
- Queueing theory motivates surfacing waiting/stale pressure before bounded
  human attention becomes the bottleneck: John D. C. Little, "A Proof for the
  Queuing Formula: L = lambda W," Operations Research, 1961,
  <https://doi.org/10.1287/opre.9.3.383>.
- SRE toil accounting motivates treating repeated manual review as an observable
  load that should be reduced by better design when it is not essential human
  judgment: <https://sre.google/sre-book/eliminating-toil/>.
- Cost-of-quality accounting motivates keeping appraisal/review cost visible
  alongside failure/externality risk: <https://asq.org/quality-resources/cost-of-quality>.

Boundary:

- recipes are general-purpose composition helpers, not demo-story helpers;
- the kernel service remains the proof builder and validator;
- work-item lifecycle remains in the work-item primitive;
- proposal, approval, learning, outcome, routine review, bundle, and git
  receipts remain owned by their existing primitives;
- execution evidence routing remains a request plan over capability signals and
  learning candidates, not a side-effect runner;
- predicted mutation outcome-link creation remains a request body over the
  outcome-link primitive, not a metric calculator or verdict recorder;
- failed-prediction review remains a routine-review request, not automatic
  reversal or rollback;
- recipes are allowed to reduce adoption friction, not to create a new runtime
  or second governance lifecycle.

Use this module when a demo or adapter repeatedly wires the same governed
mutation chain. Do not put tenant strategy, scoring policy, scenario text, or
runtime-specific execution semantics here.
