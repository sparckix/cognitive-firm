# A2H — Agent-to-Human Work Coordination

**Status:** shipped as a pattern over human work sessions.
**Module:** `cognitive_firm.orchestration.human_work`
**Tests:** `tests/test_human_work.py`

A2H defines the narrow case where a role office asks a human to do bounded
object-level work, then waits for or routes around the result. It is not a new
authority layer. It is a coordination pattern over H2A human work sessions, A2A
obligations, and accountability cases.

The protocol exists because humans in a cognitive firm are not only decision
gates. They may need to call a partner, inspect a private system, apply taste,
read a physical document, or make a legitimacy judgment. Those actions can be
substantive work even when the kernel cannot observe the work directly.

## Boundary

A2H is appropriate when all of these are true:

- a role office has a concrete need for bounded human work;
- the request can name the expected deliverable;
- the result can be handed back as a receipt, artifact reference, or bounded
  claim;
- the requesting role remains responsible for integration;
- any residual-risk or recourse boundary can be represented by an
  accountability case.

A2H is not appropriate for vague reminders, broad delegation to a human, or
attempts to transfer accountability from the role office to the human actor.

## Standard Record

Use `create_agent_requested_human_work_session(...)` for the standard shape.
It creates a human work session with:

- `requested_by=<role id>`;
- `agent_counterparty_role=<same role id>`;
- `human_actor=<human>`;
- `human_deliverable=<bounded output>`;
- `agent_followup_required=true`;
- `metadata.coordination_pattern="a2h_work_request"`;
- an initial `interaction_event` with
  `event_type="agent_requested_human_work"`.

When the request is carrying an A2A dependency, set
`obligation_id=<AgentMessage.message_id>`. This keeps the boundaries explicit:
A2A records the role-to-role obligation, A2H records the human work, and the
requesting role closes the obligation only after consuming the human result.

## Lifecycle

```text
role office detects human-required work
-> create A2H human work session
-> human claims / starts / blocks / completes / abandons
-> role office consumes receipt or artifact
-> role integrates result or records a blocker
-> accountability case if residual risk, recourse, or irreversible action was created
```

The human work lifecycle remains:

```text
requested -> claimed -> in_progress -> blocked -> handed_off | completed | abandoned -> integrated
```

For A2H read models, the lifecycle is split:

- `requested`, `claimed`, `in_progress`, `blocked`: waiting on human work or
  coordination;
- `handed_off`, `completed`: ready for role-office integration;
- `integrated`, `abandoned`: closed.

Receipt-required work cannot move to `integrated` until a receipt is present.
The receipt can be a note, artifact reference, external reference, or witness
claim, depending on the session's `receipt_type`.

For non-digitized or externally mediated human work, use
`append_human_work_receipt(...)`, `POST /kernel/human-work/{session_id}/receipt`,
or `cognitive-firm-userland receipt`. A structured receipt records a bounded
human claim:

- who is making the claim;
- the bounded summary needed for integration;
- receipt type and optional receipt reference;
- subject refs for the domain objects involved;
- artifact refs where durable evidence exists;
- observability, confidence, and review requirement.

This does not turn human work into machine-observed work. It makes the claim
explicit enough to review, sample, link to tenant-owned systems, or block
integration when the receipt is missing.

For "human reviewed this agent output" workflows, cite the agent output ref and
the action-attestation ref as receipt subjects. The receipt is human evidence;
it does not approve a governance change, execute a runtime step, or replace an
outcome link.

The key difference from a gate is that the human is producing or changing an
artifact, source claim, external-world fact, or judgment. The key difference
from ordinary delegation is that the agent remains the integration
counterparty and the organization records what kind of bottleneck occurred.

## Speed Rule

The kernel should not slow all agent work to human speed. It should let
agent-speed work proceed inside reversible, attested, mandate-bounded
envelopes, while surfacing human work only where the human is the correct actor:
authority, access, taste, relationship, safety, legitimacy, private judgment,
or physical-world contact.

