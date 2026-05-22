# Example Tenant: Mill Company

This overlay shows how a tenant instantiates the kernel's production layer —
[`docs/protocols/work-items.md`](../../../docs/protocols/work-items.md) — as a
real company. A "mill company" is any organization that runs recurring,
typed production work: a support desk, a sales-ops queue, a research-triage
lane, a data-cleaning station, a CI lane, a proof mill.

The kernel owns the contract and the claim discipline. This tenant owns the
names: it calls its operating units **stations**, defines the work kinds and
the meaning of each exit, and supplies the worker roles. Nothing here is
Lean-, proof-, or domain-specific in the kernel; the domain lives in the
station definitions and the work payloads.

## The stations

`operating_units.json` defines five stations, each a generic
`OperatingUnit`:

| Station | `unit_kind` | What it does |
|---|---|---|
| Source Qualification | `qualification_desk` | screens raw candidates into qualified inputs |
| Proposal Desk | `proposal_lane` | turns qualified inputs into bounded proposals |
| Execution Lane | `transformation_lane` | runs the proposed work within a budget |
| Governance Gate | `governance_gate` | independently ratifies value-bearing exits |
| Registry Desk | `registry_lane` | promotes ratified output into reusable state |

The `worker_roles` on each station map to the worker classes described in the
protocol doc (`deterministic`, `llm`, `agent`, `governance`, `operator`). The
Governance Gate's exits appear in its `governance_required_for` list: a
completed exit is recorded, but only counts as value once the gate ratifies it.

## Load and run

Define the stations (each line is one `OperatingUnit`):

```bash
python -m cognitive_firm.orchestration.operating_units define \
  --unit-id source_qualification --unit-kind qualification_desk \
  --display-name "Source Qualification" --owner-role role.mill_manager \
  --allowed-work-kind screen_candidate --allowed-exit qualified --allowed-exit rejected \
  --worker-role role.deterministic_filter --p95-seconds 10
```

Or apply `operating_units.json` from a tenant setup script that calls
`define_operating_unit(**unit)` for each entry.

Enqueue, claim, and complete one unit of work:

```bash
python -m cognitive_firm.orchestration.work_items enqueue \
  --unit-id source_qualification --kind screen_candidate \
  --payload-json '{"candidate_ref": "raw/inbox/cand_001"}'

python -m cognitive_firm.orchestration.work_items claim-next \
  --unit-id source_qualification --actor actor.filter_1 --role-id role.deterministic_filter

python -m cognitive_firm.orchestration.work_items complete <work_id> \
  --actor actor.filter_1 --claim-token 1 --exit-kind qualified
```

See production health across stations:

```bash
python -m cognitive_firm.orchestration.operating_unit_surface
```

## Boundary

Keep domain policy — what "qualified" means, how a proposal is scored, which
exits a regulator cares about — in this overlay or a private tenant repo. The
public kernel only requires that finished work names an exit the station
declared in advance.
