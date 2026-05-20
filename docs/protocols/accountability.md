# Accountability Summary

**Module:** `cognitive_firm.orchestration.accountability`

The accountability summary is a read model over organizational learning
carriers. It joins owner, project, review status, due dates, source references,
and externality tags so humans and role offices can see what still needs
follow-up.

It is not a blame ledger and it does not mutate state.

## What It Reads

The summary reads the organization surface:

- blocking evidence gaps;
- active human-work sessions;
- action-impact rows requiring review;
- local action-impact rows with negative externalities;
- forecast allocation recommendations and decision-use rows;
- strategy-office findings;
- recent damage signals;
- failed run checkpoints.

## What It Emits

Each `AccountabilityItem` includes:

- `item_id`;
- `source_kind`;
- `severity`;
- `status`;
- `owner_role`;
- `tenant_id`;
- `project_id`;
- `object_ref`;
- `rationale`;
- `review_required`;
- `due_at_utc`;
- `source_refs`;
- `externality_tags`;
- `metadata`.

The summary also reports counts by source kind, owner role, and project id.

## Boundary

The accountability summary consumes read models. It does not assign new work,
change ownership, close evidence gaps, or resolve damage signals. Tenants may
bind the output to a review queue or issue tracker through an authorized
adapter.

## Tests

Covered by `tests/test_accountability.py`.
