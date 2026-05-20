# Organizational Learning Loop

**Status:** public architecture guide.

In cognitive-firm, organizational learning means a durable change to future
work: dispatch, review, authority, or allocation changes because of something
the organization learned. It is not agent memory, and it is not a lessons
learned paragraph that no one has to read later.

## Loop

```text
work artifact
-> review, forecast scoring, operator decision, or damage signal
-> typed state object
-> deterministic or operator-reviewed transition
-> changed future behavior
```

The state object carries the learning. Common carriers are:

- mandate update;
- project charter update;
- evidence gap;
- forecast record or calibration row;
- action-impact row;
- action attestation;
- damage signal;
- human work session;
- accountability case;
- A2A obligation;
- artifact dependency;
- route or task update;
- organization surface read;
- strategy-office finding;
- learning-transition candidate;
- approved learning event;
- tenant-specific policy adapter change.

## Why This Matters

When agent systems get stuck, a common response is to surface more context,
more patterns, or more past notes. That can help, but it does not compound by
itself. The organization improves only when a finding becomes state that future
work has to encounter.

This is the software version of a familiar organizational-learning distinction:
one change fixes an action, a deeper change fixes the rule behind the action,
and routines carry learning across people and time. The kernel represents those
changes as typed files, channels, ledgers, gates, and adapters.

## Evidence Feedback

Evidence feedback is the state transition for "the evaluator learned that the
organization lacks an external fact, source, or adversarial comparison." It
should start as a typed gap, not as autonomous web retrieval.

The public kernel ships a small filesystem adapter at
`cognitive_firm.orchestration.evidence_gaps`. It can create, list, filter, and
update typed evidence gaps. Tenants can replace the adapter or bind sourcing
workflows to it.

A useful evidence gap includes:

- producer provenance, such as reviewer, evaluator, adjudicator, or operator;
- the claim or artifact that triggered the gap;
- the missing fact or source class;
- an adversarial fetch direction;
- the tenant/project it applies to;
- whether the gap is blocking, useful, or archival.

Autonomous sourcing becomes appropriate only after repeated gaps show that
operator sourcing time, not judgment quality, is the bottleneck.

## Charter Feedback

Charter feedback is the state transition for "the project is no longer aligned
with its intended object." It should update the project charter or an anchor
proxy, not merely tell the next agent to be careful.

Examples:

- add an out-of-scope clause after repeated adjacent-work drift;
- add an anchor proxy after a deliverable answered a weaker nearby question;
- change an end state after the original stop condition became ambiguous.

## Forecast Feedback

Forecast feedback is the state transition for "the organization learned about
its allocation judgment." A forecast market is useful when it updates routing,
not just when it stores probabilities.

Forecast records should be able to drive:

- run now;
- split the project;
- ask another independent agent;
- defer;
- kill the branch;
- request evidence before execution.

Calibration rows, high-confidence misses, and effort deltas are learning
objects because they change how future forecasts are weighted.

## Action-Impact Feedback

Action-impact feedback is the state transition for "the organization learned
what happened after an intervention." It is different from a forecast: the
forecast records belief before action, while the impact row records what was
done, what would otherwise have happened, what changed, what it cost, and what
externalities appeared.

The public kernel ships a read-model interface at
`cognitive_firm.orchestration.action_impact`. Tenants can use it for scientific
yield, business impact, throughput, or other measured outcomes.

Bandit or mini-RL policies may be useful when actions repeat and rewards are
measurable. They should remain tenant-owned. The kernel exposes enough fields
for offline evaluation, but it does not turn local reward rows into autonomous
routing authority.

## Human Work Feedback

Human work feedback is the state transition for "the organization learned that
the human is doing object-level work, not only approving agent work." A human
work session records the objective, actor, bottleneck class, artifacts, blocker,
handoff, completion, and integration reference.

Agent-to-human work coordination is the standard pattern for role offices to
request that work. The role names the deliverable, receipt expectation,
deadline if any, and linked obligation if another role is blocked on the
result. The role remains responsible for integration; the human work session
records the bounded contribution.

The organization surface separately exposes A2H work waiting on a human, A2H
work ready for agent follow-up, missing required receipts, and repeated
pressure by role and bottleneck class. This lets future work see whether a
human-work item is a healthy boundary condition or a repeated access/labor
bottleneck that should become tooling, source-connector work, or a mandate
change.

For non-digitized human work, the kernel records observability and receipt
metadata instead of pretending to observe the work directly. A completed phone
call, offline source read, or private judgment can be represented as a bounded
attestation with optional receipt and review sampling.

This makes human contribution and delay measurable without treating all human
delay as bad. Some bottlenecks are healthy: authority, taste, relationship
work, and safety review may intentionally remain human. Repeated labor or
access bottlenecks may point to tooling or delegation work.

## Action Attestation Feedback