Repeated A2H sessions with `bottleneck_class="labor"` or
`bottleneck_class="access"` are learning signals. They may justify tooling,
source-connector work, or a mandate change. Repeated A2H sessions with
`bottleneck_class="authority"`, `"taste"`, `"relationship"`, or `"safety"` may
be healthy constraints rather than automation targets.

The kernel exposes this as a read model through
`summarize_a2h_work_pressure(...)`, `GET /kernel/human-work-pressure`,
`cognitive-firm-userland human-pressure`, the organization surface, work
discovery, and Orbit/adopter-built surfaces. The default pressure threshold is
deliberately small: three active sessions for the same
`(agent_counterparty_role, bottleneck_class)` group, any stale session, or any
missing required receipt. Tenants can make the threshold stricter without
changing the protocol. Service callers should use `tenant_id` and `project_id`
selectors when reading multi-tenant logs; the route applies those filters
before grouping pressure.
Whole-firm pressure groups can also enter the conservative learning path via
`GET /kernel/learning-transition-candidates?source=human_work` or
`cognitive-firm-userland learning-candidates --source human_work`; these rows
remain observer-only review candidates and do not reroute or close sessions.

## Resource Projection

The human-work JSONL row remains canonical state. `human_work_resource(...)`
projects a session into the common [Resource Envelope](resource-envelope.md) so
adapters, dashboards, migration checks, and conformance fixtures can read A2H
state with the same object shape as other kernel resources.

The projection carries:

- `spec`: requested actor, human actor, objective, work mode, bottleneck,
  receipt policy, obligation, interaction surface, deliverable, and follow-up
  routing;
- `status`: lifecycle state, receipt presence, completion summary,
  integration ref, note count, interaction-event count, work receipts, and
  timestamps;
- `links`: requested role, human actor, collaborating roles, artifacts,
  obligation, integration ref, follow-up refs, and receipt refs where
  present.

CLI readers can emit either canonical rows or resource envelopes:

```bash
python -m cognitive_firm.orchestration.human_work list --resource
python -m cognitive_firm.orchestration.human_work followup --resource
```

`followup` is a read-only view over sessions in `handed_off` or `completed`
state with `agent_followup_required=true`. It is the "prepared, not committed"
state for A2H: the role office can see the human result is ready to consume,
including whether a required receipt is missing, but the command does not
schedule, assign, integrate, approve, or close the work.

The command-path conformance fixture exercises the same CLI path, the
ready-for-agent follow-up view, and the receipt-before-integration invariant:

```bash
make a2h-command-conformance
```

## Routing and Pre-Work Surfacing

A2H sessions appear in three places:

- `build_org_surface(...)` returns `a2h_waiting_on_human_sessions`,
  `a2h_followup_sessions`, `a2h_missing_receipt_sessions`, and `a2h_pressure`;
- `format_surface_brief(...)` prints A2H waiting, follow-up, missing receipts,
  and pressure groups;
- `GET /kernel/human-work-pressure` and `cognitive-firm-userland
  human-pressure` expose the same pressure groups as an observer-only surface;
- `GET /kernel/learning-transition-candidates?source=human_work` and
  `cognitive-firm-userland learning-candidates --source human_work` compile
  whole-firm pressure groups into observer-only review candidates;
- `discover_human_work_sessions(...)` routes sessions back to
  `agent_counterparty_role` after the human has handed off or completed the
  work.

This is the minimum useful integration. Role offices can see "I asked the
human for work," "I am waiting," and "now I need to integrate it" without
adding another scheduler or making the principal a universal blocking gate.

Orbit also exposes the pattern in the Human Work pane. Creating an
agent-requested session sets the standard fields and adds the initial
`agent_requested_human_work` interaction event. Orbit follows the same state
split and receipt-before-integration invariant as the kernel helper.

