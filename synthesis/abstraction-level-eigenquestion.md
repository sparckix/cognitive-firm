---
type: synthesis-mirror
created: 2026-05-20
source: research-assistant synthesis mirror, 2026-05-20
---

# Abstraction-Level Eigenquestion

Question: does `cognitive-firm` have the right abstraction level, or is it too
low-level to be a cognitive-firm kernel?

Answer: the kernel is layered and mostly at the right level. It is not just a
bag of files and helper functions: it has role offices, mandates, H2A/A2H/A2A,
MCP, runtime adapters, state surfaces, kernel service, app integration,
accountability, and learning-loop primitives. It also avoids owning tenant
policy, enterprise IAM administration, app workflow, and graph-runtime
semantics. That is the right direction for a reusable governance kernel.

The gap is mid-level packaging. A new adopter still has to assemble too much
from the protocol catalog. The next layer should not add many primitives; it
should name standard compositions:

- an abstraction map: kernel vs runtime vs app vs tenant;
- a resource/event catalog;
- use-case blueprints;
- an adoption decision tree;
- a learning-loop blueprint;
- an app-service integration slice;
- a human-work rubric.

The implementation pull-forward from this synthesis is in:

- `docs/abstraction-map.md`;
- `docs/resource-event-catalog.md`;
- `docs/blueprints/README.md`.
