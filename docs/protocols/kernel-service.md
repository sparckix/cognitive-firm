# Kernel Service

**Status:** local service adapter shipped.
**Module:** `cognitive_firm.kernel_service`
**Tests:** `tests/test_kernel_service.py`

The kernel service is a small HTTP boundary over Python kernel functions. It is
not a second backend and not a new source of truth.

Use it when an app surface, script, or local operator wants to call kernel
commands without importing Python modules directly.

## Boundary

The service owns transport:

- HTTP request parsing;
- JSON response envelopes;
- route dispatch;
- process hosting.

The kernel primitives own behavior:

- state transitions;
- validation;
- receipt and accountability invariants;
- organization-surface projection.

This keeps Orbit, Slack/Teams adapters, CLI wrappers, and future dashboards
from reimplementing primitive lifecycle rules.

## Current Routes

```text
GET  /health
GET  /kernel/org-surface
GET  /kernel/accountability-summary
GET  /kernel/attention/{actor_id}
GET  /kernel/vocabulary
POST /kernel/actors
POST /kernel/memberships
POST /kernel/memberships/{assignment_id}/revoke
POST /kernel/leases
POST /kernel/leases/{lease_id}/release
POST /kernel/mutation-events
POST /kernel/human-work
POST /kernel/human-work/{session_id}/state
POST /kernel/human-work/{session_id}/interaction
POST /kernel/accountability-cases
POST /kernel/a2a/messages
POST /kernel/gates/{gate_id}/resolve
POST /kernel/directives
POST /kernel/controls
POST /kernel/chat/messages
POST /kernel/roles/{role_id}/agent-utilization
```

Run locally:

```bash
cognitive-firm-kernel-service --host 127.0.0.1 --port 8765
```

The service is stdlib-only. A tenant may wrap the same dispatch layer with
FastAPI, a trusted gateway, or a cloud runtime later, but that should remain
an adapter choice.

## Startup Viability

For a startup, the first viable deployment is:

```text
Python kernel functions
-> local kernel service
-> Orbit / CLI / notification surfaces
-> filesystem SourceConnector + Git audit/sync
```

This is appropriate for one principal or a small trusted operator set on one
deployment. Git is audit, rollback, and synchronization. It is not the runtime
message bus.

Move to SQLite, Postgres, or another event backend when multiple active
operators need concurrent writes, stronger leases, or compliance evidence.

## Identity, Attribution, And Leases

Research and standards point to a split boundary:

- Authentication and federation should be delegated to established identity
  providers where possible.
- Actor attribution should be first-party because it is part of the kernel's
  accountability model.
- Leases should be first-party because they protect kernel resources and state
  transitions, not just HTTP sessions.

Practical interpretation:

- use OIDC/SAML/IdP integration for "who authenticated";
- record first-party `actor_id`, `role_id`, `surface`, `session_id`, and
  `correlation_id` on every mutation;
- use actor membership when a deployment needs explicit role/tenant/project
  authority for more than one human, agent, or service;
- add leases as kernel records over mutable resources before allowing
  concurrent multi-operator writes.

Do not let an external IdP decide organizational meaning. It can verify a
subject; the kernel decides whether that subject may act as a role, mutate a
resource, or close an accountability case.

## Research Anchors

- NIST SP 800-63-4: digital identity, identity proofing, authentication, and
  federation guidance.
- OAuth 2.0 / OIDC: delegated authorization and federated login patterns.
- OpenTelemetry semantic conventions: stable cross-service attribute names for
  traces, logs, and events.
- Gray and Cheriton leases: time-bounded control over distributed resources;
  modern variants preserve the same basic idea with fencing and expiry.

## T1 / T2

| Concern | T1 local service | T2 upgrade |
|---|---|---|
| Authentication | local process boundary or shared token | IdP-backed OIDC/SAML |
| Actor attribution | explicit actor strings in payloads/events | canonical `ActorIdentity` records |
| Role membership | trusted convention | scoped `ActorMembership` records |
| Leases | not required for one writer | first-party lease records with expiry/fencing |
| Backend | filesystem SourceConnector | SQLite transactional mutation backend, then Postgres/event store |
| Audit | Git plus local manifests | signed manifests and external timestamping |