Action attestation feedback is the state transition for "the organization
learned what an agent, runtime, tool, or script actually produced." It is the
machine-side counterpart to a human work receipt.

An action attestation records subject kind, subject reference, digest,
producer, runtime/tool/policy refs, input/output refs, verification status,
and optional signature or transparency-log refs. The row does not prove the
artifact is correct. It makes the action reviewable, repeatable, and
attachable to later evidence review, incident review, or release policy.

Use human work sessions for bounded human claims. Use action attestations for
machine-side provenance.

## Accountability Feedback

Accountability feedback is the state transition for "this item crossed from
ordinary follow-up into accountable closure." The accountability summary shows
what needs attention; an accountability case records decision right, authority
envelope, accountable role, responsible actor, risk tier, recourse path,
residual-risk owner, SLA, and closure evidence.

This is where the kernel handles the speed mismatch between agents and humans.
The goal is not to force every agent action through a human. The goal is to
let agent-speed work proceed inside bounded, reversible, attested envelopes,
while humans or accountable roles remain at the boundaries where residual risk,
irreversible action, taste, legitimacy, recourse, or externalities are created.

If agent throughput exceeds accountable review capacity, the correct response
is to cap, queue, sample, sandbox, or split responsibility. Rubber-stamped gates
are not accountability.

## Organization Surface

The organization surface is the read side of the learning loop. It does not
create new authority and it is not an app-specific view. It joins current
kernel state so a human, role office, or dashboard can see:

- blocking evidence gaps;
- open evidence gaps;
- active and waiting human work sessions;
- blocked A2A obligations;
- recent damage signals;
- invalid project charters;
- forecast-market health and score debt;
- action-impact review items and local negative externalities;
- observer-only strategy-review findings;
- governed self-modification proposals;
- learning-transition candidates;
- approved learning events.

This makes learning carriers operational. A finding that has been translated
into a state object becomes visible before future work starts; a finding that
remains only in prose does not.

## Strategy Office Feedback

Strategy-office feedback is the state transition for "the organization learned
that its current routing, source instrumentation, or optimization target needs
review." It sits above forecast and action-impact feedback:

- forecast feedback records belief and calibration before action;
- action-impact feedback records what happened after action;
- strategy-office feedback records what should be inspected because those
  surfaces reveal source-health gaps, debt, externalities, or repeated misses.

The public kernel exposes this as an observer-only interface, not as a mandatory
new role. Tenants decide whether a manager, reviewer, research director,
principal, or dedicated office reviews the findings.

## Learning Transition Compiler

The learning-transition compiler is the conservative bridge from review finding
to possible state change. It reads the organization surface and emits
reviewable candidates such as:

- evidence gap;
- project charter update;
- mandate review;
- human work session;
- forecast contract;
- source repair;
- role review.

The compiler does not apply those candidates. It exists so organizational
learning has a concrete next object to review, without letting an automated
optimizer rewrite governance state.

## Approved Learning Events

Approved learning events are the promotion target after a candidate has been
reviewed. They record a durable behavior-change event:

```text
source carriers
-> learning-transition candidate
-> review / approval
-> approved learning event
-> tenant-owned application of the referenced change
```

An approved learning event includes decision-use, source-carrier refs,
before/after state, approval ref, externality-review ref, owner, and future cue
for reuse. It does not apply the underlying mutation. Tenants decide how a
route, mandate, charter, evidence standard, review threshold, routine, or policy
adapter actually changes.

Approved learning events also have a lifecycle: `active`, `superseded`, or
`retired`. Replay returns only active events and uses deterministic role,
tenant/project, and cue filters. Tenant/project replay includes global events
unless an event is explicitly scoped to a different tenant or project.

## Accountability And Local Review

The accountability summary is the follow-up surface for learning carriers. It
joins owner, project, review status, due date, externality tags, and source
references so a role or human can see what still needs attention.

For significant primitive additions or policy changes, local review artifacts
can preserve multiple lenses before promotion. Useful lenses include org
design, economics, history, philosophy, biology, systems engineering, safety,
operator burden, and domain expertise. Concrete review artifacts live in the
gitignored `reviews/` workspace; durable conclusions can be promoted into docs
or tenant policy after review.

## Kernel and Tenant Split

The public kernel owns the carriers and transition discipline. Tenants own the
content:

- what counts as evidence;
- what anchors a project;
- who may approve a mandate change;
- which domains need probabilistic forecasts;
- which outcomes are safe enough to measure as action impact;
- which failure modes deserve escalation.

This split lets different organizations use the same learning loop without
sharing private policy or domain content.

## Anti-Patterns

- Writing a retrospective that no future dispatcher or reviewer is required to
  read.
- Adding more primitive names to prompts instead of changing a state object.
- Letting a role update its own mandate without review.
- Treating semantic similarity as a substitute for deterministic anchors.
- Moving tenant-specific policy into public kernel docs or code.
