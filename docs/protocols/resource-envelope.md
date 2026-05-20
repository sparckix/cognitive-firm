# Resource Envelope

**Module:** `cognitive_firm.orchestration.resource_envelope`

The resource envelope is the lightweight object shape for kernel resources. It
keeps primitive data portable without requiring the repo to become a Kubernetes
clone.

## Shape

Each resource has:

```text
api_version
kind
metadata
stability
spec
status
links
```

`metadata` includes name, optional resource ID, tenant/project IDs, labels,
annotations, and timestamps.

`stability` is one of:

- `alpha`: shape may change while the primitive is still settling;
- `beta`: shape is expected to hold unless tests or field use expose a gap;
- `stable`: shape is part of the supported public contract.

## Boundary

The envelope is a compatibility convention, not a storage backend. Individual
primitives can keep their own T1 files while exposing resources through this
shape for conformance, documentation, migration, or external adapters.

## Tests

Covered by `tests/test_resource_envelope.py`.
