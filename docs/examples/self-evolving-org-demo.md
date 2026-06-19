# Self-Evolving Organization Demo

Run:

```bash
make self-evolving-org
```

Then open:

```text
.cognitive-firm-runs/self-evolving-org-realtime/demo-firm/reports/self-evolving-org-company-state.html
```

The command runs the bounded fixture demo into the stable gitignored workdir
`.cognitive-firm-runs/self-evolving-org-realtime`, prints the viewer path, and
exits. If you want live-refresh over HTTP instead of opening the generated
file directly, add `SELF_EVOLVING_SERVE=1` or run the explicit serve target
shown below.

The primary command has two independent knobs:

```bash
# live Codex planner/reviewers/workload packets, score totals visible
make self-evolving-org SELF_EVOLVING_RUNTIME=codex

# fixture runtime, score feedback withheld from firm-visible state
make self-evolving-org SELF_EVOLVING_FEEDBACK=withheld

# live Codex A/B run: score-feedback arm vs no-feedback arm
make self-evolving-org SELF_EVOLVING_RUNTIME=codex SELF_EVOLVING_FEEDBACK=compare
```

`SELF_EVOLVING_RUNTIME` controls who does work (`fixture`, `codex`, or another
supported subscription/local CLI such as `claude`). `SELF_EVOLVING_FEEDBACK`
controls the score surface (`score_totals`, `withheld`, or `compare`). In live
comparison mode, both arms use the same runtime settings; only firm-visible
score feedback differs. Single-arm runs print
`demo-firm/reports/self-evolving-org-company-state.html`. Comparison runs print
`reports/self-evolving-feedback-comparison.html`, which links to both arm
viewers.

To run and serve in one command:

```bash
make self-evolving-org SELF_EVOLVING_SERVE=1
```

That serves the generated single-arm viewer at:

```text
http://127.0.0.1:8765/self-evolving-org-company-state.html
```

For comparison mode:

```bash
make self-evolving-org SELF_EVOLVING_FEEDBACK=compare SELF_EVOLVING_SERVE=1
```

That serves the comparison page at:

```text
http://127.0.0.1:8765/reports/self-evolving-feedback-comparison.html
```

To re-serve an already generated comparison directory over HTTP, run:

```bash
make self-evolving-org-compare-serve \
  SELF_EVOLVING_COMPARISON_SERVE_WORKDIR=.cognitive-firm-runs/self-evolving-feedback-comparison-...
```

For CI or terminal-only smoke:

```bash
make self-evolving-org-demo
```

For an inspectable run with persistent reports and a static HTML timeline:

```bash
make self-evolving-org-view
```

To serve those generated reports so the company-state page can live-refresh
from the JSON projection:

```bash
make self-evolving-org-realtime-serve
```

In another terminal, run the realtime fixture into the same stable ignored
workdir:

```bash
make self-evolving-org-realtime-view
```

Then open
`http://127.0.0.1:8765/self-evolving-org-company-state.html`.

The Make targets share one bounded-iteration knob:

```bash
make self-evolving-org-view SELF_EVOLVING_DEMO_ITERATIONS=10
```

They also support operator controls for longer autonomous runs:

```bash
make self-evolving-org-view \
  SELF_EVOLVING_DEMO_ITERATIONS=100 \
  SELF_EVOLVING_DEMO_BUDGET_UNITS=25 \
  SELF_EVOLVING_DEMO_STOP_FILE=/tmp/cf-demo.stop
```

This example has two modes:

- `make self-evolving-org-demo` runs a deterministic, no-model proof fixture.
  It proves the governance/proof path without spending tokens or calling a
  provider.
- `make self-evolving-org-view` runs the same no-model proof fixture into a
  timestamped gitignored directory under `.cognitive-firm-runs/`, then prints
  the tabbed demo viewer, operator runbook, and report JSON paths for
  inspection.
- `make self-evolving-daemon-smoke` installs a starter firm, adds an
  `org_evolver` office and pending task, then runs the actual daemon against
  that installed firm with a local subscription-CLI-shaped stub runtime. It
  proves the native path through role session, mandate, work discovery,
  authorization, daemon dispatch, task closure, continuity, transition logs,
  the runtime run/checkpoint projection, and a verified daemon action
  attestation for the CLI dispatch. It writes
  `reports/self-evolving-daemon-smoke.md`,
  `reports/self-evolving-daemon-timeline.json`, and
  `reports/self-evolving-daemon-timeline.html` inside the generated firm.
- `make self-evolving-daemon-governed-smoke` runs the same daemon-native
  dispatch path, has the daemon-dispatched runtime write a bounded planner
  artifact, then feeds that artifact into the existing governed mutation path.
  This is the no-cost proof that daemon-native work can lead to the same
  proposal, approval, mutation, attestation, learning, outcome, bundle, proof,
  replay, report, and git chain without recreating those semantics in the
  daemon smoke.
- `make self-evolving-org-agent-demo` runs a live planner bridge. A
  subscription or local tool-using agent proposes bounded structural changes,
  then the kernel routes each proposed mutation through the same governance,
  attestation, learning, outcome, review, bundle, and git path. The target
  writes reports under the same repo-local `.cognitive-firm-runs/` tree and
  prints the tabbed demo viewer, operator runbook, and report JSON paths.
- `make self-evolving-org-api-demo` runs a portable API model-call planner.
  This is useful when a subscription/local agent is not available, but it is a
  weaker worker shape: fungible, API-sourced, and less persistent. It also
  writes the same viewer/proof artifacts under `.cognitive-firm-runs/`.

All modes install a fresh starter firm into a temporary directory and add a
small demo overlay. The difference is where proposals come from: fixed fixture
steps in the no-cost path, agent-generated JSON in the live planner bridge, or
API model-call JSON in the portable fallback.

