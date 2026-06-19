# Decision Aggregation Cases

**Status:** first-party interface shipped.
**Module:** `cognitive_firm.orchestration.decision_aggregation`
**Tests:** `tests/test_decision_aggregation.py`, `tests/test_kernel_service.py`,
`tests/test_self_evolving_org_demo.py`

Decision aggregation records how an eligible set of humans, agents, or services
produced a recommendation or approval input. It does not allocate authority and
does not mutate organization state.

Use this when a decision path needs more than one input:

- advisory review before a principal decision;
- quorum over eligible role holders;
- veto review for risk or compliance;
- unanimity for charter, mandate, or other high-friction changes;
- a future expert-weighted, ranked-choice, or market-evidence procedure.

Voting is one possible decision rule. The kernel primitive is the aggregation
case: eligibility snapshot, procedure, positions, abstentions, result, and
evidence refs.

## Relation To Decision Rights

Decision rights answer: who may decide?

Decision aggregation answers: how were eligible inputs collected and computed
for this decision?

The output feeds existing surfaces such as governance-change approval evidence,
policy decisions, residual-decision review, accountability closure, or learning
candidates. A computed aggregation case is not enough to apply a structural
change by itself.

## Case Shape

Canonical state lives under:

```text
org/decision_aggregation/decision_aggregation_cases.jsonl
```

Fields:

| Field | Meaning |
|---|---|
| `case_id` | stable id |
| `subject_ref` | proposal, work item, policy candidate, residual decision, or review packet |
| `decision_class` | tenant-defined decision class |
| `scope_kind` / `scope_ref` | project, tenant, operating unit, resource class, etc. |
| `procedure_kind` | `single_authority`, `quorum_majority`, `veto`, or `unanimity` |
| `eligibility_basis` | mandate, charter, authority-domain, membership, or policy basis |
| `eligible_roles` / `eligible_actors` | fixed eligibility snapshot for this case |
| `positions` | one position per eligible actor/role pair; may be approve, reject, abstain, recuse, or veto |
| `result` | deterministic recommendation plus counts and quorum state |
| `downstream_ref` | optional target that will consume the recommendation |
| `evidence_refs` | source evidence for the case |

## Procedures

`single_authority`

- Requires exactly one non-abstaining eligible position.
- Approve maps to recommendation `approve`; reject or veto maps to `reject`.
- Otherwise escalates.

`quorum_majority`

- Requires at least `quorum` non-abstaining positions.
- Approvals exceeding rejections recommend `approve`.
- Rejections exceeding approvals recommend `reject`.
- Missing quorum or tie recommends `escalate`.

`veto`

- Any eligible `veto` position recommends `reject`.
- Without a veto, it falls back to quorum-majority behavior.

`unanimity`

- Requires the quorum to equal the eligible slot count.
- Every eligible slot must approve.
- Any rejection or veto recommends `reject`.
- Absence, abstention, or recusal recommends `escalate`.

## Procedure Profiles

`DecisionProcedureProfile` is a built-in recipe that expands into an ordinary
decision aggregation case. Profiles reduce adopter wiring but do not create a
second authority system. The case result is still evidence only unless a
mandate, charter, policy, or downstream governance path says otherwise.

Built-in profiles:

| Profile | Procedure | Quorum rule | Use |
|---|---|---|---|
| `single_authority` | `single_authority` | one | one named authority records a position |
| `majority` | `quorum_majority` | majority of eligible snapshot | lightweight advisory majority |
| `quorum_majority` | `quorum_majority` | explicit quorum, or majority of eligible snapshot when using the profile helper | ordinary quorum review |
| `unanimity` | `unanimity` | all eligible slots | high-friction changes where any dissent should block or escalate |
| `veto_review` | `veto` | explicit quorum, or majority of eligible snapshot when using the profile helper | risk/compliance review with a real veto signal |

Python helpers:

```python
from cognitive_firm.orchestration.decision_aggregation import (
    open_decision_aggregation_case_from_profile,
    resolve_decision_procedure_profile,
)
```

Use `resolve_decision_procedure_profile(...)` when a caller wants to inspect
the resolved procedure and quorum before opening a case. Use
`open_decision_aggregation_case_from_profile(...)` when the caller wants the
standard JSONL case row.

## Service Flow

```json
GET  /kernel/decision-procedure-profiles
POST /kernel/decision-aggregation-cases
POST /kernel/decision-aggregation-cases/<case_id>/positions
POST /kernel/decision-aggregation-cases/<case_id>/compute
POST /kernel/decision-aggregation-cases/<case_id>/route-escalation
GET  /kernel/decision-aggregation-cases
GET  /kernel/decision-aggregation-cases?resource=true
```

