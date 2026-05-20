"""State backend interfaces for cognitive-firm kernel state.

The T1 implementation is filesystem-backed: JSONL for ordered events and
plain files for artifacts. T2 deployments can replace that transport while
preserving the logical kernel contract.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Protocol
import uuid

from cognitive_firm.orchestration.connector_families import ConnectorFamily


class SourceConnector(Protocol):
    """Named connector boundary for kernel-adjacent sources.

    State backends, MCP enterprise-system bridges, runtime adapters, and
    notification providers are all connectors. Each family has its own
    semantics, but every connector should be identifiable in logs and docs.
    """

    connector_id: str
    connector_family: ConnectorFamily | str


class EventSource(Protocol):
    """Append-only ordered event source."""

    def append_event(self, stream: str, event: dict[str, Any]) -> None:
        """Append one JSON-compatible event to a named stream."""

    def read_events(self, stream: str) -> list[dict[str, Any]]:
        """Read all events from a named stream in append order."""


class TransactionalMutationBackend(EventSource, Protocol):
    """State backend that fences contested mutations transactionally."""

    def acquire_lease(
        self,
        *,
        resource_ref: str,
        actor_id: str,
        role_id: str | None = None,
        ttl_seconds: int = 300,
        purpose: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Acquire a lease over one mutable resource."""

    def release_lease(self, *, lease_id: str, actor_id: str) -> dict[str, Any]:
        """Release an active lease held by the actor."""

    def guarded_append_event(
        self,
        *,
        stream: str,
        event: dict[str, Any],
        resource_ref: str,
        lease_id: str,
        actor_id: str,
        fencing_token: int,
    ) -> dict[str, Any]:
        """Append an event only if the lease is current in the same transaction."""

    def list_leases(self, *, resource_ref: str | None = None) -> list[dict[str, Any]]:
        """List current and historical leases."""


class ArtifactSource(Protocol):
    """Small artifact source for kernel-owned read models and receipts."""

    def put_artifact(self, key: str, payload: dict[str, Any]) -> None:
        """Persist a JSON-compatible artifact by key."""

    def get_artifact(self, key: str) -> dict[str, Any] | None:
        """Return a JSON artifact by key, or None when absent."""