The overlay seeds `org/charters/self_evolving_firm.md`. The demo firm is not a
random business simulator and it does not ask agents to optimize an undefined
universe. Its genesis charter anchors capability to an exogenous workload:
task packets in `org/workload/inbox/`, scored by an external rubric that the
firm cannot read or modify. Capability is trailing workload score per dispatched
budget unit, with error, incident, and unresolved-authority-gap counts as guard
metrics. Counts of offices, policies, proposals, or documents are explicitly
not capability measures.

The initial game is a neutral Coordination Desk, not an abstract "improve
yourself" loop. The shipped genesis workload contains 20 concrete packets for
the fictional Halloway Institute across five classes: intake triage, hidden
records refinement, resource conflict, memory retrieval, and routine pruning.
Each packet has named parties, dates, attachments, one buried complication, and
a concrete deliverable. The tasks are concrete enough to score and inspect, but
generic enough that the kernel does not choose an industry business model.

The v1 workload is fixed on purpose. Fixed packets make the score-feedback vs.
withheld-feedback comparison reproducible and make smoke failures debuggable.
They are not meant to support unlimited optimization. Recommended live runs are
1-3 governed iterations; longer runs should add an operator-side held-out
tranche or packet generator so the firm must generalize instead of overfitting
to the visible benchmark.

The workload probe harness dispatches those packets through the kernel
work-item route for `workload_probe_desk`. Firm-visible state receives the
packet inbox, execution receipts, action attestations, and optionally score
totals. The operator-only scorecards are written outside the generated
`demo-firm` directory under the run root's `operator-only/workload-probes/`
directory. The answer key and rubric are not copied into `org/` or `reports/`.
The firm-visible measurement carrier is
`reports/workload-probes/workload-probe-summary.json`, with the receipt index at
`org/workload/executions/README.md`. Live planner prompts and reviewer evidence
refs carry those paths so capability claims can be checked against the workload
probe instead of relying on model narration.

Two feedback arms are supported:

- `score_totals` returns packet totals and score-per-budget into firm-visible
  receipts and the workload-probe summary. This is the anchored-learning arm.
- `withheld` still scores operator-side, but firm-visible receipts say that
  score feedback was withheld. This is the no-feedback baseline for observing
  whether the organization involutes into process work when it cannot see task
  performance. Planner prompts explicitly warn that operator-only score values
  are not firm-visible evidence.

Use `SELF_EVOLVING_FEEDBACK=withheld` with the Make targets, or pass
`--workload-feedback withheld` to the script directly.

After executing or inspecting that workload, the firm may self-organize by
proposing one bounded state change at a time where workload evidence shows the
current office structure, mandates, decision model, protocol, or learning units
are costing score or budget. Agents may refine the charter, but only through
the same proposal, review, approval, attestation, learning, proof, and git chain
as any other structural mutation.

This genesis shape follows the useful lesson from recent self-organizing
LLM-MAS work: give agents a mission and a protocol envelope, then inspect the
organization they invent. `Drop the Hierarchy and Roles` argues for mission,
protocol, and capable agents over pre-assigned detailed roles
(arXiv:2603.28990). `Meta-Team` motivates experience-driven evolution from
distributed execution evidence into behavior, coordination, and team-level
organization changes (arXiv:2605.29790). `ReDel` shows why recursive
delegation needs event logging and replay visualization (arXiv:2408.02248).
`TheBotCompany` motivates phase evidence and dynamic team adaptation while
keeping verification visible (arXiv:2603.25928). cognitive-firm adds the
governance layer around that emergence: typed offices, A2A review, explicit
decision rights, durable learning, bundles, mutation proofs, and git receipts.
The workload anchor is also the Goodhart guard: the firm can inspect task
packets and its visible capability contract, but it must not read, infer, or
optimize the hidden scoring rubric itself.

The default fixture runs three iterations to keep public smoke fast. For a
longer local proof run, pass a higher iteration count through Make or call the
script directly with a persistent workdir:

```bash
PYTHONPATH=src python demos/self_evolving_org/run.py \
  --iterations 10 \
  --workdir .cognitive-firm-runs/cf-demo-long
```

To run the no-feedback comparison:

```bash
make self-evolving-org-compare SELF_EVOLVING_DEMO_ITERATIONS=3
```

This creates two generated firms under
`.cognitive-firm-runs/self-evolving-feedback-comparison-*`: one score-feedback
arm and one no-feedback arm. The operator scores both arms with the same hidden
workload scorecards, but only the score-feedback arm receives score totals in
firm-visible state. The target starts a local static server; inspect
`http://127.0.0.1:8765/reports/self-evolving-feedback-comparison.html` first,
then drill into either embedded arm viewer.
The comparison report is the fastest way to see whether visible score feedback
changed the approved mutation, hidden holdout score, blocked proposals, and
budget use. Each arm still has its own generated
`demo-firm/reports/self-evolving-org-company-state.html` viewer for the full
proposal, reviewer, proof, workload, and git trace. In the Agent Work tab,
live reviewer positions show both their captured prompt/output artifacts and
the input evidence refs they reviewed. Reviewer-quorum blocks preserve the same
decision positions, so a blocked run is still useful evidence rather than a
blank failed demo.

In live runs, a no-feedback arm may legitimately end with
`termination_reason=blocked_by_reviewer_quorum` if reviewer offices abstain
because the firm cannot substantiate predicted capability or budget impact.
That is an expected governed outcome: the harness routes the escalated decision
aggregation case through
`POST /kernel/decision-aggregation-cases/{case_id}/route-escalation`, which
records a capability/evidence signal, exposes an observer-only learning
candidate, can draft a blocked governance proposal, and still writes the
comparison report.

