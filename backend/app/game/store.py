"""Append-only event store.

Every runtime action is logged through ``EventStore.append``. ``SqlEventStore``
writes to the ``ie_event_log`` table; ``MemoryEventStore`` keeps records in a
list (tests, simulation). Records are JSON-safe dicts.
"""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

log = logging.getLogger(__name__)


def json_safe(x: Any) -> Any:
    """Convert payloads to JSON-safe values (no NaN/inf, tuples -> lists, keys -> str)."""
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    if isinstance(x, dict):
        return {str(k): json_safe(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [json_safe(v) for v in x]
    return x


class EventStore(Protocol):
    async def append(self, kind: str, *, session_id: str, group_id: str | None = None, round: int | None = None,
                     participant_id: str | None = None, payload: dict[str, Any] | None = None) -> None: ...


@dataclass
class MemoryEventStore:
    records: list[dict[str, Any]] = field(default_factory=list)

    async def append(self, kind, *, session_id, group_id=None, round=None, participant_id=None, payload=None):
        self.records.append({"ts": datetime.now(timezone.utc).isoformat(), "kind": kind, "session_id": session_id,
                             "group_id": group_id, "round": round, "participant_id": participant_id,
                             "payload": json_safe(payload or {})})

    def of_kind(self, kind: str) -> list[dict[str, Any]]:
        return [r for r in self.records if r["kind"] == kind]


class SqlEventStore:
    """Writes each record in its own short transaction, serialized per process."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()

    async def append(self, kind, *, session_id, group_id=None, round=None, participant_id=None, payload=None):
        from app.models.database import get_db
        from app.models.game_models import EventLog

        row = EventLog(ts=datetime.now(timezone.utc), session_id=session_id, group_id=group_id, round=round,
                       participant_id=participant_id, kind=kind, payload=json_safe(payload or {}))
        async with self._lock:
            async with get_db() as db:
                db.add(row)
                await db.commit()


@dataclass
class PrefixedEventStore:
    """Logs to another store with every kind prefixed (practice rounds: ``practice_decision`` ...),
    so analyses of the real game never pick up practice records by accident."""

    inner: EventStore
    prefix: str

    async def append(self, kind, *, session_id, group_id=None, round=None, participant_id=None, payload=None):
        await self.inner.append(self.prefix + kind, session_id=session_id, group_id=group_id, round=round,
                                participant_id=participant_id, payload=payload)
