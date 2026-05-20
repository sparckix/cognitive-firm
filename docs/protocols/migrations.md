# Migration Records

**Module:** `cognitive_firm.orchestration.migrations`

Migration records are the kernel's T1 protocol for changing durable state
schemas without silent drift.

## Phases

Supported phases:

- `expand`;
- `backfill`;
- `contract`;
- `verify`.

Records default to dry-run. A migration is marked `applied` only when callers
explicitly pass the apply flag and no errors are recorded.

## Fields

Each migration record includes:

- `migration_id`;
- `primitive`;
- `from_version`;
- `to_version`;
- `phase`;
- `status`;
- `actor`;
- `created_at_utc`;
- `dry_run`;
- `rationale`;
- `affected_refs`;
- `backup_ref`;
- `verification_ref`;
- `errors`;
- `metadata`.

## Boundary

The migration protocol records migration intent and results. It does not
transform a primitive by itself. Primitive-specific migration code should record
dry runs, backups, verification references, and final applied records here.

Default local path:

```text
org/migrations/migrations.jsonl
```

## Filesystem To SQLite Mutation Backend

For a T1 to lean-T2 storage upgrade, use this sequence:

1. Record an `expand` dry-run migration for the target primitive or service.
2. Start the kernel service with `--mutation-backend sqlite` in a staging
   workspace.
3. Exercise `make kernel-service-smoke` and the primitive-specific tests.
4. Back up the JSONL lease/event files named by the primitive.
5. Route new contested mutations through `/kernel/leases` and
   `/kernel/mutation-events`.
6. Record a `verify` migration with the smoke/test output reference.
7. Only then mark the migration applied.

Do not silently copy every JSONL row into SQLite and declare completion. The
important migration property is not file format; it is that contested mutations
now verify the lease and append the event in one transaction.

## Tests

Covered by `tests/test_migrations.py`.
