# EU AI Act Deploy Gate

This protocol is an optional T2 deployment check. It is for organizations that
choose to mark a role as `t2_deployment: true` and require an adopter-authored
EU AI Act mapping before that role can dispatch.

The kernel does not provide legal advice, classify a system for the adopter, or
author the mapping. It only checks whether the mapping artifact exists, covers
the current mandate hash, and names the authorized paths and MCP servers the
role can use.

## Behavior

When `t2_deployment: false` or omitted, the gate returns `allowed`.

When `t2_deployment: true`, `check_eu_ai_act_gate(...)` expects:

- `docs/compliance/eu_ai_act_mapping.md`;
- front matter with the current mandate hash;
- coverage entries for each `authorized_paths` root;
- coverage entries for each authorized MCP server;
- a recent enough `signed_at` value, if freshness review is enabled.

Missing or stale mapping blocks dispatch. A freshness reminder can emit a
non-blocking signal so the organization reviews an older mapping before it
becomes stale.

## Boundary

This primitive is a deployment gate, not a compliance program. The adopter owns:

- whether the EU AI Act applies;
- which articles map to which system behaviors;
- who can sign the mapping;
- whether cryptographic signatures are required;
- jurisdiction-specific legal review.

## Tests

Covered by `tests/test_eu_ai_act_deploy_gate.py`.
