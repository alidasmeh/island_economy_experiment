"""Waiting room and group formation.

Participants who enter a session's waiting room are matched, in arrival order,
into the session's next planned group (``assignments``: condition + seed).
Each formed group gets a ``GroupRuntime`` running as an asyncio task.

All live state is in memory in this single process (deploy with one replica).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.engine import Config, draw_group_setup

from . import repo
from .runtime import ActionError, GroupRuntime, Transport
from .store import EventStore

log = logging.getLogger(__name__)

SUPPORTED_CONDITIONS = ("none",)   # "human" arrives in Milestone 4


def plan_assignments(conditions: list[str], seeds: list[int]) -> list[dict[str, Any]]:
    """Matched design: each seed is played once under every condition, interleaved."""
    return [{"condition": c, "seed": s} for s in seeds for c in conditions]


@dataclass
class SessionLive:
    code: str
    assignments: list[dict[str, Any]]
    next_index: int = 0
    waiting: list[str] = field(default_factory=list)


class Lobby:
    def __init__(self, cfg: Config, store: EventStore, transport: Transport, code_version: str = ""):
        self.cfg, self.store, self.transport, self.code_version = cfg, store, transport, code_version
        self.sessions: dict[str, SessionLive] = {}
        self.groups: dict[str, GroupRuntime] = {}
        self.by_participant: dict[str, GroupRuntime] = {}

    async def _session(self, code: str) -> SessionLive:
        if code not in self.sessions:
            s = await repo.get_session(code)
            if s is None:
                raise ActionError("unknown session")
            existing = await repo.groups_in_session(code)
            self.sessions[code] = SessionLive(code=code, assignments=list(s.assignments), next_index=len(existing))
        return self.sessions[code]

    def runtime_of(self, participant_id: str) -> GroupRuntime | None:
        return self.by_participant.get(participant_id)

    async def enter_waiting_room(self, participant_id: str, session_code: str, status: str = "joined",
                                 client_info: dict[str, Any] | None = None) -> dict[str, Any]:
        if participant_id in self.by_participant:
            return {"ok": True, "in_group": True}
        if status in ("playing", "finished", "aborted"):
            raise ActionError("you have already been assigned to a group")
        s = await self._session(session_code)
        if s.next_index >= len(s.assignments):
            await self.store.append("session_full", session_id=session_code, participant_id=participant_id, payload={})
            raise ActionError("this session is full")
        if participant_id not in s.waiting:
            s.waiting.append(participant_id)
            await repo.update_participant(participant_id, status="waiting")
            await self.store.append("waiting_room_entered", session_id=session_code, participant_id=participant_id,
                                    payload={"position": len(s.waiting), **(client_info or {})})
        await self._try_form_groups(s)
        await self.broadcast_waiting(s)
        return {"ok": True}

    async def leave_waiting_room(self, participant_id: str, session_code: str, reason: str) -> None:
        s = self.sessions.get(session_code)
        if s and participant_id in s.waiting:
            s.waiting.remove(participant_id)
            await self.store.append("waiting_room_left", session_id=session_code, participant_id=participant_id,
                                    payload={"reason": reason})
            await self.broadcast_waiting(s)

    def group_size(self, condition: str) -> int:
        return self.cfg.n_players + (1 if condition == "human" else 0)

    async def _try_form_groups(self, s: SessionLive) -> None:
        while s.next_index < len(s.assignments):
            a = s.assignments[s.next_index]
            size = self.group_size(a["condition"])
            if len(s.waiting) < size:
                return
            seats, s.waiting = s.waiting[:size], s.waiting[size:]
            index = s.next_index
            s.next_index += 1
            await self._start_group(s, index, a["condition"], int(a["seed"]), seats)

    async def _start_group(self, s: SessionLive, index: int, condition: str, seed: int, seats: list[str]) -> None:
        group_id = f"{s.code}-g{index + 1:03d}"
        n_rounds = draw_group_setup(seed, self.cfg).n_rounds
        await repo.create_group(group_id=group_id, session_id=s.code, index=index, condition=condition, seed=seed,
                                n_rounds=n_rounds, seats=seats)
        rt = GroupRuntime(group_id=group_id, session_id=s.code, condition=condition, seed=seed, cfg=self.cfg,
                          seats=seats, store=self.store, transport=self.transport, code_version=self.code_version,
                          on_finish=self._on_finish)
        self.groups[group_id] = rt
        for pid in seats:
            self.by_participant[pid] = rt
        log.info("group %s formed (%s, seed %s)", group_id, condition, seed)
        rt.start()

    async def _on_finish(self, rt: GroupRuntime) -> None:
        await repo.finish_group(rt.group_id, rt.status)

    async def broadcast_waiting(self, s: SessionLive) -> None:
        for pid in s.waiting:
            await self.transport.send(pid, "state", self.waiting_snapshot(s, pid))

    def waiting_snapshot(self, s: SessionLive, pid: str) -> dict[str, Any]:
        needed = self.group_size(s.assignments[s.next_index]["condition"]) if s.next_index < len(s.assignments) else 0
        return {"view": "waiting", "n_waiting": len(s.waiting), "n_needed": needed}

    async def snapshot(self, participant_id: str, session_code: str, status: str = "joined") -> dict[str, Any]:
        rt = self.by_participant.get(participant_id)
        if rt is not None:
            return rt.snapshot_for(rt.seat_of(participant_id))
        if status in ("playing", "finished", "aborted"):
            # Assigned to a group this process no longer runs (e.g. after a server restart).
            return {"view": "unavailable"}
        s = await self._session(session_code)
        if participant_id in s.waiting:
            return self.waiting_snapshot(s, participant_id)
        return {"view": "lobby"}

    async def shutdown(self) -> None:
        for rt in self.groups.values():
            if rt.task and not rt.task.done():
                rt.task.cancel()