@dataclass(frozen=True)
class FilesystemStateBackend(SourceConnector, EventSource, ArtifactSource):
    """T1 filesystem backend.

    Events are stored as `<root>/events/<stream>.jsonl`. Artifacts are stored
    as `<root>/artifacts/<key>.json`, with slashes in keys treated as
    directories.
    """

    root: Path
    connector_id: str = "filesystem"
    connector_family: ConnectorFamily = "state_backend"

    def _event_path(self, stream: str) -> Path:
        return self.root / "events" / f"{_safe_stream(stream)}.jsonl"

    def _artifact_path(self, key: str) -> Path:
        return self.root / "artifacts" / f"{_safe_key(key)}.json"

    def append_event(self, stream: str, event: dict[str, Any]) -> None:
        path = self._event_path(stream)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    def read_events(self, stream: str) -> list[dict[str, Any]]:
        path = self._event_path(stream)
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(json.loads(line))
        return events

    def put_artifact(self, key: str, payload: dict[str, Any]) -> None:
        path = self._artifact_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    def get_artifact(self, key: str) -> dict[str, Any] | None:
        path = self._artifact_path(key)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class SqliteEventSource(SourceConnector, EventSource):
    """Lean T2 event source using SQLite.

    This is intentionally events-only. It provides ordered appends with a
    database file, leaving object storage and signed audit as separate T2
    decisions.
    """

    path: Path
    connector_id: str = "sqlite"
    connector_family: ConnectorFamily = "state_backend"

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              stream TEXT NOT NULL,
              payload TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_stream_id ON events(stream, id)")
        return conn

    def append_event(self, stream: str, event: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO events(stream, payload) VALUES (?, ?)",
                (stream, json.dumps(event, sort_keys=True)),
            )

    def read_events(self, stream: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM events WHERE stream = ? ORDER BY id ASC",
                (stream,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]


@dataclass(frozen=True)
class SqliteMutationBackend(SourceConnector, EventSource):
    """SQLite mutation backend with transactional lease fencing.

    This is the lean T2 backend for contested resources. Lease verification and
    event append happen inside one SQLite ``BEGIN IMMEDIATE`` transaction, so a
    stale or mismatched fencing token cannot pass a separate preflight and then
    write afterward.
    """

    path: Path
    connector_id: str = "sqlite_mutation"
    connector_family: ConnectorFamily = "state_backend"

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        self._ensure_schema(conn)
        return conn

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              stream TEXT NOT NULL,
              payload TEXT NOT NULL,
              resource_ref TEXT,
              lease_id TEXT,
              fencing_token INTEGER,
              created_at_utc TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mutation_events_stream_id ON events(stream, id)")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS leases (
              lease_id TEXT PRIMARY KEY,
              resource_ref TEXT NOT NULL,
              held_by_actor_id TEXT NOT NULL,
              held_by_role_id TEXT,
              acquired_at_utc TEXT NOT NULL,
              expires_at_utc TEXT NOT NULL,
              state TEXT NOT NULL,
              fencing_token INTEGER NOT NULL,
              released_at_utc TEXT,
              purpose TEXT NOT NULL,
              metadata TEXT NOT NULL
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_leases_resource_state ON leases(resource_ref, state)")

    def append_event(self, stream: str, event: dict[str, Any]) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO events(stream, payload, created_at_utc)
                VALUES (?, ?, ?)
                """,
                (stream, json.dumps(event, sort_keys=True), _now_iso()),
            )

    def read_events(self, stream: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM events WHERE stream = ? ORDER BY id ASC",
                (stream,),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def acquire_lease(
        self,
        *,
        resource_ref: str,
        actor_id: str,
        role_id: str | None = None,
        ttl_seconds: int = 300,
        purpose: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not resource_ref.strip():
            raise ValueError("resource_ref is required")
        if not actor_id.strip():
            raise ValueError("actor_id is required")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                now = _now_dt()
                active = conn.execute(
                    """
                    SELECT * FROM leases
                    WHERE resource_ref = ? AND state = 'active' AND expires_at_utc > ?
                    ORDER BY fencing_token DESC
                    LIMIT 1
                    """,
                    (resource_ref, now.isoformat()),
                ).fetchone()
                if active is not None:
                    raise PermissionError(
                        f"resource {resource_ref} is leased by {active['held_by_actor_id']} "
                        f"until {active['expires_at_utc']}"
                    )
                row = conn.execute(
                    "SELECT COALESCE(MAX(fencing_token), 0) AS max_token FROM leases WHERE resource_ref = ?",
                    (resource_ref,),
                ).fetchone()
                token = int(row["max_token"]) + 1
                lease = {
                    "lease_id": f"lease_{uuid.uuid4().hex[:12]}",
                    "resource_ref": resource_ref,
                    "held_by_actor_id": actor_id,
                    "held_by_role_id": role_id,
                    "acquired_at_utc": now.isoformat(),
                    "expires_at_utc": (now + timedelta(seconds=ttl_seconds)).isoformat(),
                    "state": "active",
                    "fencing_token": token,
                    "released_at_utc": None,
                    "purpose": purpose,
                    "metadata": metadata or {},
                }
                conn.execute(
                    """
                    INSERT INTO leases(
                      lease_id, resource_ref, held_by_actor_id, held_by_role_id,
                      acquired_at_utc, expires_at_utc, state, fencing_token,
                      released_at_utc, purpose, metadata
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        lease["lease_id"],
                        lease["resource_ref"],
                        lease["held_by_actor_id"],
                        lease["held_by_role_id"],
                        lease["acquired_at_utc"],
                        lease["expires_at_utc"],
                        lease["state"],
                        lease["fencing_token"],
                        lease["released_at_utc"],
                        lease["purpose"],
                        json.dumps(lease["metadata"], sort_keys=True),
                    ),
                )
                conn.commit()
                return lease
            except Exception:
                conn.rollback()
                raise

    def release_lease(self, *, lease_id: str, actor_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute("SELECT * FROM leases WHERE lease_id = ?", (lease_id,)).fetchone()
                if row is None:
                    raise KeyError(f"lease not found: {lease_id}")
                if row["held_by_actor_id"] != actor_id:
                    raise PermissionError("only the lease holder can release the lease")
                if row["state"] == "active":
                    conn.execute(
                        "UPDATE leases SET state = 'released', released_at_utc = ? WHERE lease_id = ?",
                        (_now_iso(), lease_id),
                    )
                conn.commit()
                return self._lease_by_id(lease_id)
            except Exception:
                conn.rollback()
                raise

    def guarded_append_event(
        self,
        *,
        stream: str,
        event: dict[str, Any],
        resource_ref: str,
        lease_id: str,
        actor_id: str,
        fencing_token: int,
    ) -> dict[str, Any]:
        """Verify lease/fencing token and append event in one transaction."""

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                lease = conn.execute(
                    """
                    SELECT * FROM leases
                    WHERE resource_ref = ?
                      AND lease_id = ?
                      AND state = 'active'
                      AND expires_at_utc > ?
                    """,
                    (resource_ref, lease_id, _now_iso()),
                ).fetchone()
                if lease is None:
                    raise PermissionError(f"active lease not found for {resource_ref}: {lease_id}")
                if lease["held_by_actor_id"] != actor_id:
                    raise PermissionError("lease holder does not match actor")
                if int(lease["fencing_token"]) != int(fencing_token):
                    raise PermissionError("lease fencing token does not match")
                payload = {
                    **event,
                    "resource_ref": resource_ref,
                    "lease_id": lease_id,
                    "fencing_token": fencing_token,
                }
                cursor = conn.execute(
                    """
                    INSERT INTO events(
                      stream, payload, resource_ref, lease_id, fencing_token, created_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        stream,
                        json.dumps(payload, sort_keys=True),
                        resource_ref,
                        lease_id,
                        int(fencing_token),
                        _now_iso(),
                    ),
                )
                conn.commit()
                return {"event_row_id": cursor.lastrowid, "event": payload}
            except Exception:
                conn.rollback()
                raise

    def list_leases(self, *, resource_ref: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM leases"
        params: tuple[Any, ...] = ()
        if resource_ref is not None:
            query += " WHERE resource_ref = ?"
            params = (resource_ref,)
        query += " ORDER BY acquired_at_utc ASC, fencing_token ASC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._lease_row_to_dict(row) for row in rows]

    def _lease_by_id(self, lease_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM leases WHERE lease_id = ?", (lease_id,)).fetchone()
        if row is None:
            raise KeyError(f"lease not found: {lease_id}")
        return self._lease_row_to_dict(row)

    @staticmethod
    def _lease_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
        out = dict(row)
        out["metadata"] = json.loads(str(out.get("metadata") or "{}"))
        return out


@dataclass(frozen=True)
class PostgresMutationBackend(SourceConnector, EventSource):
    """Postgres implementation of the transactional mutation backend contract.

    The adapter requires ``psycopg`` at runtime but does not make it a hard
    dependency of the public package. Deployments can pass either ``conninfo``
    or a ``connection_factory`` returning a psycopg-compatible connection.
    """

    conninfo: str | None = None
    connection_factory: Callable[[], Any] | None = None
    connector_id: str = "postgres_mutation"
    connector_family: ConnectorFamily = "state_backend"

    def _connect(self) -> Any:
        if self.connection_factory is not None:
            return self.connection_factory()
        if not self.conninfo:
            raise ValueError("conninfo or connection_factory is required")
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - depends on deployment extras.
            raise RuntimeError("PostgresMutationBackend requires psycopg") from exc
        return psycopg.connect(self.conninfo, row_factory=dict_row)

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            with conn.transaction():
                conn.execute(postgres_transactional_mutation_schema_sql())

    def append_event(self, stream: str, event: dict[str, Any]) -> None:
        with self._connect() as conn:
            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO cognitive_firm_events(stream, payload, created_at_utc)
                    VALUES (%(stream)s, %(payload)s::jsonb, now())
                    """,
                    {"stream": stream, "payload": json.dumps(event, sort_keys=True)},
                )

    def read_events(self, stream: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT payload
                FROM cognitive_firm_events
                WHERE stream = %(stream)s
                ORDER BY id ASC
                """,
                {"stream": stream},
            ).fetchall()
        return [dict(row["payload"]) if isinstance(row["payload"], dict) else json.loads(row["payload"]) for row in rows]

    def acquire_lease(
        self,
        *,
        resource_ref: str,
        actor_id: str,
        role_id: str | None = None,
        ttl_seconds: int = 300,
        purpose: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not resource_ref.strip():
            raise ValueError("resource_ref is required")
        if not actor_id.strip():
            raise ValueError("actor_id is required")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        lease_id = f"lease_{uuid.uuid4().hex[:12]}"
        with self._connect() as conn:
            with conn.transaction():
                self._lock_resource(conn, resource_ref)
                active = conn.execute(
                    """
                    SELECT held_by_actor_id, expires_at_utc
                    FROM cognitive_firm_leases
                    WHERE resource_ref = %(resource_ref)s
                      AND state = 'active'
                      AND expires_at_utc > now()
                    ORDER BY fencing_token DESC
                    LIMIT 1
                    FOR UPDATE
                    """,
                    {"resource_ref": resource_ref},
                ).fetchone()
                if active is not None:
                    raise PermissionError(
                        f"resource {resource_ref} is leased by {active['held_by_actor_id']} "
                        f"until {active['expires_at_utc']}"
                    )
                row = conn.execute(
                    """
                    SELECT COALESCE(MAX(fencing_token), 0) AS max_token
                    FROM cognitive_firm_leases
                    WHERE resource_ref = %(resource_ref)s
                    """,
                    {"resource_ref": resource_ref},
                ).fetchone()
                token = int(row["max_token"]) + 1
                lease = {
                    "lease_id": lease_id,
                    "resource_ref": resource_ref,
                    "held_by_actor_id": actor_id,
                    "held_by_role_id": role_id,
                    "acquired_at_utc": _now_iso(),
                    "expires_at_utc": (_now_dt() + timedelta(seconds=ttl_seconds)).isoformat(),
                    "state": "active",
                    "fencing_token": token,
                    "released_at_utc": None,
                    "purpose": purpose,
                    "metadata": metadata or {},
                }
                conn.execute(
                    """
                    INSERT INTO cognitive_firm_leases(
                      lease_id, resource_ref, held_by_actor_id, held_by_role_id,
                      acquired_at_utc, expires_at_utc, state, fencing_token,
                      released_at_utc, purpose, metadata
                    ) VALUES (
                      %(lease_id)s, %(resource_ref)s, %(held_by_actor_id)s, %(held_by_role_id)s,
                      %(acquired_at_utc)s, %(expires_at_utc)s, %(state)s, %(fencing_token)s,
                      %(released_at_utc)s, %(purpose)s, %(metadata)s::jsonb
                    )
                    """,
                    {**lease, "metadata": json.dumps(lease["metadata"], sort_keys=True)},
                )
                return lease

    def release_lease(self, *, lease_id: str, actor_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    "SELECT * FROM cognitive_firm_leases WHERE lease_id = %(lease_id)s FOR UPDATE",
                    {"lease_id": lease_id},
                ).fetchone()
                if row is None:
                    raise KeyError(f"lease not found: {lease_id}")
                if row["held_by_actor_id"] != actor_id:
                    raise PermissionError("only the lease holder can release the lease")
                if row["state"] == "active":
                    conn.execute(
                        """
                        UPDATE cognitive_firm_leases
                        SET state = 'released', released_at_utc = now()
                        WHERE lease_id = %(lease_id)s
                        """,
                        {"lease_id": lease_id},
                    )
                return self._lease_by_id(conn, lease_id)

    def guarded_append_event(
        self,
        *,
        stream: str,
        event: dict[str, Any],
        resource_ref: str,
        lease_id: str,
        actor_id: str,
        fencing_token: int,
    ) -> dict[str, Any]:
        payload = {
            **event,
            "resource_ref": resource_ref,
            "lease_id": lease_id,
            "fencing_token": fencing_token,
        }
        with self._connect() as conn:
            with conn.transaction():
                row = conn.execute(
                    postgres_guarded_append_transaction_sql(),
                    {
                        "stream": stream,
                        "payload": json.dumps(payload, sort_keys=True),
                        "resource_ref": resource_ref,
                        "lease_id": lease_id,
                        "actor_id": actor_id,
                        "fencing_token": int(fencing_token),
                    },
                ).fetchone()
                if row is None:
                    raise PermissionError("active lease/fencing check failed")
                return {"event_row_id": row["id"], "event": payload}

    def list_leases(self, *, resource_ref: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM cognitive_firm_leases"
        params: dict[str, Any] = {}
        if resource_ref is not None:
            query += " WHERE resource_ref = %(resource_ref)s"
            params["resource_ref"] = resource_ref
        query += " ORDER BY acquired_at_utc ASC, fencing_token ASC"
        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_lease(row) for row in rows]

    @staticmethod
    def _lock_resource(conn: Any, resource_ref: str) -> None:
        conn.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%(resource_ref)s, 0))",
            {"resource_ref": resource_ref},
        )

    @classmethod
    def _lease_by_id(cls, conn: Any, lease_id: str) -> dict[str, Any]:
        row = conn.execute(
            "SELECT * FROM cognitive_firm_leases WHERE lease_id = %(lease_id)s",
            {"lease_id": lease_id},
        ).fetchone()
        if row is None:
            raise KeyError(f"lease not found: {lease_id}")
        return cls._row_to_lease(row)

    @staticmethod
    def _row_to_lease(row: dict[str, Any]) -> dict[str, Any]:
        out = dict(row)
        metadata = out.get("metadata")
        if isinstance(metadata, str):
            out["metadata"] = json.loads(metadata)
        elif metadata is None:
            out["metadata"] = {}
        return out


def postgres_transactional_mutation_schema_sql() -> str:
    """Return the Postgres schema equivalent for ``TransactionalMutationBackend``.

    The public kernel ships SQLite as the first runnable T2 backend. This SQL
    keeps the Postgres contract concrete for adopters without adding an
    unconditional database-driver dependency to the package.
    """

    return """
CREATE TABLE IF NOT EXISTS cognitive_firm_events (
  id BIGSERIAL PRIMARY KEY,
  stream TEXT NOT NULL,
  payload JSONB NOT NULL,
  resource_ref TEXT,
  lease_id TEXT,
  fencing_token BIGINT,
  created_at_utc TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_cognitive_firm_events_stream_id
  ON cognitive_firm_events(stream, id);

CREATE TABLE IF NOT EXISTS cognitive_firm_leases (
  lease_id TEXT PRIMARY KEY,
  resource_ref TEXT NOT NULL,
  held_by_actor_id TEXT NOT NULL,
  held_by_role_id TEXT,
  acquired_at_utc TIMESTAMPTZ NOT NULL,
  expires_at_utc TIMESTAMPTZ NOT NULL,
  state TEXT NOT NULL,
  fencing_token BIGINT NOT NULL,
  released_at_utc TIMESTAMPTZ,
  purpose TEXT NOT NULL,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS idx_cognitive_firm_leases_resource_state
  ON cognitive_firm_leases(resource_ref, state);
""".strip()


def postgres_guarded_append_transaction_sql() -> str:
    """Return the core Postgres guarded-append transaction.

    Callers should execute this inside one transaction with bound parameters
    named as shown. The ``FOR UPDATE`` row lock is the important property:
    lease validation and event append are one mutation boundary.
    """

    return """
WITH active_lease AS (
  SELECT lease_id, held_by_actor_id, fencing_token
  FROM cognitive_firm_leases
  WHERE resource_ref = %(resource_ref)s
    AND lease_id = %(lease_id)s
    AND state = 'active'
    AND expires_at_utc > now()
  FOR UPDATE
)
INSERT INTO cognitive_firm_events(
  stream, payload, resource_ref, lease_id, fencing_token
)
SELECT
  %(stream)s,
  %(payload)s::jsonb,
  %(resource_ref)s,
  %(lease_id)s,
  %(fencing_token)s
FROM active_lease
WHERE held_by_actor_id = %(actor_id)s
  AND fencing_token = %(fencing_token)s
RETURNING id;
""".strip()


def _safe_stream(stream: str) -> str:
    cleaned = stream.strip().replace("/", "_")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("stream cannot be empty")
    if any(part == ".." for part in cleaned.split("_")):
        raise ValueError("stream cannot contain parent traversal")
    return cleaned


def _safe_key(key: str) -> str:
    cleaned = key.strip()
    if cleaned.startswith("/"):
        raise ValueError("key cannot be absolute")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("key cannot be empty")
    parts = Path(cleaned).parts
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("key cannot contain unsafe path segments")
    return str(Path(*parts))


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now_dt().isoformat()
