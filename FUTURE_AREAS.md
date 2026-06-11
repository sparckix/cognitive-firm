# Future Areas

This note is for the implementation repository. It translates the companion
paper's research agenda into kernel-level work that should remain generic,
testable, and separate from tenant policy.

The kernel should not claim to invent organizational learning or human-AI
teaming. Its distinctive implementation role is narrower: provide typed,
auditable machinery for turning agent and human-agent work into governed
organizational state.

## Current Implementation Thesis

`cognitive-firm` is a governance kernel with a first-party governed work
runtime. Its strongest implementation claim is:

> Probabilistic agents can propose, execute, and summarize work, but durable
> organizational authority should pass through typed state, deterministic
> checks, source-linked evidence, and principal-approved transitions.

The kernel currently supports this through:

- role offices and mandates;
- H2A and A2A protocol surfaces;
- first-party work discovery, execution routing, and CLI/tool dispatch;
- project charters;
- evidence gaps;
- human work sessions;
- forecast-market and action-impact read models;
- source connectors and runtime adapters;
- organization surface projections;
- strategy-office findings;
- learning-transition candidates;
- approved learning events;
- accountability summaries.

## Implementation Directions

### 1. Proposition-To-Artifact Traceability

Create a traceability matrix that maps the companion paper's main propositions
to implementation artifacts:

```text
paper proposition
-> kernel primitive
-> protocol doc
-> test
-> smoke command
-> evidence artifact
```

This makes the repo auditable as an implementation of the theory rather than a
pile of adjacent primitives.

### 2. Learning-Event Replay

Approved learning events are now durable records, but the next step is replay:
future pre-work surfaces should show which approved events are relevant to the
current project, role, route, or failure mode.

The kernel-level version should stay conservative:

- match by explicit refs, tags, role, project, tenant, and future cue;
- do not use semantic similarity as authority;
- produce a projection, not an automatic route mutation;
- let tenants decide whether a replayed event blocks, warns, or informs.

### 3. Governance Benchmark Fixtures

Add small benchmark fixtures that compare governed and ungoverned execution
shapes:

- self-evaluation trap;
- scope-drift trap;
- context-contamination trap;
- fake-compliance trap;
- metric-inflation trap;
- unauthorized-write trap;
- stale-routine trap.

Each fixture should have expected outcomes for U-form, weakly gated, and
M-form-style governed execution. The goal is not leaderboards; it is regression
coverage for the kernel's reason to exist.

### 4. Attestation Bundles

Define a portable attestation bundle for governed runs:

- contract hash;
- input state hash;
- role and mandate hash;
- verifier version;
- event stream ref;
- output artifact refs;
- pass/fail verdict;
- caveats;
- operator approval refs.

This is the implementation analog of independent audit: a third party should be
able to inspect what was checked without asking the agent to summarize its own
compliance.

### 5. Tenant Overlay Conformance

Add fixtures that prove a tenant overlay can be mounted, inspected, smoked, and
removed without contaminating the public kernel.

Good conformance tests:

- example tenant loads without private paths;
- tenant forecast/action-impact summaries feed the org surface;
- tenant policy does not enter public docs;
- symlink teardown restores kernel defaults;
- missing tenant files fail with actionable errors.

### 6. External Runtime Conformance

The kernel should remain compatible with LangGraph-style, CrewAI-style,
AutoGen-style, and custom runtimes through runtime adapters, not by absorbing
their execution models.

Add fixtures that verify:

- a runtime can emit started/checkpointed/failed/completed events;
- run checkpoints derive the same projection;
- org surface consumes the projection;
- H2A interrupts become typed kernel state, not runtime-specific chat.

### 7. Organizational Forgetting

Approved learning events need lifecycle mechanics:

- active;
- superseded;
- retired;
- review-after date;
- superseding event ref;
- retirement rationale.

The kernel should make forgetting explicit because stale routines are a failure
mode, not just clutter.

### 8. Local Review Workspace Discipline

Keep synthetic panels, adversarial reviews, and research payloads under the
gitignored `reviews/` workspace. Promote only durable conclusions into public
docs, tests, or kernel state.

The kernel should support local review discipline without presenting every
review method as a shipped primitive.

### 9. Multi-Authority T2 Boundary

T1 is single-authority. T2 should not be a vague enterprise mode; it should
activate only when the repo has:

- signed policy changes;
- approval quorums;
- role-bound authority;
- conflict resolution;
- identity provider integration;
- audit-preserving database backend;
- cross-device and cross-operator threat model.

Until then, multi-authority support should remain a documented boundary, not an
implicit promise.

### 10. Kernel/App/Tenant Boundary Tests

Add tests that fail when implementation layers blur:

- app surfaces cannot directly mutate mandates unless a kernel intent allows it;
- tenant policy cannot become a default kernel rule;
- runtime adapters cannot become state backends;
- notification providers cannot become durable state;
- MCP connectors cannot bypass capability tokens.

These boundary tests are the implementation version of the OS / Config / App
theory.

## Near-Term Priority

The highest-leverage next sequence is:

1. learning-event replay projection;
2. proposition-to-artifact traceability matrix;
3. tenant overlay conformance fixture;
4. external runtime conformance fixture;
5. attestation bundle schema;
6. organizational forgetting lifecycle.

That sequence strengthens the repo's core claim without broadening scope beyond
a small, auditable governance kernel.
