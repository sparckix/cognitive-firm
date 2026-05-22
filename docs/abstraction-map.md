# Abstraction Map

`cognitive-firm` is a governance kernel. It should own durable organizational
mechanisms, not tenant strategy, app workflow, or model execution.

## Layer Model

| Layer | Owns | Does not own |
|---|---|---|
| Kernel primitives | authority, state transitions, obligations, evidence, human work, attestations, accountability, learning records | domain policy, scoring, UI workflow |
| Protocols | H2A, A2H, A2A, MCP, runtime adapters, inbound events, app integration, state backends, distribution, extension schemas | provider-specific product behavior |
| Service boundary | local HTTP/API surface over kernel primitives, actor context, leases, policy checks, attention/vocabulary routes | enterprise IAM administration or graph-runtime scheduling |
| Runtime adapters | projection of external runtime lifecycle into kernel state | execution graph semantics, model inference, retry policy inside the runtime |
| Distribution layer | versioned distro/overlay packages with `add`/`replace`/`patch` composition, package registry, transactional git-backed installer, verifier, rollback, governed overlay install (authority-diff), git-URL fetch + lockfile, `extends` inheritance, `lint`/`--dry-run` | the kernel itself; the installer only writes adopter-owned overlay files; a package may not widen a role's authority |
| Userland | operator/member-human-facing layer over the kernel: enrollment, attention router, action queues, surface-policy inspection, vocabulary spine — pure functions over kernel logs and the kernel service, with the `cognitive-firm-userland` CLI and an Orbit `NeedsMePane` | durable state; it is an assembly layer, never a kernel primitive |
| App surfaces | Orbit, Telegram, CLI, plus tenant-built Slack/Teams/Linear/GitHub adapters | durable source of truth |
| Tenant overlay | role mandates, project charters, local metrics, private connectors, workflow-specific policy | reusable kernel mechanism |

## What Belongs In The Kernel

Keep a feature in the kernel when it is a reusable organizational mechanism:

- it records who had authority to act;
- it changes durable organization state;
- it creates a reviewable obligation, evidence gap, or accountability case;
- it records human work or machine provenance;
- it promotes a recurring finding into approved future behavior;
- it defines an adapter contract without embedding tenant policy.

Examples: actor identity, actor membership, leases, H2A/A2H/A2A, MCP
capabilities, inbound-event quarantine, run checkpoints, action attestations,
accountability cases, learning events, state-surface inventory, operating-unit
contracts and the durable work-item queue, outcome links, routine reviews,
governed resource allocation, and residual decision rights.

The extension-schema mechanism (`validate_payload`) is a kernel module written
once, but the schemas it enforces are config a package ships — adding a
validated custom type never requires a kernel change. A distro or overlay is
also config: roles, mandates, preferences, operating units, and charters an
adopter edits to match their firm.

## What Belongs Outside The Kernel

Keep a feature in app/config/tenant space when it is policy or product logic:

- scientific-yield scoring, P&L attribution, or domain-specific metrics;
- forecast-market implementation details;
- optimizer or bandit policy;
- enterprise SSO setup and IdP administration;
- app UI workflows and product screens;
- Linear/GitHub/Salesforce object taxonomies;
- jurisdiction-specific compliance interpretations;
- tenant source connectors and private evidence rules.

The kernel may expose an interface for these. It should not make a public
default that only fits one organization.

## Five Canonical Flows

### Runtime With Human Interrupt

Runtime emits `interrupted` -> kernel records a run checkpoint -> A2H creates a
human-work session -> human submits a receipt -> runtime resumes with its own
resume token.

Read: `docs/examples/langgraph-runtime-adapter.md`,
`docs/examples/a2h-workflow-demo.md`.

### External-System Write

Role requests an MCP action -> capability check passes -> outbox relay writes a
request event -> provider adapter executes -> deterministic projection records
what changed or what needs review.

Read: `docs/protocols/mcp.md`, `docs/protocols/app-integration.md`.

### Incident To Learning Event

Evidence gap, forecast miss, externality, accountability case, or strategy
finding appears on the organization surface -> learning compiler proposes a
candidate -> tenant reviews -> approved learning event records the behavior
change.

Read: `docs/examples/learning-loop-demo.md`,
`docs/organizational_learning_loop.md`.

### Small-Team Actor Membership

External IdP authenticates a subject -> actor identity maps subject to a kernel
actor -> actor membership grants scoped role authority -> kernel service
accepts or denies mutations based on role, subject scope, and lease.

Read: `docs/protocols/identity-providers.md`,
`docs/protocols/actor-membership.md`, `docs/protocols/kernel-service.md`.

### App Surface Mutation

App sends a kernel intent -> service reconstructs actor context -> service
checks membership, scope, and lease -> primitive writes state -> org surface
projects the result back to humans and roles.

Read: `docs/protocols/kernel-service.md`, `docs/protocols/app-integration.md`.

## Design Test For New Additions

Before adding a primitive, ask:

1. Which invariant from `docs/kernel-invariants.md` does it serve?
2. What is the durable state record?
3. Who writes it, who reads it, and what fails if it is absent?
4. Is this mechanism reusable across tenants?
5. Could this be an app/tenant blueprint instead of a kernel primitive?

If the answer is mostly tenant-specific, keep it in an overlay and expose an
interface only after repeated use.
