# Tenant Isolation

**Status:** lean scope guard shipped.
**Module:** `cognitive_firm.orchestration.tenant_isolation`
**Tests:** `tests/test_tenant_isolation.py`

Tenant isolation has two layers:

- kernel scope checks that stop obvious cross-tenant actor/path mistakes;
- deployment isolation for separate authority domains.

The public kernel ships the first layer. It does not claim to ship a hosted
multi-tenant control plane.

## Kernel Scope Guard

The lean guard checks:

- the actor context tenant matches the requested tenant;
- the requested path remains inside the configured tenant overlay root;
- tenant identifiers are simple relative names.

This is useful for local app surfaces and tenant setup scripts. It prevents
common mistakes such as applying one tenant's role file to another tenant's
overlay path.

## Deployment Boundary

Hard tenant isolation still belongs to deployment architecture:

- separate repos or branches for sensitive tenants;
- separate databases or schemas where needed;
- gateway/API isolation;
- tenant-specific secrets and key custody;
- backup/restore boundaries;
- enterprise IAM and audit policy.

The kernel provides the vocabulary and local guard. A production multi-tenant
service still needs infrastructure policy around it.

## Example

```python
from cognitive_firm.orchestration.tenant_isolation import (
    tenant_overlay_root,
    validate_tenant_ref,
)

boundary = tenant_overlay_root(Path("tenants"), "tenant-a")
validate_tenant_ref(
    actor=actor_context,
    tenant_id="tenant-a",
    path=boundary.root / "roles" / "manager.yaml",
    boundary=boundary,
)
```