For an open-ended local session, use a high iteration ceiling with an explicit
budget or stop file. The stop file is checked between governed iterations, so a
single in-flight mutation can finish and write complete reports:

```bash
PYTHONPATH=src python demos/self_evolving_org/run.py \
  --run-until-stopped \
  --budget-units 100 \
  --stop-file .cognitive-firm-runs/cf-demo.stop \
  --workdir .cognitive-firm-runs/cf-demo-open
```

Create the stop file from another terminal to end the run cleanly:

```bash
touch .cognitive-firm-runs/cf-demo.stop
```

`--run-until-stopped` intentionally requires either `--budget-units` or
`--stop-file`. The demo can keep asking agents for proposed org changes, but the
operator still retains a clear stop condition and the generated firm still ends
with inspectable reports, proofs, and git history.

For live subscription-agent runs, the demo guards the hidden scoring boundary:
Codex sandbox bypass and Claude extra read roots are rejected for this workload
demo. Custom local planner commands remain supported as trusted operator
wrappers, but they are not represented as sandboxed subscription runtimes.

Every report includes `operator_controls.schema =
bounded_run_controls.v1`. Inspect `operator_controls` in
`reports/self-evolving-org-demo.json` or the operator runbook to see consumed
budget, remaining budget, simulation-clock position, and a deterministic
`stop_receipt` when the run ends because the budget is exhausted or the stop
file is observed.

## Simulation Time

The v1 demo uses an explicit bounded simulation clock:

- one **simulation tick** equals one proposed structural change completing its
  governed path;
- each tick has a stable id such as `tick_0001` and label such as `T+0001`;
- the clock advances only after the step produces its run, work item, A2A
  reviews, advisory decision case, proposal, approval, mutation, learning
  event, outcome link, proof bundle, and git commit;
- wall-clock time is still recorded by the underlying kernel logs and git
  history, but wall-clock duration is not the simulation clock.

This prevents the demo from implying that minutes or seconds inside a model are
organizational time. The organization advances when a governed state transition
finishes. In live daemon mode, the daemon's polling cadence determines when the
next planner task is offered, while the demo clock still advances only when a
governed mutation tick closes.

## Live Agent Play Loop

Live agents do not free-chat until something happens. They play inside a bounded
role office and task envelope:

1. The starter firm is installed and seeded with durable offices and mandates.
2. The daemon discovers a pending task for `org_evolver`.
3. The configured role-bearing runtime, for example Claude Code or Codex CLI,
   receives the mandate, role contract, task, and execution route.
4. The runtime writes a bounded planner artifact describing proposed structural
   changes.
5. The kernel parses and bounds those proposals, then routes each accepted
   proposal through the same governed tick path used by fixture mode.
6. If the runtime times out or emits invalid planner output, the run writes a
   rejection/dispatch report and no org mutation is applied.

The live planner is therefore allowed to be creative about what the organization
should improve, but it is not allowed to bypass typed authority, A2A review,
advisory aggregation, approval, evidence, learning review, or mutation proof.
In compact live-smoke mode, the planner prompt prioritizes the self-evolving
firm charter and the Org Evolver mandate so the first proposal is grounded in
the company game rather than incidental protocol files.

Fixture mode preserves the first three hand-authored changes, then generates
additional bounded, domain-neutral mandate/role/policy refinements. Generated
steps still go through the same work item, proposal, approval, mutation,
attestation, learning, outcome, review, bundle, proof, replay, and git path.

Each iteration creates:

- a planner receipt when proposal steps come from fixture, subscription/local
  agent, or API planner output;
- a governed run and claimable work item;
- a phase execution plan with strategy, execution, and verification evidence;
- a typed A2A review request from `org_evolver` to `evaluator`, persisted in
  the generated firm's `org/channels/` directory, then acknowledged,
  accepted, moved in progress, and fulfilled through the obligation lifecycle;
- a second typed A2A request from `evaluator` to `risk_guardian` for independent
  review of authority expansion, rollback, recursion, resource, and incentive
  risk;
- a third typed A2A request from `evaluator` to `learning_steward` for
  learning-unit quality review before the accepted change can affect future
  work;
- an advisory `DecisionAggregationCase` using a four-role quorum-majority
  procedure over `org_evolver`, `evaluator`, `risk_guardian`, and
  `learning_steward`; this records review agreement as evidence without
  replacing principal approval;
- multi-agent trace events imported through the kernel service;
- a capability signal routed into a learning-transition candidate;
- a governance-change proposal promoted from that candidate with invariant
  checks;
- an approval decision;
- an applied file mutation in the demo firm;
- an action attestation for the mutation;
- an approved learning event and learning encounter;
- a future-work replay proof that the approved learning reappears through work
  discovery for the responsible role;
- an outcome link with baseline, post measurement, and verdict;
- a routine review for the accepted learning;
- a governed-run attestation bundle;
- a compact governed-mutation proof chain;
- a delegation graph projection for the iteration's trace events;
- a git commit in the generated demo firm.

Each run also includes one deliberately blocked structural proposal. The
blocked fixture starts as a capability signal and learning-transition
candidate, then attempts promotion without the evidence required for structural
mutation. The kernel records a blocked governance-change proposal and writes no
target role file. This proves the same path can carry useful negative evidence
without granting authority or applying a mutation.

The demo is intentionally not an agent framework. It shows the governance layer
around autonomous organization changes: typed authority, proposal evidence,
approval, provenance, measured outcome, review, bundle validation, and git as
the system of record.

## Decision Model

The v1 demo is not a voting or consensus demo. It uses a scoped decision-rights
shape:

- `org_evolver` proposes a bounded structural change;
- `evaluator` receives a typed A2A review request and fulfills the review
  obligation;
- `risk_guardian` receives a second typed A2A review request and independently
  checks rollback, authority expansion, recursion, resource, and incentive
  risk;
