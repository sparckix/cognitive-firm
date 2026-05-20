# Reader Checklist

Use this checklist when opening the repository for the first time or reviewing
a fork. It is deliberately short: the goal is to decide whether you understand
the kernel boundary well enough to change or adopt it.

## Thirty-Minute Understanding Check

After reading `README.md`, `docs/first-30-minutes.md`,
`docs/abstraction-map.md`, `docs/resource-event-catalog.md`, and
`docs/blueprints/README.md`, you should be able to answer:

1. What durable state does the kernel own?
2. What belongs in a tenant overlay instead?
3. Which app surfaces are projections rather than sources of truth?
4. How does a human produce bounded work with a receipt?
5. How does an external runtime pause and resume without owning organization
   state?
6. How does a finding become an approved learning event?
7. Which public smoke command proves the behavior you are relying on?

If any answer is unclear, start from the blueprint closest to your use case
instead of reading every protocol file.

## Change Review Check

Before changing the kernel, answer:

1. Which invariant from `docs/kernel-invariants.md` is affected?
2. Which state surface from `docs/resource-event-catalog.md` owns the fact?
3. Is the change kernel mechanism, app behavior, tenant policy, or runtime
   behavior?
4. Which test proves the new behavior?
5. Which public doc would become stale if the change landed?

## Adoption Check

For a real organization, do not start with a broad rollout. Pick one recurring
decision pipeline and use:

- `docs/field-validation-pilot.md`;
- `docs/templates/field-pilot/README.md`;
- `docs/examples/app-service-integration-example.md`;
- `docs/examples/learning-loop-demo.md`.

The adoption question is not whether the repo has many primitives. It is
whether one workflow becomes more reliable, faster, or cheaper without hiding
extra work in human coordination.

