# Learning Event Replay Example

This example shows the intended test for organizational learning: a reviewed
state transition changes what future work sees.

## Before

A role repeatedly ships analysis with unsupported comparator claims. The
organization surface shows evidence gaps and a strategy finding:

```text
source_kind=evidence_gap
target=comparator claims
severity=blocking
```

The learning transition compiler creates a candidate:

```text
transition_kind=source_repair
future_application_cue="new comparator claim"
```

## Approval

A reviewer approves a learning event:

```text
learning_unit_kind=routine_change
future_application_cue="new comparator claim"
behavior_change="Comparator claims require source note or explicit uncertainty."
```

The event is not a memo. It is active state.

## Future Replay

When a later role starts work on a similar artifact, replay filters by role,
tenant/project, and cue. The active learning event is returned before the role
commits work:

```text
cue: new comparator claim
encountered learning: require source note or explicit uncertainty
```

The role can now:

- add the source note;
- mark the claim uncertain;
- open an evidence gap;
- avoid repeating the old failure mode.

## What Counts As Success

Replay succeeds only if future work encounters the learning event at a moment
where behavior can change.

Archival visibility is not enough. A learning event that never changes routing,
review, authority, source practice, or artifact quality is not doing useful
organizational work.

## Executable Walkthrough

Run:

```bash
PYTHONPATH=src python scripts/learning_loop_walkthrough.py
```

The script exercises evidence gap closure, human-work integration,
accountability, approved learning-event creation, and replay into matching
future work.
