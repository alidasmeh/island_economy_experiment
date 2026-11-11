"""Allocation, waiting room and group formation.

A session plans a list of groups (``assignments``: condition + seed). Each
participant is **allocated** a condition and a role (player | coordinator) when
they first connect, before the instructions, so the instructions can be
specific to both. Allocation fills the earliest planned group that still needs
people; inside that group the role is drawn at random, weighted by the number of
open seats (so in a ``human`` group each newcomer becomes the coordinator with
probability 1 / (N + 1) while all seats are open). Only participants who are
connected or in the waiting room hold a seat, so people who leave during the
instructions free it for newcomers.

Participants who finish the instructions enter the waiting room. A planned group
starts as soon as the waiting room holds enough participants allocated to its
condition: N players, plus one coordinator in ``human``. Groups may therefore
start out of order (e.g. a ``none`` group while a ``human`` group waits for a
coordinator).

All live state is in memory in this single process (deploy with one replica).
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from typing import Any

from app.engine import Config, draw_group_setup

from . import repo
from .runtime import ActionError, GroupRuntime, Transport
from .store import EventStore

log = logging.getLogger(__name__)

SUPPORTED_CONDITIONS = ("none", "human")
_sysrand = random.SystemRandom()


def plan_assignments(conditions: list[str], seeds: list[int]) -> list[dict[str, Any]]:
    """Matched design: each seed is played once under every condition, interleaved."""
    return [{"condition": c, "seed": s} for s in seeds for c in conditions]


@dataclass
class SessionLive:
    code: str
    assignments: list[dict[str, Any]]
    started: set[int] = field(default_factory=set)
    alloc: dict[str, tuple[str, str]] = field(default_factory=dict)   # pid -> (condition, role), not yet grouped
    waiting: list[str] = field(default_factory=list)

    def unstarted(self) -> list[int]:
        return [i for i in range(len(self.assignments)) if i not in self.started]


class Lobby:
    def __init__(self, cfg: Config, store: EventStore, transport: Transport, code_version: str = "",
                 rng: random.Random | None = None):
        self.cfg, self.store, self.transport, self.code_version = cfg, store, transport, code_version
        self.rng = rng or _sysrand
        self.sessions: dict[str, SessionLive] = {}
        self.groups: dict[str, GroupRuntime] = {}
        self.by_participant: dict[str, GroupRuntime] = {}
        self.connections: dict[str, int] = {}

    async def _session(self, code: str) -> SessionLive:
        if code not in self.sessions:
            s = await repo.get_session(code)
            if s is None:
                raise ActionError("unknown session")
            existing = await repo.groups_in_session(code)
            self.sessions[code] = SessionLive(code=code, assignments=list(s.assignments),
                                              started={g.index_in_session for g in existing})
        return self.sessions[code]

    def runtime_of(self, participant_id: str) -> GroupRuntime | None:
        return self.by_participant.get(participant_id)

    def needs(self, condition: str) -> dict[str, int]:
        return {"player": self.cfg.n_players, **({"coordinator": 1} if condition == "human" else {})}

    def group_size(self, condition: str) -> int:
        return sum(self.needs(condition).values())

    # ------------------------------------------------------------------ connections

    def connected(self, participant_id: str) -> None:
        self.connections[participant_id] = self.connections.get(participant_id, 0) + 1

    def disconnected(self, participant_id: str) -> int:
        n = max(0, self.connections.get(participant_id, 0) - 1)
        if n:
            self.connections[participant_id] = n
        else:
            self.connections.pop(participant_id, None)
        return n

    def _holds_seat(self, s: SessionLive, pid: str) -> bool:
        return pid in s.waiting or self.connections.get(pid, 0) > 0

    # ------------------------------------------------------------------ allocation

    async def allocate(self, p) -> tuple[str, str] | None:
        """Condition and role for participant ``p`` (allocated once, then fixed). None = session full."""
        s = await self._session(p.session_id)
        if p.condition and p.role:
            s.alloc.setdefault(p.id, (p.condition, p.role))
            return p.condition, p.role
        if p.id in s.alloc:
            return s.alloc[p.id]
        unstarted = s.unstarted()
        if not unstarted:
            return None
        held: dict[tuple[str, str], int] = {}
        for pid, slot in s.alloc.items():
            if pid != p.id and self._holds_seat(s, pid):
                held[slot] = held.get(slot, 0) + 1
        cum: dict[tuple[str, str], int] = {}
        choice, deficits = None, {}
        for i in unstarted:
            cond = s.assignments[i]["condition"]
            for role, n in self.needs(cond).items():
                cum[(cond, role)] = cum.get((cond, role), 0) + n
            deficits = {(cond, role): cum[(cond, role)] - held.get((cond, role), 0)
                        for role in self.needs(cond)}
            deficits = {k: v for k, v in deficits.items() if v > 0}
            if deficits:
                break
        if not deficits:   # every open seat is held; overbook the earliest planned group
            cond = s.assignments[unstarted[0]]["condition"]
            deficits = {(cond, role): n for role, n in self.needs(cond).items()}
        slots = list(deficits)
        choice = self.rng.choices(slots, weights=[deficits[k] for k in slots])[0]
        s.alloc[p.id] = choice
        await repo.update_participant(p.id, condition=choice[0], role=choice[1])
        await self.store.append("allocated", session_id=s.code, participant_id=p.id,
                                payload={"condition": choice[0], "role": choice[1],
                                         "open_seats": {f"{c}/{r}": v for (c, r), v in deficits.items()}})
        return choice

    # ------------------------------------------------------------------ waiting room

    async def enter_waiting_room(self, p, client_info: dict[str, Any] | None = None) -> dict[str, Any]:
        pid, code = p.id, p.session_id
        if pid in self.by_participant:
            return {"ok": True, "in_group": True}
        if p.status in ("playing", "finished", "aborted"):
            raise ActionError("you have already been assigned to a group")
        s = await self._session(code)
        slot = await self.allocate(p)
        if slot is None or not any(s.assignments[i]["condition"] == slot[0] for i in s.unstarted()):
            await self.store.append("session_full", session_id=code, participant_id=pid, payload={})
            raise ActionError("this session is full")
        if pid not in s.waiting:
            s.waiting.append(pid)
            await repo.update_participant(pid, status="waiting")
            await self.store.append("waiting_room_entered", session_id=code, participant_id=pid,
                                    payload={"position": len(s.waiting), "condition": slot[0], "role": slot[1],
                                             **(client_info or {})})
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

    def _waiting_with(self, s: SessionLive, condition: str, role: str | None = None) -> list[str]:
        return [pid for pid in s.waiting
                if s.alloc.get(pid, ("", ""))[0] == condition and (role is None or s.alloc[pid][1] == role)]

    async def _try_form_groups(self, s: SessionLive) -> None:
        formed = True
        while formed:
            formed = False
            for i in s.unstarted():
                cond = s.assignments[i]["condition"]
                seats: dict[str, list[str]] = {}
                for role, n in self.needs(cond).items():
                    have = self._waiting_with(s, cond, role)
                    if len(have) < n:
                        break
                    seats[role] = have[:n]
                else:
                    for pid in (*seats["player"], *seats.get("coordinator", [])):
                        s.waiting.remove(pid)
                        s.alloc.pop(pid, None)
                    s.started.add(i)
                    coordinator = seats["coordinator"][0] if "coordinator" in seats else None
                    await self._start_group(s, i, cond, int(s.assignments[i]["seed"]), seats["player"], coordinator)
                    formed = True
                    break
        # Anyone still waiting for a condition with no planned group left cannot be placed.
        open_conditions = {s.assignments[i]["condition"] for i in s.unstarted()}
        for pid in [p for p in s.waiting if s.alloc.get(p, ("",))[0] not in open_conditions]:
            s.waiting.remove(pid)
            await self.store.append("session_full", session_id=s.code, participant_id=pid,
                                    payload={"while_waiting": True})
            await self.transport.send(pid, "state", {"view": "full"})

    async def _start_group(self, s: SessionLive, index: int, condition: str, seed: int, seats: list[str],
                           coordinator: str | None) -> None:
        group_id = f"{s.code}-g{index + 1:03d}"
        n_rounds = draw_group_setup(seed, self.cfg).n_rounds
        await repo.create_group(group_id=group_id, session_id=s.code, index=index, condition=condition, seed=seed,
                                n_rounds=n_rounds, seats=seats, coordinator=coordinator)
        rt = GroupRuntime(group_id=group_id, session_id=s.code, condition=condition, seed=seed, cfg=self.cfg,
                          seats=seats, coordinator=coordinator, store=self.store, transport=self.transport,
                          code_version=self.code_version, on_finish=self._on_finish)
        self.groups[group_id] = rt
        for pid in rt.members():
            self.by_participant[pid] = rt
        log.info("group %s formed (%s, seed %s)", group_id, condition, seed)
        rt.start()

    async def _on_finish(self, rt: GroupRuntime) -> None:
        await repo.finish_group(rt.group_id, rt.status)

    async def broadcast_waiting(self, s: SessionLive) -> None:
        for pid in s.waiting:
            await self.transport.send(pid, "state", self.waiting_snapshot(s, pid))

    def waiting_snapshot(self, s: SessionLive, pid: str) -> dict[str, Any]:
        cond, role = s.alloc.get(pid, ("none", "player"))
        size = self.group_size(cond)
        return {"view": "waiting", "condition": cond, "role": role,
                "n_waiting": min(len(self._waiting_with(s, cond)), size), "n_needed": size}

    async def snapshot(self, p) -> dict[str, Any]:
        rt = self.by_participant.get(p.id)
        if rt is not None:
            return rt.snapshot_for_participant(p.id)
        if p.status in ("playing", "finished", "aborted"):
            # Assigned to a group this process no longer runs (e.g. after a server restart).
            return {"view": "unavailable"}
        s = await self._session(p.session_id)
        if p.id in s.waiting:
            return self.waiting_snapshot(s, p.id)
        slot = await self.allocate(p)
        if slot is None:
            return {"view": "full"}
        return {"view": "lobby", "condition": slot[0], "role": slot[1]}

    async def shutdown(self) -> None:
        for rt in self.groups.values():
            if rt.task and not rt.task.done():
                rt.task.cancel()