`GET /kernel/decision-procedure-profiles` is read-only and returns the built-in
profile recipes. It does not decide which profile applies to a tenant decision
class.

`POST /kernel/decision-aggregation-cases` accepts either an explicit
`procedure_kind` plus `quorum`, or a `procedure_profile` shortcut that resolves
to the same underlying fields. Callers may provide `case_id` when replay,
demo, or adapter idempotence requires stable references; otherwise the kernel
generates one.

Positions from ineligible actors or roles are rejected. Duplicate positions for
the same actor/role pair are rejected. Abstentions and recusals are recorded
separately from absence. Neither counts toward quorum. Callers may provide
`position_id` for stable receipts; otherwise the kernel generates one.

When `compute` produces an `escalated` case, callers may use
`POST /kernel/decision-aggregation-cases/<case_id>/route-escalation`. The route
packages quorum failure, abstention, recusal, veto/tie ambiguity, or missing
decision evidence as a normal `CapabilitySignal` and observer-only learning
candidate. This is useful for demos and adapters because the failed
coordination becomes durable evidence without being treated as an approved
decision. The route does not resolve the case, override the aggregation result,
approve a governance change, or mutate files.

## Terminal Userland

`cognitive-firm-userland` exposes the same service flow as thin terminal
carriers:

```bash
cognitive-firm-userland decision-profiles
cognitive-firm-userland decision-cases --status escalated
cognitive-firm-userland decision-open \
  --subject-ref governance_change:gcp_1 \
  --decision-class route_policy_change \
  --scope-kind tenant \
  --scope-ref tenant-a \
  --procedure-profile majority \
  --eligibility-basis "reviewer sample" \
  --eligible-role role.reviewer_a \
  --eligible-role role.reviewer_b \
  --eligible-role role.reviewer_c
cognitive-firm-userland decision-position dac_1 \
  --actor-id human.alice \
  --role-id role.reviewer_a \
  --position approve \
  --rationale "reviewed the evidence"
cognitive-firm-userland decision-compute dac_1
cognitive-firm-userland decision-route-escalation dac_1 \
  --summary "reviewer quorum failed" \
  --owner-role role.manager
```

The commands call kernel-service routes and print evidence summaries. They do
not decide authority, approve governance, dispatch work, or mutate files.
Write commands accept `--lease-id` and `--fencing-token` when the service runs
with required mutation leases.

## Boundary

The kernel owns:

- case record shape;
- eligibility snapshot;
- position validation;
- deterministic procedure computation;
- evidence/resource projection.

Tenants own:

- which procedure applies to which decision class;
- who is eligible;
- whether the result is binding, advisory, or escalatory;
- downstream approval policy.

Do not use this primitive as a second governance-change engine. Route its
result into the existing governance, policy, residual-decision, accountability,
or learning paths.

## Research Anchor

This primitive is grounded in:

- Simon, `Administrative Behavior`, and March and Simon, `Organizations`, for
  bounded rationality and organizations as decision systems. See
  <https://en.wikipedia.org/wiki/Administrative_Behavior> as a public index for
  Simon's book.
- Arrow, `Social Choice and Individual Values`, plus later voting-rule
  impossibility and manipulability results, for why voting is a procedure with
  conditions rather than a universal authority primitive. See Arrow's Nobel
  lecture, <https://www.nobelprize.org/prizes/economic-sciences/1972/arrow/lecture/>,
  and the book index at
  <https://en.wikipedia.org/wiki/Social_Choice_and_Individual_Values>.
- Grossman-Hart and Hart-Moore incomplete-contract work, for separating
  residual control rights from aggregation procedures.
- Distributed-systems agreement literature, including Lamport and
  Fischer-Lynch-Paterson, for deterministic replay, quorum failure, and
  ambiguity handling. See Fischer, Lynch, and Paterson,
  "Impossibility of Distributed Consensus with One Faulty Process",
  <https://doi.org/10.1145/3149.214121>.
- Human-computer interaction and human-work literature such as Suchman's
  `Plans and Situated Actions` and Amershi et al.'s human-AI interaction
  guidelines, for preserving situated human judgment, recusal, abstention, and
  receipts rather than reducing all human contribution to a button click. See
  Suchman's publication index,
  <https://en.wikipedia.org/wiki/Lucy_Suchman>, and Amershi et al.,
  "Guidelines for Human-AI Interaction",
  <https://doi.org/10.1145/3290605.3300233>.

These anchors justify the boundary, not a broad product claim: the kernel
records decision-procedure evidence, while authority remains in mandates,
charters, policy, residual rights, and approval paths.
