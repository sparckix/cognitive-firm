# State Surface Inventory

**Module:** `cognitive_firm.orchestration.state_surface_inventory`

The state-surface inventory lists the durable and projected state surfaces in
the kernel. It exists to keep connector families distinct and to make storage
boundaries inspectable by tests.

## Connector Families

| Family | Owns |
|---|---|
| `state_backend` | Kernel event streams, JSONL records, artifacts, and projections over them. |
| `app_surface` | UI or operator surface that submits typed kernel-service requests. |
| `enterprise_system` | MCP-facing systems such as issue trackers, CRMs, ERPs, or document systems. |
| `runtime` | External graph, crew, chat, or agent runtime lifecycle events. |
| `inbound_event` | External webhook/event-stream observation entering quarantine/projection. |
| `notification` | Attention delivery providers such as Telegram or null/local channels. |
| `identity_provider` | Authenticates request subjects; kernel maps them to actor authority. |
| `tenant_adapter` | Tenant-owned summaries such as forecast-market health or action-impact summaries. |

Local review artifacts use the root `reviews/` workspace. That directory is
gitignored by default; publish only conclusions that should become durable
public docs or tenant policy.

## Canonical, Read Model, Projection

Use these labels when adding or reviewing a state surface:

| Class | Meaning | Examples |
|---|---|---|
| Canonical state | The durable record that owns a fact. Mutations must go through the primitive or kernel service that owns the lifecycle. | Human work JSONL, accountability cases, A2A messages, transition rows, leases, actor identity records. |
| Read model | A derived view rebuilt from canonical state or tenant-owned summaries. It is convenient to query but not authoritative for mutation. | Organization surface, accountability summary, forecast-market summary, action-impact summary, strategy review. |
| Projection | A UI, app, or external-system rendering of kernel state. It can submit typed intents but must not become the source of truth. | Orbit panes, Telegram messages, Linear issue projections, dashboards. |
| Tenant-owned ledger | A domain-specific source owned by an overlay. The kernel consumes its generic summary shape only. | Scientific-yield decomposition, P&L attribution, tenant forecast pool, tenant action-impact records. |

The intelligence-source projection reads this inventory and the organization
surface to show source health, thin signals, and repair items. It does not
replace this inventory; it is a coverage view over it.

The public kernel should make canonical surfaces boring and sparse. New
intelligence usually belongs in a tenant-owned ledger, a read model, or a
learning-event proposal until it proves it should change core behavior.

## Inventory Fields

Each `StateSurface` includes:

- `primitive`;
- `module`;
- `surface_kind`;
- `connector_family`;
- `state_class`;
- `default_location`;
- `writer`;
- `reader`;
- `tenant_owned`;
- `notes`;
- `conformance_tests`.

`state_class` uses the same source-of-truth vocabulary as this document:

- `canonical_state`;
- `read_model`;
- `projection`;
- `telemetry`;
- `tenant_owned_ledger`.

The test suite also scans `src/cognitive_firm/orchestration` for modules that
define common default JSONL logs. A new JSONL-backed primitive that follows the
normal `DEFAULT_*_LOG` naming pattern must be added to the inventory or the
inventory test fails.

## Rule

Do not route ERP/CRM/runtime/provider semantics through a state backend because
it is convenient. State backends store kernel state. Enterprise systems,
runtimes, notification providers, and tenant ledgers remain separate connector
families.

Do not mutate through a projection. A projection may call the kernel service,
which enforces actor identity, mandate/capability policy, and leases where
configured. If an app surface needs a new write, add a typed kernel intent
instead of writing files directly from the app.

## Tests

Covered by `tests/test_state_surface_inventory.py`.
