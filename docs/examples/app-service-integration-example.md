# App-Service Integration Example

This example shows how a dashboard, Slack app, Linear app, or custom internal
tool should mutate kernel state.

The rule is simple: apps project state and submit intents. They do not write
durable kernel files directly.

## Flow

```text
app intent
  -> kernel service
  -> actor context
  -> membership + subject-scope check
  -> optional lease check
  -> primitive mutation
  -> organization-surface projection
```

## Minimal Actor Context

An app request should carry enough authenticated context for the kernel service
to reconstruct an actor:

```json
{
  "actor_context": {
    "actor_id": "actor.alice",
    "subject": "alice@example.com",
    "role_id": "role.manager",
    "tenant_id": "example"
  }
}
```

In production, the app should not invent this context. It should come from an
identity provider adapter, gateway-verified headers, or a tenant-owned
authentication layer.

## Example Mutation

A dashboard wants to resolve a gate. It sends a mutation request to the kernel
service. The service checks:

1. the bearer token if enabled;
2. the actor identity;
3. the actor's scoped role membership;
4. subject scope if configured;
5. a lease if mutation leases are required.

Only then does the gate primitive write durable state.

## Expected Result

After the mutation, readers should inspect the organization surface rather than
the app's local state:

```bash
python -m cognitive_firm.orchestration.org_surface
```

The app can render that projection back to the user. If the projection does not
show the change, the app should treat its local optimistic state as uncommitted.

Executable check:

```bash
make app-service-integration-smoke
```

This fixture registers an actor, grants scoped membership, acquires a lease,
submits a service mutation, and verifies the organization surface reflects the
new human-work session.

## Boundary

The app owns layout, user sessions, provider OAuth screens, optimistic UI state,
app-specific error copy, and tenant-specific routing rules.

The kernel owns actor authority, mutation preconditions, durable records,
replayable state, audit surfaces, and accountability surfaces.

## Common Mistakes

| Mistake | Why it fails |
|---|---|
| App writes JSONL files directly | Bypasses actor, membership, lease, and audit checks. |
| App treats local state as truth | Creates split-brain state when the kernel rejects a mutation. |
| App uses an IdP group as kernel authority | IdP groups authenticate or classify subjects; kernel membership grants organizational authority. |
| App hides rejected mutations | Rejections are governance signals and should be visible to the user or operator. |