- `learning_steward` receives a third typed A2A review request and checks
  future-use cue, source refs, routine review, and retirement pressure for the
  learning unit;
- the demo records an advisory `DecisionAggregationCase` with the
  `quorum_majority` procedure over proposer, evaluator, risk guardian, and
  learning steward;
- `role.principal` is the approval authority and tie breaker for the demo
  harness.

This keeps the separation of generation, evaluation, approval, and execution
visible. A future multi-principal or committee variant should use an explicit
decision-aggregation policy, not infer agreement from multiple agent messages.
The v1 aggregation case is evidence for review, not the authority that applies
the mutation.

The deterministic fixture is not the claim that the organization self-evolved.
It is the release-safe proof harness for the mutation path. The
subscription/local agent planner has a better worker shape than an API model
call for persistence and repo work, but it is still a bridge until the demo is
daemon-native.

Every planner mode writes durable planner receipts under
`reports/planner/<receipt_id>/` in the generated demo firm. The receipt records
the planner transport, step ids, prompt/response/step digests, sanitized command
metadata for subscription/local agent runs, and the parsed step JSON. Accepted
mutations cite the planner receipt in phase evidence, trace refs, capability
signal evidence, action-attestation inputs, learning-event sources, work
artifacts, and mutation-proof evidence. This makes the planner output
auditable without letting it bypass proposal review or approval.

The subscription/local-agent target accepts the same iteration knob. Prefer the
provider-neutral runtime selector when using Claude Code or Codex directly:

```bash
make self-evolving-org-agent-demo \
  SELF_EVOLVING_DEMO_ITERATIONS=2 \
  AGENT_RUNTIME=claude
```

`AGENT_RUNTIME=claude` or `AGENT_RUNTIME=codex` uses the same
`orchestration.agent_runtime_invocation` policy as the Python daemon: project
root, adapter inference, Claude permission mode, Codex sandbox mode, optional
tool flags, and subscription-auth env scrubbing are all controlled by the
`COGNITIVE_FIRM_*` variables in `.env.example`.

Live subscription runs require the selected CLI to be authenticated in the
operator environment first (`claude /login` or `codex login`). If the runtime is
not logged in, the demo writes a rejected planner receipt and stops before any
mutation.

Use `AGENT_PLANNER_COMMAND` only for a custom wrapper. If the command string
contains `{prompt_file}`, the demo replaces it with a temporary prompt path. If
the command omits `{prompt_file}`, the prompt is sent on stdin. The command must
return only the bounded JSON shape described in the prompt. The kernel then
parses, bounds, records, and governs those proposed changes exactly as it does
for fixture and API planner output.

The demo also proves learning is not just archived. After each approved
mutation, it asks work discovery for role-relevant approved learning using the
new decision cue and records the resulting `learning-event-replay` candidate in
the per-step report. This demonstrates that an accepted learning unit can be
encountered by future work instead of remaining retrospective prose.

The daemon-native smoke is also not the live self-evolving claim. Its runtime
is a local stub so it can run in public CI without network or account state.
Its job is to prove the correct kernel path that the live demo must use. Its
timeline viewer shows the installed role office, mandate, pending task,
runtime run, checkpoints, verified daemon action attestation, and completed
task closure.

The daemon-native flagship should run against the installed starter firm using
role mandates, role sessions, inbox/work discovery, authorization gates, and
the configured role-bearing agent runtime.

The first daemon-native enabling slice is now present: `scripts/agent_daemon.py`
accepts `--project-root`, `--org-root`, and `--workspace-root`, removes the
fixed role enum, reads bootstrap/mandate/control/directive paths from the
target firm, and passes the target firm as the subscription-agent project/cwd.
For the cleanest isolated run, launch the process with these environment
variables set before import-time path constants are loaded:

```bash
COGNITIVE_FIRM_PROJECT_ROOT=/path/to/demo-firm \
ORG_ROOT=/path/to/demo-firm/org \
COGNITIVE_FIRM_WORKSPACE=/path/to/demo-firm/cognitive_firm_workspace \
PYTHONPATH=src python scripts/agent_daemon.py \
  --role org_evolver \
  --tick-once \
  --unattended
```

That is the intended path for the flagship demo. The current `make
self-evolving-org-agent-demo` bridge is useful for testing proposal sanitation
and proof-chain mechanics, but it is not the final native demonstration. Live
planner output is bounded before proposal creation: paths must stay under the
demo `org/` envelope, `target_ref` must match `applied_relpath`, change kinds
must match their target path class, duplicate step ids are rejected, and
generated role YAML may only declare local org-file authority. The bridge
rejects role YAML that declares tools, MCP capability grants, secrets,
environment fields, wildcard-only paths, or authorized paths outside the demo
governance envelope.

Rejected planner output is durable. If a subscription/local planner exits
nonzero, returns malformed JSON, proposes a path outside the bounded demo
envelope, or proposes unsafe role YAML, the command exits with status `2` and
writes:

- `reports/self-evolving-org-planner-rejection.json`
- `reports/self-evolving-org-planner-rejection.md`
- `reports/planner/<receipt_id>/receipt.json`
- `reports/planner/<receipt_id>/prompt.md`
- `reports/planner/<receipt_id>/response.txt`
- `reports/planner/<receipt_id>/stderr.txt`
- `reports/planner/<receipt_id>/error.txt`

No governance proposal is opened and no organization mutation is applied for a
rejected planner receipt. The rejection artifact exists so live-agent failures
remain inspectable without weakening the approval path.

The no-cost native dispatch check is:

```bash
make self-evolving-daemon-smoke
```

The no-cost daemon-backed governed mutation check is:

```bash
make self-evolving-daemon-governed-smoke
```

