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
  execution signals, learning candidates, and phase plans.
- `build_governed_run_operator_summary`: produces
  `governed_run_operator_summary.v1`, a stable human/operator review projection
  for demos and adapters.
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
blocked phase plans, and review candidates; it does not close them or choose a
route.

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