## Accountability

Use an accountability case when the human work creates or accepts residual risk:

- irreversible external action;
- recourse owed to another party;
- externality-bearing decision;
- authority-envelope exception;
- high-impact taste or legitimacy call;
- blocked review SLA.

The accountability case names the accountable role, decision-right basis,
recourse path, residual-risk owner, and closure evidence. The A2H session
records the work; the accountability case records who owns closure.

## Receipt, Retention, And Sampling

The default public kernel records bounded claims, receipts, and artifact
references. It does not store private transcripts by default.

Recommended T1 defaults:

- `receipt_required=true` for agent-requested work;
- `receipt_type="note"` unless an external reference or artifact exists;
- `sample_for_review=false` for ordinary low-risk work;
- `sample_for_review=true` for unobservable, relationship, safety, or
  authority work where repeated claims become consequential.
- use `GET /kernel/human-speed-envelope` or
  `cognitive-firm-userland speed-envelope` when the operator needs an explicit
  accountable-speed recommendation before choosing agent speed, sampled review,
  batched human review, a pre-action gate, or accountable closure.

T2 adopters should add tenant policy for:

- domain-specific receipt types;
- retention windows;
- redaction before external review;
- sampling rates by risk tier and bottleneck class;
- escalation from missing receipt to accountability case.

## Examples

Restricted source check:

```python
create_agent_requested_human_work_session(
    requested_by_role="role.researcher",
    human_actor="principal",
    objective="Check the restricted source and report whether it supports the claim.",
    work_mode="source_check",
    bottleneck_class="access",
    human_deliverable="bounded source-support claim",
    obligation_id="msg_...",
    receipt_required=True,
    receipt_type="note",
)
```

Partner call:

```python
create_agent_requested_human_work_session(
    requested_by_role="role.manager",
    human_actor="principal",
    objective="Call the partner and confirm whether Friday review is realistic.",
    work_mode="relationship",
    bottleneck_class="relationship",
    human_deliverable="timeline claim plus any blocker",
    interaction_surface="offline",
)
```

Structured receipt:

```bash
python -m cognitive_firm.orchestration.human_work receipt hws_123 \
  --actor principal \
  --summary "The restricted source supports the claim within the requested scope." \
  --receipt-type artifact_ref \
  --subject-ref source://restricted/source-a \
  --artifact-ref artifact://redacted-source-note
```

Taste or legitimacy call:

```python
create_agent_requested_human_work_session(
    requested_by_role="role.editor",
    human_actor="principal",
    objective="Review whether this public phrasing is acceptable for the audience.",
    work_mode="taste_call",
    bottleneck_class="taste",
    human_deliverable="accept / revise / reject plus short reason",
)
```

## Anti-Patterns

- Treating the agent as the human's manager. The agent coordinates work inside
  a mandate; it does not become the principal.
- Recording private reasoning or full relationship transcripts by default.
- Asking for broad, unbounded human work without a deliverable.
- Closing an A2A obligation before the A2H result is integrated.
- Using A2H to launder accountability for an agent decision.
- Turning every uncertainty into a human request instead of using evidence
  gaps, artifact dependencies, or bounded autonomous work.

## Threat-Model Coverage

| Risk | T1 behavior | T2 path |
|---|---|---|
| Invisible human bottleneck | Human work session records objective, bottleneck class, state, and follow-up | Add SLA dashboards and sampling policy |
| Non-digitized work | Bounded observability plus optional structured receipt with subject, artifact, witness, or external refs | Add stronger receipt policy by domain |
| Agent over-requesting humans | Bottleneck classes surface repeated labor/access requests | Add allocation policy and rate limits |
| Accountability laundering | Pair with accountability cases at residual-risk boundaries | Add role-specific recourse and review SLAs |
| Privacy overcapture | Store bounded claims and artifact refs, not transcripts by default | Add retention policy and redaction workflow |