The live daemon-backed path uses the same code path but replaces the stub
runtime with a role-bearing local/subscription agent runtime. Prefer the
provider-neutral selector:

```bash
make self-evolving-daemon-live-governed-demo \
  AGENT_RUNTIME=codex \
  SELF_EVOLVING_DAEMON_WORKDIR=.cognitive-firm-runs/cf-live-demo \
  SELF_EVOLVING_DAEMON_TIMEOUT=300
```

or, for Claude Code:

```bash
make self-evolving-daemon-live-governed-demo \
  AGENT_RUNTIME=claude \
  SELF_EVOLVING_DAEMON_WORKDIR=.cognitive-firm-runs/cf-live-demo \
  SELF_EVOLVING_DAEMON_TIMEOUT=300
```

`AGENT_RUNTIME` maps to the local subscription CLI with `AGENT_ADAPTER=auto`.
Use explicit `AGENT_CLI` and `AGENT_ADAPTER` only when debugging a wrapper or
forcing a specific adapter shape.

In that mode the daemon does not apply the structural mutation directly. It
dispatches the durable `org_evolver` role, records dispatch provenance, and
the role-bearing runtime produces `workspace/daemon_planner_steps.json`. The
demo then creates a planner receipt from that artifact and routes it through
the same governed mutation core used by the fixture, subscription/local planner
bridge, and API planner bridge. The resulting
`reports/self-evolving-org-demo.md` includes a `Daemon Dispatch` section, and
the organization timeline includes a `daemon_dispatch` node.

If the live daemon-dispatched runtime fails to write
`workspace/daemon_planner_steps.json`, or writes invalid/unsafe planner JSON,
the demo writes the same rejected-planner receipt and rejection report used by
the live planner bridge, exits nonzero, and applies no organization mutation.

Useful inspection files for the live daemon path:

- `.cognitive-firm-runs/cf-live-demo/demo-firm/reports/self-evolving-daemon-smoke.md`
- `.cognitive-firm-runs/cf-live-demo/demo-firm/reports/self-evolving-org-company-state.html`
- `.cognitive-firm-runs/cf-live-demo/demo-firm/reports/self-evolving-org-demo.md`
- `.cognitive-firm-runs/cf-live-demo/demo-firm/reports/self-evolving-org-timeline.json`
- `.cognitive-firm-runs/cf-live-demo/demo-firm/reports/self-evolving-org-mutation-proofs.json`
- `.cognitive-firm-runs/cf-live-demo/demo-firm/org/learning/events.jsonl`
- `.cognitive-firm-runs/cf-live-demo/demo-firm/cognitive_firm_workspace/transitions.jsonl`
- `.cognitive-firm-runs/cf-live-demo/demo-firm/workspace/daemon_planner_steps.json`

Observability checklist after a bounded live smoke:

- daemon prompt: `workspace/agent_prompts/*.md`;
- daemon dispatch log: `workspace/agent_daemon_log.jsonl`;
- live planner artifact: `workspace/daemon_planner_steps.json`;
- governed planner receipt: `reports/planner/<receipt_id>/prompt.md`,
  `response.txt`, `steps.json`, and `receipt.json`;
- agent-to-agent review messages: `org/channels/*/{inbox,sent}/*.json`;
- tabbed human-first demo viewer:
  `reports/self-evolving-org-company-state.html`;
- timeline graph export: `reports/self-evolving-org-timeline.json`;
- mutation proof export:
  `reports/self-evolving-org-mutation-proofs.json`;
- generated-firm git history: `git -C <run>/demo-firm log --oneline`.

To preflight a planner artifact before running the full governed mutation path:

```bash
make self-evolving-planner-validate \
  SELF_EVOLVING_PLANNER_JSON=/path/to/daemon_planner_steps.json
```

The validator uses the same parser and safety checks as the demo bridge. It
prints a compact JSON verdict and does not install a firm, open a proposal, or
mutate any org state.

Each step also emits a `governed_mutation_proof` in
`reports/self-evolving-org-mutation-proofs.json`. The proof chain is:

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

The bundle and proof reference existing kernel records and the git commit. They
are review/export projections, not a second source of truth. The demo builds
the governed-run bundle through `POST /kernel/governed-run-bundles/build`, then
builds and validates the mutation proof through the read-only
`POST /kernel/mutation-proofs/build` and
`POST /kernel/mutation-proofs/validate` routes.
The proof also carries `evidence_carrier_refs` for the capability signal,
learning-transition candidate, phase execution plan, planner receipt, and trace
events that supported the promoted proposal.
Before writing the final report, the demo rebuilds each mutation proof from the
recorded step facts through the same read-only proof-build route and compares
the rebuilt payload with the saved proof. The summary includes
`mutation_proofs_reconstructed` and `mutation_proof_replay_valid`.
The demo also writes `reports/self-evolving-org-demo.md`, a compact human
review report with summary metrics, accepted mutations, proof-chain tables,
planner receipts, evidence carrier refs, delegation diagnostics, blocked
proposals, provenance report refs, and git receipts. Accepted governed
mutations also write reusable provenance handoff reports under
`reports/provenance/` by calling the same read-only
`GET /kernel/provenance-report?run_id=...` route used by userland. Accepted
and blocked governance proposals write reusable review handoff packets under
`reports/proposals/` by calling
`GET /kernel/governance-changes/{proposal_id}/review-packet`. The main demo
report summarizes those packets' follow-through status so reviewers can see
which accepted proposals reached closed-loop evidence and which blocked
proposal remains proposal-only.
After outcome and routine-review records exist, each accepted mutation also
obtains a future work-discovery context packet, verifies it through
`POST /kernel/work-discovery/context-packet/verify`, and records a
learning-use receipt tied to that verified packet. The packet is evidence for
future dispatch, not hidden memory or workflow state.

