# Demo Project Charter

## Core Question

Can the example tenant evaluate a bounded research claim using the public
cognitive-firm kernel without adding tenant-specific code to the kernel?

## Out Of Scope

- Production deployment.
- Multi-principal RBAC.
- External-system write dispatch.
- Domain-specific forecast scoring.

## End States

- `validated`: the claim survived the tenant's evidence and review policy.
- `rejected`: the claim failed review or required evidence was missing.
- `deferred`: the next useful step requires unavailable external input.

## Forecast Type

directional_forecast

## Inheritance

The project inherits only generic kernel protocols and tenant-local evidence.

## Anchor Proxies

- anchor: charter_validates
  type: parser_check
  predicate: project charter validates with no generic contract errors

- anchor: kernel_boundary_preserved
  type: code_review_predicate
  predicate: tenant policy remains outside kernel modules

- anchor: organization_surface_renders
  type: cli_check
  predicate: organization surface renders without tenant-specific code
