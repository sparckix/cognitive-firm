# Blueprints

Blueprints are small compositions of existing primitives. They are not new
kernel mechanisms. Use them when you know the workflow you want but do not yet
know which protocols to combine.

## Choose A Blueprint

| If you need to... | Start with | Kernel surfaces |
|---|---|---|
| Let a graph/runtime pause for human input | Runtime with human interrupt | runtime adapter, run checkpoints, A2H, human work |
| Safely call an external system | External-system write | MCP, capability tokens, outbox relay, app integration |
| Turn repeated failures into future behavior | Incident to learning event | org surface, strategy office, learning compiler, learning events |
| Add a second human or service actor | Small-team actor membership | identity provider, actor identity, actor membership, leases |
| Let a dashboard or app mutate state | App surface mutation | app intent, actor context, kernel service, org surface |
| Decide whether to record a human action | Human-work rubric | H2A, A2H, human work, accountability cases |

For a fuller multi-actor version of the small-team pattern, read
`docs/blueprints/multi-actor-authority.md`.

## Runtime With Human Interrupt

Use when LangGraph, Temporal, an agent loop, or another runtime must stop and
ask a human for bounded work.

Minimum path:

1. Runtime emits `interrupted`.
2. `record_runtime_event` records the checkpoint.
3. A2H creates a human-work session with deliverable and deadline.
4. Human submits receipt.
5. Runtime resumes through its own resume token.

Do not put graph scheduling or retry policy in the kernel. The kernel records
the organization state created by the interrupt.

## External-System Write

Use when a role wants to mutate Linear, GitHub, Salesforce, an ERP, or another
system.

Minimum path:

1. Role proposes an MCP call.
2. Capability token and mandate authorize the call.
3. Outbox relay records the request.
4. Provider adapter executes or projects the result.
5. Follow-up event records success, failure, or review need.

Provider schemas and business rules stay in the tenant/app adapter.

## Incident To Learning Event

Use when the same failure mode keeps recurring.

Minimum path:

1. Evidence gap, forecast miss, externality, accountability case, or strategy
   finding appears on the organization surface.
2. Learning compiler creates a candidate.
3. Tenant review decides whether it is real.
4. Approved learning event records the behavior change.
5. Tenant policy, mandate, or source practice changes outside the kernel.

The learning event is not a memo. It is the durable record that future behavior
changed or should change.

## Small-Team Actor Membership

Use when more than one human or service can act in the same firm.

Minimum path:

1. Identity provider authenticates the subject.
2. Actor identity maps subject facts into a kernel actor.
3. Actor membership grants scoped role authority.
4. Kernel service checks subject scope and role membership.
5. Mutation records actor context and resulting state.

IdP lifecycle administration remains tenant-owned.

## App Surface Mutation

Use when Orbit, Telegram, CLI, the kernel service, or a tenant-built app needs
to write kernel state.

Minimum path:

1. App sends an intent.
2. Kernel service reconstructs actor context.
3. Service checks membership, scope, policy, and lease.
4. Primitive writes the record.
5. Org surface projects the result.

The app should not write durable kernel files directly.

For a worked example, read
`docs/examples/app-service-integration-example.md`.

## Human-Work Rubric

Use this to decide what to record.

| Situation | Record as |
|---|---|
| Human must perform bounded work with deliverable | Human work session |
| Human must approve or reject a machine proposal | Gate or policy decision |
| Human accepts residual risk or owns recourse | Accountability case |
| Human adds ordinary context with no durable obligation | Tenant note or app comment |
| Human changes future operating behavior | Learning event or governance change |

Over-recording creates noise. Under-recording hides the real bottleneck. The
test is whether the action creates an obligation, authority change, evidence
claim, or future behavior change.