For visual inspection, the primary surface is
`reports/self-evolving-org-company-state.html`, backed by
`reports/self-evolving-org-company-state.json`. It is a single tabbed viewer
with a visual Home / Company entry, Agent Work, and Proof Chain tabs. The home
surface is inspired by a sealed coordination floor: visible work enters the
firm, hidden scoring stays outside the firm, offices discuss through protocol
state, and approved changes leave proof and git receipts. The Agent Work tab
keeps prompt and response artifacts readable by showing short digests first and
putting raw prompt/response excerpts behind expandable controls.

The Proof Chain tab uses the same timeline graph that is exported as
`reports/self-evolving-org-timeline.json`, a portable node/edge graph over
planner receipts, runs, work items, phase plans, A2A review obligations,
decision aggregation cases, signals, learning candidates, proposals, approvals,
mutations, attestations, learning events, future replay proofs, outcomes,
reviews, bundles, commits, trace events, and the blocked unsafe proposal.
This projection answers:

- what role offices exist now;
- what structural mutations were accepted;
- what learning units and verified context packets can affect future dispatch;
- what planner transport produced the proposals;
- what prompt/response artifacts exist for live planner runs;
- what A2A review messages were exchanged;
- where the proof, timeline, and git receipts live.

The tabbed company-state view is the place to inspect both the evolving
organization and the proof chain. It is a dependency-free review surface for
Orbit or a future web demo; it is not a second source of truth.

Use `make self-evolving-org-view` for the simplest persistent inspection path.
Use `--workdir` directly when you want to choose the output directory yourself:

```bash
PYTHONPATH=src python demos/self_evolving_org/run.py --workdir .cognitive-firm-runs/cf-demo
open .cognitive-firm-runs/cf-demo/demo-firm/reports/self-evolving-org-company-state.html
```

For a live-refreshing view, run the realtime report server and demo against the
same stable ignored workdir. The HTML embeds the initial state for file-open
inspection and polls `self-evolving-org-company-state.json` every two seconds
when served over localhost. The harness writes an initial company-state
snapshot before the first tick and refreshes it after every completed governed
iteration:

```bash
make self-evolving-org-realtime-serve

SELF_EVOLVING_DEMO_ITERATIONS=100 \
SELF_EVOLVING_DEMO_BUDGET_UNITS=25 \
make self-evolving-org-realtime-view
```

The direct `--workdir` path expects a fresh output directory. To intentionally
rerun into the same directory, pass `--replace-existing`; this deletes and
recreates only the generated `demo-firm` below that workdir:

```bash
PYTHONPATH=src python demos/self_evolving_org/run.py \
  --workdir /tmp/cf-demo \
  --replace-existing
```

Execution evidence is also service-native. The demo writes phase plans through
`POST /kernel/phase-execution-plans` and
`POST /kernel/phase-execution-plans/{plan_id}/directives`, records verifier
feedback through
`POST /kernel/phase-execution-plans/{plan_id}/verification-feedback`, sends a
typed review request through `POST /kernel/a2a/messages`, advances the review
through `POST /kernel/a2a/messages/{message_id}/obligation`, imports trace
events through `POST /kernel/multi-agent-trace-events`, records advisory
decision procedure evidence through `POST /kernel/decision-aggregation-cases`,
`POST /kernel/decision-aggregation-cases/{case_id}/positions`, and
`POST /kernel/decision-aggregation-cases/{case_id}/compute`, and reads the
delegation graph through `GET /kernel/delegation-graph`. Those records are
evidence for review; they do not approve or apply structural changes.

Structural proposal creation is also service-native. Each accepted iteration
records and routes a capability signal through
`POST /kernel/capability-signals` and
`POST /kernel/capability-signals/{signal_id}/route`, reads the resulting
candidate from `GET /kernel/learning-transition-candidates?source=capability`,
and promotes it through
`POST /kernel/learning-transition-candidates/{candidate_id}/governance-change`.
The accepted signal is closed only after the governance proposal is approved.
The blocked fixture remains unresolved and appears in the report under
`blocked_proposals`.

Use `--full-json` to inspect the per-iteration ids and bundle summaries:

```bash
PYTHONPATH=src python demos/self_evolving_org/run.py --full-json
```

Run the live planner bridge with a subscription/local agent runtime:

```bash
AGENT_RUNTIME=claude make self-evolving-agent-preflight
AGENT_RUNTIME=claude make self-evolving-org-agent-demo
AGENT_RUNTIME=codex make self-evolving-agent-preflight
AGENT_RUNTIME=codex make self-evolving-org-agent-demo
```

`self-evolving-agent-preflight` is a no-mutation readiness check. It asks the
local agent CLI for one exact JSON object using the same invocation policy as
the demo. Known subscription CLIs prefer local subscription/token auth by
stripping the provider API key that would otherwise override it. Prompt
transport is `auto`: Claude receives an argv prompt, Codex receives stdin, and
receipts redact argv prompt text. The preflight returns a structured failure
when the runtime is missing, not logged in, blocked during initialization, timed
out, credit-limited, or returned non-JSON output.

The shortest release-style live proof is one planner call with no live reviewer
or workload-executor slots. It spends one bounded budget unit and still routes
any accepted change through proposal review, governed mutation, mutation proof,
future replay proof, report JSON, and the operator runbook:

```bash
make self-evolving-agent-preflight \
  AGENT_RUNTIME=codex \
  AGENT_ADAPTER=codex_exec

make self-evolving-org-agent-demo \
  AGENT_RUNTIME=codex \
  AGENT_ADAPTER=codex_exec \
  SELF_EVOLVING_DEMO_ITERATIONS=1 \
  SELF_EVOLVING_DEMO_BUDGET_UNITS=1 \
  SELF_EVOLVING_PLANNER_PROMPT_MODE=compact \
  SELF_EVOLVING_PLANNER_TIMEOUT_SECONDS=300
```

