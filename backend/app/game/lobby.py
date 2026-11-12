"""Onboarding, allocation, waiting room, group formation and exit.

Participant steps (``Participant.status``)::

    joined -> consented -> quiz_passed -> practice -> practice_done -> waiting -> playing
           -> finished (questionnaire open) -> completed (payment page)
    exits: no_consent | quiz_failed | no_group (waited too long) | aborted

The server enforces the order: nobody enters the waiting room without consent, a
passed quiz and (if configured) finished practice rounds.

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
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.bots import make_bot
from app.engine import Config, draw_group_setup

from . import onboarding, repo
from .runtime import ActionError, GroupRuntime, Transport, bot_id
from .store import EventStore, PrefixedEventStore

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
    waiting_since: dict[str, float] = field(default_factory=dict)   # first entry into the waiting room
    settings: dict[str, Any] = field(default_factory=dict)

    def unstarted(self) -> list[int]:
        return [i for i in range(len(self.assignments)) if i not in self.started]


class Lobby:
    def __init__(self, cfg: Config, store: EventStore, transport: Transport, code_version: str = "",
                 rng: random.Random | None = None, clock: Callable[[], float] = time.time):
        self.cfg, self.store, self.transport, self.code_version = cfg, store, transport, code_version
        self.rng = rng or _sysrand
        self.clock = clock
        self.sessions: dict[str, SessionLive] = {}
        self.groups: dict[str, GroupRuntime] = {}
        self.by_participant: dict[str, GroupRuntime] = {}
        self.practices: dict[str, GroupRuntime] = {}      # participant id -> practice runtime
        self.connections: dict[str, int] = {}

    async def _session(self, code: str) -> SessionLive:
        if code not in self.sessions:
            s = await repo.get_session(code)
            if s is None:
                raise ActionError("unknown session")
            existing = await repo.groups_in_session(code)
            self.sessions[code] = SessionLive(code=code, assignments=list(s.assignments),
                                              started={g.index_in_session for g in existing},
                                              settings=dict(s.settings or {}))
        return self.sessions[code]

    def runtime_of(self, participant_id: str) -> GroupRuntime | None:
        """The group the participant is playing in, or their practice rounds."""
        return self.by_participant.get(participant_id) or self.practices.get(participant_id)

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
        if p.status in ("playing", "finished", "completed", "aborted"):
            raise ActionError("you have already been assigned to a group")
        if p.status not in self._may_wait():
            raise ActionError("please finish the instructions, the quiz and the practice rounds first")
        s = await self._session(code)
        slot = await self.allocate(p)
        if slot is None or not any(s.assignments[i]["condition"] == slot[0] for i in s.unstarted()):
            await self.store.append("session_full", session_id=code, participant_id=pid, payload={})
            raise ActionError("this session is full")
        if pid not in s.waiting:
            s.waiting.append(pid)
            s.waiting_since.setdefault(pid, self.clock())
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
                          code_version=self.code_version, on_finish=self._on_finish, on_flag=self._on_flag)
        self.groups[group_id] = rt
        for pid in rt.members():
            self.by_participant[pid] = rt
        log.info("group %s formed (%s, seed %s)", group_id, condition, seed)
        rt.start()

    async def _on_flag(self, rt: GroupRuntime, flag: dict[str, Any]) -> None:
        await repo.flag_group(rt.group_id, flag)

    async def _on_finish(self, rt: GroupRuntime) -> None:
        bonuses: dict[str, float] = {}
        if rt.settlement is not None:
            st = rt.settlement
            bonuses = {pid: round(st.payoff_money[i], 2) for i, pid in enumerate(rt.seats)}
            if rt.coordinator:
                bonuses[rt.coordinator] = round(st.coordinator_payoff_money, 2)
        await repo.finish_group(rt.group_id, rt.status, bonuses)

    async def broadcast_waiting(self, s: SessionLive) -> None:
        for pid in s.waiting:
            await self.transport.send(pid, "state", self.waiting_snapshot(s, pid))

    def waiting_snapshot(self, s: SessionLive, pid: str) -> dict[str, Any]:
        cond, role = s.alloc.get(pid, ("none", "player"))
        size = self.group_size(cond)
        since = s.waiting_since.get(pid, self.clock())
        return {"view": "waiting", "condition": cond, "role": role,
                "n_waiting": min(len(self._waiting_with(s, cond)), size), "n_needed": size,
                "can_leave_at_ms": int((since + self.cfg.waiting_room_max_seconds) * 1000),
                "server_now_ms": int(self.clock() * 1000)}

    def _may_wait(self) -> tuple[str, ...]:
        return ("practice_done", "waiting") + (("quiz_passed",) if self.cfg.practice_rounds == 0 else ())

    async def snapshot(self, p) -> dict[str, Any]:
        """What the participant should see now, from their step in the study."""
        if p.status in ("completed", "quiz_failed", "no_group", "aborted", "no_consent"):
            return await self.exit_snapshot(p)
        rt = self.by_participant.get(p.id)
        if rt is not None:
            return rt.snapshot_for_participant(p.id)
        if p.status == "finished":
            return {"view": "questionnaire", "condition": p.condition, "role": p.role,
                    "items": self.questionnaire_public(p)}
        if p.status == "playing":
            # Assigned to a group this process no longer runs (e.g. after a server restart).
            return {"view": "unavailable"}
        s = await self._session(p.session_id)
        if p.status == "joined":
            return {"view": "lobby", "step": "consent", "consent_version": self.cfg.consent_version}
        if p.id in s.waiting:
            return self.waiting_snapshot(s, p.id)
        slot = await self.allocate(p)
        if slot is None:
            return {"view": "full"}
        base = {"view": "lobby", "condition": slot[0], "role": slot[1]}
        if p.status == "consented":
            return {**base, "step": "instructions", "quiz": self._quiz_state(p, slot)}
        if p.status in ("quiz_passed", "practice") and self.cfg.practice_rounds > 0:
            prt = self.practices.get(p.id)
            if prt is not None:
                return prt.snapshot_for_participant(p.id)
            return {**base, "step": "practice", "practice_rounds": self.cfg.practice_rounds,
                    "n_computer": self.cfg.n_players if slot[1] == "coordinator" else self.cfg.n_players - 1}
        return {**base, "step": "ready"}   # the client now enters the waiting room

    def _quiz_state(self, p, slot: tuple[str, str]) -> dict[str, Any]:
        qs = onboarding.quiz_questions(self.cfg, slot[0], slot[1])
        return {"questions": onboarding.public_quiz(qs), "attempts_used": p.quiz_attempts or 0,
                "max_attempts": self.cfg.quiz_max_attempts}

    def questionnaire_public(self, p) -> list[dict[str, Any]]:
        return [it.public() for it in onboarding.questionnaire_items(p.condition or "none", p.role or "player")]

    async def exit_snapshot(self, p) -> dict[str, Any]:
        s = await self._session(p.session_id)
        outcome = p.status
        info = onboarding.completion_info(self.cfg, s.settings, outcome)
        paid_bonus = p.bonus if outcome == "completed" else None
        return {"view": "exit", **info, "role": p.role, "condition": p.condition,
                "show_up_fee": self.cfg.show_up_fee if outcome != "no_consent" else None,
                "bonus": paid_bonus, "currency": self.cfg.currency}

    async def _push(self, p) -> None:
        await self.transport.send(p.id, "state", await self.snapshot(p))

    async def _release_seat(self, s: SessionLive, pid: str) -> None:
        """A participant who leaves before a group starts no longer holds an allocation."""
        if pid in s.waiting:
            s.waiting.remove(pid)
        s.alloc.pop(pid, None)
        await self.broadcast_waiting(s)

    # ------------------------------------------------------------------ onboarding steps

    async def give_consent(self, p, data: Any) -> dict[str, Any]:
        if p.status != "joined":
            raise ActionError("consent has already been recorded")
        if not isinstance(data, dict) or not isinstance(data.get("consent"), bool):
            raise ActionError("invalid consent answer")
        given = data["consent"]
        status = "consented" if given else "no_consent"
        await repo.update_participant(p.id, status=status)
        await self.store.append("consent", session_id=p.session_id, participant_id=p.id,
                                payload={"given": given, "version": self.cfg.consent_version})
        p.status = status
        await self._push(p)
        return {"ok": True}

    async def submit_quiz(self, p, data: Any) -> dict[str, Any]:
        if p.status != "consented":
            raise ActionError("the quiz is not open")
        s = await self._session(p.session_id)
        slot = await self.allocate(p)
        if slot is None:
            raise ActionError("this session is full")
        qs = onboarding.quiz_questions(self.cfg, slot[0], slot[1])
        try:
            passed, wrong, answers = onboarding.grade_quiz(qs, (data or {}).get("answers") if isinstance(data, dict)
                                                           else None)
        except ValueError as exc:
            raise ActionError(str(exc)) from None
        attempt = (p.quiz_attempts or 0) + 1
        failed_out = not passed and attempt >= self.cfg.quiz_max_attempts
        status = "quiz_passed" if passed else ("quiz_failed" if failed_out else "consented")
        await repo.update_participant(p.id, quiz_attempts=attempt, status=status)
        await self.store.append("quiz_attempt", session_id=p.session_id, participant_id=p.id,
                                payload={"attempt": attempt, "passed": passed, "answers": answers, "wrong": wrong,
                                         "condition": slot[0], "role": slot[1],
                                         "seconds": _seconds((data or {}).get("seconds"))})
        p.quiz_attempts, p.status = attempt, status
        if failed_out:
            await self._release_seat(s, p.id)
        await self._push(p)
        return {"ok": True, "passed": passed, "wrong": wrong, "attempts_left": self.cfg.quiz_max_attempts - attempt}

    async def start_practice(self, p) -> dict[str, Any]:
        if self.cfg.practice_rounds == 0 or p.status not in ("quiz_passed", "practice"):
            raise ActionError("practice rounds are not open")
        if p.id in self.practices:
            return {"ok": True}
        s = await self._session(p.session_id)
        slot = await self.allocate(p)
        if slot is None:
            raise ActionError("this session is full")
        n = self.cfg.n_players
        names = self.cfg.practice_bots
        if slot[1] == "coordinator":   # sets rules for N computer islanders
            seats = [bot_id(i) for i in range(n)]
            bots = {i: make_bot(names[i], self.cfg) for i in range(n)}
            condition, coordinator = "human", p.id
        else:                          # seat A; the others are computer islanders (no coordinator, no rules)
            seats = [p.id] + [bot_id(i) for i in range(1, n)]
            bots = {i: make_bot(names[i], self.cfg) for i in range(1, n)}
            condition, coordinator = "none", None
        rt = GroupRuntime(group_id=f"{s.code}-practice-{p.id}", session_id=s.code, condition=condition,
                          seed=self.cfg.practice_seed, cfg=self.cfg, seats=seats, coordinator=coordinator,
                          store=PrefixedEventStore(self.store, "practice_"), transport=self.transport,
                          code_version=self.code_version, bots=bots, practice=True,
                          n_rounds=self.cfg.practice_rounds)
        self.practices[p.id] = rt
        await repo.update_participant(p.id, status="practice")
        await self.store.append("practice_requested", session_id=s.code, participant_id=p.id,
                                payload={"role": slot[1], "rounds": self.cfg.practice_rounds,
                                         "bots": {str(i): b.name for i, b in bots.items()}})
        rt.start()
        return {"ok": True}

    async def finish_practice(self, p) -> dict[str, Any]:
        rt = self.practices.get(p.id)
        if p.status != "practice" or rt is None:
            raise ActionError("no practice rounds to finish")
        if rt.status == "running":
            raise ActionError("the practice rounds are not over yet")
        self.practices.pop(p.id, None)
        await repo.update_participant(p.id, status="practice_done")
        await self.store.append("practice_finished", session_id=p.session_id, participant_id=p.id,
                                payload={"status": rt.status})
        p.status = "practice_done"
        await self._push(p)
        return {"ok": True}

    async def leave_after_waiting(self, p) -> dict[str, Any]:
        """After waiting_room_max_seconds a participant may end the study with the no_group code."""
        s = await self._session(p.session_id)
        if p.id not in s.waiting:
            raise ActionError("you are not in the waiting room")
        waited = self.clock() - s.waiting_since.get(p.id, self.clock())
        if waited < self.cfg.waiting_room_max_seconds:
            raise ActionError("please wait a little longer")
        await repo.update_participant(p.id, status="no_group")
        await self.store.append("waiting_room_left", session_id=s.code, participant_id=p.id,
                                payload={"reason": "no_group", "waited_seconds": round(waited, 1)})
        await self._release_seat(s, p.id)
        p.status = "no_group"
        await self._push(p)
        return {"ok": True}

    async def submit_questionnaire(self, p, data: Any) -> dict[str, Any]:
        if p.status != "finished":
            raise ActionError("the questionnaire is not open")
        items = onboarding.questionnaire_items(p.condition or "none", p.role or "player")
        try:
            answers = onboarding.clean_questionnaire(items, (data or {}).get("answers") if isinstance(data, dict)
                                                     else None)
        except ValueError as exc:
            raise ActionError(str(exc)) from None
        await self.store.append("questionnaire", session_id=p.session_id, group_id=p.group_id,
                                participant_id=p.id,
                                payload={"answers": answers, "role": p.role, "condition": p.condition,
                                         "seconds": _seconds((data or {}).get("seconds"))})
        await repo.update_participant(p.id, status="completed")
        await self.store.append("completed", session_id=p.session_id, group_id=p.group_id, participant_id=p.id,
                                payload={"bonus": p.bonus})
        self.by_participant.pop(p.id, None)
        p.status = "completed"
        await self._push(p)
        return {"ok": True}

    async def shutdown(self) -> None:
        for rt in [*self.groups.values(), *self.practices.values()]:
            if rt.task and not rt.task.done():
                rt.task.cancel()


def _seconds(v: Any) -> int | None:
    """Client-reported duration, bounded."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return max(0, min(int(v), 86400))
