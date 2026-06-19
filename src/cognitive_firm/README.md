# cognitive_firm

This package is the source of truth for reusable cognitive-firm behavior. Put
kernel primitives, invariants, schemas, state transitions, service routes,
distribution mechanics, adapters, projections, userland helpers, and shared
runtime utilities here.

A change belongs here when:

- another program should be able to import and rely on it;
- it records or validates authority;
- it changes durable organization state;
- it defines a reusable protocol, event, resource, or schema;
- it affects auditability, learning, accountability, or state mutation;
- more than one script, app, demo, or tenant overlay needs it.

Keep tenant strategy, credentials, local policy, private connectors, and
workflow-specific preferences outside this package. Those belong in overlays,
examples, app code, or private tenant repositories.

<!-- AUTO-INDEX:START (managed by scripts/gen_folder_index.py — edit prose OUTSIDE this block) -->

## Index

**Sub-folders**

- [`common/`](common/) - 3 file(s)
- [`distribution/`](distribution/) - 14 file(s)
- [`notifications/`](notifications/) - 4 file(s)
- [`orchestration/`](orchestration/) - 84 file(s)
- [`role_extensions/`](role_extensions/) - 9 file(s)
- [`sessions/`](sessions/) - 3 file(s)
- [`signals/`](signals/) - 3 file(s)
- [`userland/`](userland/) - 11 file(s)

**Documents**

- [__init__.py](__init__.py)
- [cli.py](cli.py)
- [identity_providers.py](identity_providers.py)
- [identity_provisioning.py](identity_provisioning.py)
- [kernel_service.py](kernel_service.py)
- [py.typed](py.typed)

<sub>8 sub-folder(s), 6 document(s). Auto-generated; re-run `scripts/gen_folder_index.py` after adding files.</sub>

<!-- AUTO-INDEX:END -->