When reviewer or workload-executor runtimes are configured, the same target
returns `agent_runtime_readiness_summary.v1` across all configured slots:

```bash
AGENT_RUNTIME=codex \
AGENT_ADAPTER=codex_exec \
AGENT_REVIEWER_RUNTIME=claude \
AGENT_REVIEWER_ADAPTER=claude_print \
SELF_EVOLVING_WORKLOAD_EXECUTOR_RUNTIME=claude \
SELF_EVOLVING_WORKLOAD_EXECUTOR_ADAPTER=claude_print \
make self-evolving-agent-preflight
```

The planner slot is required. Reviewer and workload-executor slots are optional
and can be absent without blocking a fixture/protocol-backed run.

For a short smoke, use compact prompt mode and a small planner timeout. This
still routes any accepted proposal through the same governed mutation chain:

```bash
AGENT_RUNTIME=claude \
SELF_EVOLVING_PLANNER_TIMEOUT_SECONDS=60 \
make self-evolving-agent-preflight

AGENT_RUNTIME=claude \
SELF_EVOLVING_DEMO_ITERATIONS=1 \
SELF_EVOLVING_DEMO_BUDGET_UNITS=1 \
SELF_EVOLVING_PLANNER_PROMPT_MODE=compact \
SELF_EVOLVING_PLANNER_TIMEOUT_SECONDS=60 \
make self-evolving-org-agent-demo
```

If the runtime takes too long or fails to return valid planner JSON, the demo
writes a rejected planner receipt and stops before opening a governance
proposal.

The daemon-native live target is stricter because the agent must write
`workspace/daemon_planner_steps.json` inside the installed demo firm:

```bash
AGENT_CLI=codex \
AGENT_ADAPTER=codex_exec \
SELF_EVOLVING_DAEMON_TIMEOUT=300 \
make self-evolving-daemon-live-governed-demo
```

If that artifact is missing or malformed, the run is useful negative evidence:
the daemon dispatch receipt is preserved, the planner output is rejected, and
no structural mutation is applied.

For a custom wrapper, provide a command that emits the planner JSON on stdout.
The prompt is passed on stdin unless the command contains `{prompt_file}`:

```bash
AGENT_PLANNER_COMMAND="/absolute/path/to/my-agent-planner" make self-evolving-org-agent-demo
AGENT_PLANNER_COMMAND="/absolute/path/to/my-agent-planner {prompt_file}" make self-evolving-org-agent-demo
```

The target prints the generated tabbed demo viewer and report JSON paths. The
generated reports directory also includes
`self-evolving-org-runbook.md`, which is the fastest inspection index for
humans: it links the viewer, planner receipts, mutation proofs, git history,
and safe rerun commands. The runbook JSON uses the generic
`governed_run_operator_summary.v1` projection from
`governed_run_recipes`, with demo-specific metadata under `metadata`. Accepted
mutations also feed the runbook's `Learning Closure` section, which joins the
learning event, verified context packet, learning-use receipt, changed org
context, future replay cue, outcome review, routine review, and evidence refs.
To serve the tabbed viewer with live polling, pass the printed
`SELF_EVOLVING_DEMO_WORKDIR` to
`make self-evolving-org-serve`, or use the stable realtime targets shown above
for fixture-mode inspection.

The live planner target plays one bounded simulation tick per accepted
governed structural mutation. Set `SELF_EVOLVING_DEMO_ITERATIONS=N` to choose
the maximum number of accepted ticks. Each tick runs through multiple durable
offices: `org_evolver` proposes, `evaluator` reviews, `risk_guardian` checks
authority/risk, `learning_steward` checks durable learning quality, and
`principal` remains the approval authority. The company-state viewer shows
the resulting offices, A2A messages, planner transcript, canonical agent
invocation audit row, learning units, and Proof Chain tab.
The viewer also includes a runtime-slots panel that shows which offices were
backed by a live spawned worker in the run and which offices participated
through protocol/governance state.

The live-worker boundary is deliberately explicit. By default, v1 spawns one
live role-bearing runtime per run for the proposer/worker path (`org_evolver`
in the direct planner bridge, or the daemon-dispatched role in the
daemon-native path). Evaluator, risk guardian, learning steward, and principal
still participate as durable kernel offices through A2A obligations, decision
positions, learning checks, and approval state.

Optionally, the direct live planner bridge can also back the evaluator,
risk_guardian, and learning_steward review offices with a subscription/local
agent CLI. Their outputs are advisory JSON review positions. The demo records
each reviewer process as an `agent_cli_dispatch` action attestation tied to the
A2A message, then feeds the attestation refs into the decision aggregation case,
work completion refs, and mutation proof. A reviewer process does not get a
separate mutation path or approval authority.

Runtime selection is not hardcoded in the demo script. `Makefile` maps
`AGENT_RUNTIME`, `AGENT_CLI`, and `AGENT_ADAPTER` into
`demos/self_evolving_org/run.py` or `demos/self_evolving_org/daemon_smoke.py`.
The provider-neutral subprocess policy lives in
`src/cognitive_firm/orchestration/agent_runtime_invocation.py`: `claude_print`
wraps Claude Code's noninteractive print mode, `codex_exec` wraps Codex exec,
and `AGENT_PLANNER_COMMAND` can point at any local wrapper that emits the
planner JSON schema on stdout. The API fallback is separate: Gemini, DeepSeek,
OpenAI, and OpenAI-compatible local servers are model-call planners, not
persistent subscription/local agent CLIs.

Inspect the available worker shapes with:

```bash
make self-evolving-agent-adapters
```

## Live Invocation Accounting

The demo separates planner, reviewer, and workload executor calls so operators
can choose how much live agent work to spend:

