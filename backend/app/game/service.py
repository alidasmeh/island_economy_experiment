"""Process-wide game service: config, event store and lobby (created at app startup)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.engine import Config, load_config
from app.sim.runner import code_version

from .lobby import Lobby
from .runtime import Transport
from .store import EventStore, SqlEventStore


@dataclass
class GameService:
    cfg: Config
    store: EventStore
    lobby: Lobby
    code_version: str


_service: GameService | None = None


def init_service(transport: Transport, *, cfg: Config | None = None, store: EventStore | None = None) -> GameService:
    global _service
    cfg = cfg or load_config(os.getenv("ISLAND_PARAMS") or None)
    store = store or SqlEventStore()
    version = code_version()
    _service = GameService(cfg=cfg, store=store, lobby=Lobby(cfg, store, transport, version), code_version=version)
    return _service


def get_service() -> GameService:
    if _service is None:
        raise RuntimeError("game service not initialized")
    return _service
