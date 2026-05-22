# First Project Charter

This is the placeholder project the starter-firm distro ships so a freshly
installed organization has a real, runnable governance loop on day one. It is
deliberately generic. Replace its Core Question with your firm's actual first
unit of work — that first domain project is the operator's own first action.

## Core Question

Can this organization take one bounded unit of work from intake to a reviewed,
accountable closure using only the kernel's generic governance loop — without
adding domain-specific code to the kernel?

## Out Of Scope

- Domain-specific work: this charter is a loop test, not a real deliverable.
- Multi-principal RBAC.
- External-system write dispatch.
- Production deployment hardening.

## End States

- `validated`: a work item flowed through the Review Desk and the reviewer
  accepted it; the governance loop is proven runnable.
- `rejected`: the work item failed review or required evidence was missing.
- `deferred`: the next useful step requires unavailable external input.

## Forecast Type

directional_forecast

## Inheritance

The project inherits only the generic kernel protocols and the starter-firm
roles, mandates, and preferences this distro installed.

## Anchor Proxies

- anchor: charter_validates
  type: parser_check
  predicate: project charter validates with no generic contract errors

- anchor: governance_loop_closes
  type: cli_check
  predicate: a work item can be enqueued, claimed, completed, and reviewed
    through the Review Desk operating unit

- anchor: kernel_boundary_preserved
  type: code_review_predicate
  predicate: domain policy remains outside kernel modules