| Mode | Planner | Reviewers | Workload packets | Transport |
|---|---:|---:|---:|---|
| `make self-evolving-org` with fixture runtime | 0 | 0 | 0 | no external calls |
| `make self-evolving-org-agent-demo AGENT_RUNTIME=codex` | 1 per run | 0 unless `AGENT_REVIEWER_RUNTIME` is set | 0 unless `SELF_EVOLVING_WORKLOAD_EXECUTOR_RUNTIME` is set | subscription/local CLI |
| `make self-evolving-org SELF_EVOLVING_RUNTIME=codex` | 1 per run | 3 per governed iteration | `SELF_EVOLVING_LIVE_WORKLOAD_LIMIT` per run, default 3 | subscription/local CLI |
| `make self-evolving-org-api-demo` | 1 per run | 0 | 0 | API model call |

`SELF_EVOLVING_FEEDBACK=compare` runs two arms, score-feedback and no-feedback,
so live invocation counts double. For example, a three-iteration live Codex
comparison with the default workload limit runs up to:

```text
(1 planner + 3 workload packet executors + 3 reviewers * 3 iterations) * 2 arms
= 26 subscription/local CLI invocations
```

The count can be lower if an arm stops early because reviewer aggregation
blocks a proposal or an operator budget/stop condition fires.

For a bounded live Codex run:

```bash
AGENT_RUNTIME=codex \
AGENT_ADAPTER=codex_exec \
SELF_EVOLVING_DEMO_ITERATIONS=2 \
SELF_EVOLVING_PLANNER_TIMEOUT_SECONDS=300 \
make self-evolving-org-agent-demo
```

To also run live reviewer offices through the same local/subscription CLI:

```bash
AGENT_RUNTIME=codex \
AGENT_ADAPTER=codex_exec \
AGENT_REVIEWER_RUNTIME=codex \
AGENT_REVIEWER_ADAPTER=codex_exec \
SELF_EVOLVING_DEMO_ITERATIONS=1 \
SELF_EVOLVING_PLANNER_TIMEOUT_SECONDS=300 \
SELF_EVOLVING_REVIEWER_TIMEOUT_SECONDS=120 \
make self-evolving-org-agent-demo
```

The company-state viewer should then show four live runtime offices:
`role.org_evolver`, `role.evaluator`, `role.risk_guardian`, and
`role.learning_steward`. `role.principal` remains the approval authority in
governed state.

To make a live runtime execute visible workload packets as well as propose the
structural mutation, set a workload executor runtime and a small packet limit.
Those packet runs are still kernel work items with action attestations; hidden
scorecards remain outside `demo-firm` under the run root's `operator-only/`
directory.

```bash
AGENT_RUNTIME=codex \
AGENT_ADAPTER=codex_exec \
AGENT_REVIEWER_RUNTIME=claude \
AGENT_REVIEWER_ADAPTER=claude_print \
SELF_EVOLVING_WORKLOAD_EXECUTOR_RUNTIME=claude \
SELF_EVOLVING_WORKLOAD_EXECUTOR_ADAPTER=claude_print \
SELF_EVOLVING_WORKLOAD_EXECUTOR_LIMIT=2 \
SELF_EVOLVING_DEMO_ITERATIONS=1 \
SELF_EVOLVING_DEMO_BUDGET_UNITS=1 \
make self-evolving-org-agent-demo
```

The Home / Company metrics include `live work packets`; Agent Work includes the
workload executor attestation and artifact refs. Keep the limit small for smoke
runs because each packet is a separate subscription/local CLI invocation.

For the stricter daemon-native live path:

```bash
AGENT_CLI=codex \
AGENT_ADAPTER=codex_exec \
SELF_EVOLVING_DAEMON_TIMEOUT=300 \
make self-evolving-daemon-live-governed-demo
```

The daemon-native target dispatches the subscription CLI through
`scripts/agent_daemon.py`, records a canonical `agent_cli_dispatch`
attestation, reads the daemon-written planner artifact, then sends exactly one
accepted planner step through the same governed mutation chain. It is the best
single-command proof that the demo is using daemon, role, task, A2A,
attestation, learning, and proof primitives together.

The daemon-native target also accepts the same optional reviewer runtime env:

```bash
AGENT_CLI=codex \
AGENT_ADAPTER=codex_exec \
AGENT_REVIEWER_RUNTIME=codex \
AGENT_REVIEWER_ADAPTER=codex_exec \
SELF_EVOLVING_DAEMON_TIMEOUT=300 \
SELF_EVOLVING_REVIEWER_TIMEOUT_SECONDS=120 \
make self-evolving-daemon-live-governed-demo
```

In this mode, the planner proposal comes from the daemon-dispatched
`org_evolver` worker, while evaluator, risk guardian, and learning steward are
spawned during the governed mutation path and recorded as reviewer evidence.

Run the API model-call fallback with the repo's existing API runtime:

```bash
make self-evolving-org-api-demo
MODEL_ID=gpt-4.1 make self-evolving-org-api-demo
MODEL_ID=gemini-2.5-flash make self-evolving-org-api-demo
MODEL_ID=deepseek-chat make self-evolving-org-api-demo
MODEL_ID=deepseek-reasoner make self-evolving-org-api-demo
MODEL_ID='openai-compatible:llama3.3' make self-evolving-org-api-demo
```

The API fallback is model-call based, not an agent CLI. It requires the matching
provider credentials: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`,
`DEEPSEEK_API_KEY`, or `OPENAI_COMPATIBLE_BASE_URL` plus
`OPENAI_COMPATIBLE_API_KEY`. For local/open-source servers, either pass
`MODEL_ID='openai-compatible:<model>'` or set `OPENAI_COMPATIBLE_MODEL`.