## Service Modes

T1 default:

```bash
cognitive-firm-kernel-service
```

Registered-actor mode:

```bash
cognitive-firm-kernel-service --enforce-registered-actors
```

Membership-enforced mode:

```bash
cognitive-firm-kernel-service --enforce-registered-actors --enforce-actor-membership
```

In this mode, a request with `actor_context.role_id` must match an active
membership for the actor and requested tenant/project scope. Bootstrap
memberships through setup scripts, a service actor, or a temporary local
service config before enabling this mode.

Actor and membership administration routes require an identity-admin role in
strict service modes. By default, accepted admin roles are:

- `role.identity_admin`
- `role.owner`
- `role.principal`

This prevents an ordinary registered actor from granting roles or registering
new actors by omitting role context.

Subject-scope mode:

```bash
export COGNITIVE_FIRM_KERNEL_TOKEN=...
export COGNITIVE_FIRM_KERNEL_ACTOR_ID=human.alice
export COGNITIVE_FIRM_KERNEL_ACTOR_KIND=human
export COGNITIVE_FIRM_KERNEL_ROLES_ALLOWED=role.manager,role.reviewer
export COGNITIVE_FIRM_KERNEL_TENANT_IDS=tenant-a
cognitive-firm-kernel-service --require-token --enforce-subject-scope
```

When enabled, authenticated subject role and tenant claims must match the
request `actor_context`. For local bearer-token mode, the scope claims come
from the environment variables above. For production, an identity-provider
adapter should supply the same fields from OIDC, SAML, mTLS, or a trusted
gateway. This is the lean multi-principal isolation guard: the IdP
authenticates the subject, and the kernel rejects cross-role or cross-tenant
mutations before primitive code runs.

Lease-required mode:

```bash
cognitive-firm-kernel-service --enforce-registered-actors --require-leases
```

SQLite fenced-mutation mode:

```bash
cognitive-firm-kernel-service --mutation-backend sqlite --mutation-db cognitive_firm_workspace/kernel_mutations.sqlite3
```

In this mode, `/kernel/leases` and `/kernel/leases/{lease_id}/release` use the
configured SQLite mutation backend instead of the T1 JSONL lease file.
`/kernel/mutation-events` appends an event only when the supplied
`resource_ref`, `lease_id`, actor, and `fencing_token` match an active lease in
the same SQLite transaction. This is the public kernel's lean T2 mutation path.
Primitive-specific routes verify required leases against the configured SQLite
backend, so a SQLite lease does not silently authorize against the JSONL lease
log. Existing JSONL-backed primitive writes can migrate onto fully
transactional mutation events incrementally.

Local bearer-token mode:

```bash
export COGNITIVE_FIRM_KERNEL_TOKEN=...
export COGNITIVE_FIRM_KERNEL_ACTOR_ID=human.alice
export COGNITIVE_FIRM_KERNEL_ACTOR_KIND=human
cognitive-firm-kernel-service --require-token
```

The modes are additive. This lets a startup begin with a local service and move
toward multi-operator controls without changing primitive semantics.

## App Surface Writes

Orbit and the Telegram push channel are service clients. Their mutation
endpoints call these kernel routes and then refresh their projections. They do
not own gate resolution, directive/control files, chat appends, human-work
state, or role utilization config.

For local development:

```bash
cognitive-firm-kernel-service --host 127.0.0.1 --port 8765
ORBIT_SURFACE_MODE=kernel_intents COGNITIVE_FIRM_KERNEL_SERVICE_URL=http://127.0.0.1:8765 npm run dev
```

## Verification

```bash
make kernel-service-smoke
make app-integration-conformance
make smoke-public
```

`kernel-service-smoke` exercises the service dispatch path, SQLite lease
acquire, guarded event append, and stale fencing rejection. The app integration
conformance smoke exercises the deterministic Linear MCP projection shape and
signed inbound-event retry/idempotency behavior without requiring network
credentials.
