"""Live group runtime: round timeline, server-side timers, submissions, timeouts.

One ``GroupRuntime`` per group runs as an asyncio task. All mutations happen on
the event loop, so no locking is needed. The runtime talks to the outside world
only through two small interfaces:

* ``EventStore.append`` — append-only logging of everything that happens;
* ``Transport.send``   — push a JSON message to one participant.

What a participant receives is built by ``snapshot_for(seat)``, which uses the
engine's observation functions; nothing else about other players is ever sent.
"""

from __future__ import annotations

import asyncio
import logging
import string
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from typing import Any, Protocol

from app.engine import (
    Config,
    Decision,
    ValidationError,
    default_policy,
    draw_group_setup,
    initial_state,
    resolve_round,
    round_rng,
    settle_game,
    timeout_decision,
    validate_decision,
)
from app.engine.observation import player_observation, public_policy
from app.engine.types import RoundLedger

from .store import EventStore

log = logging.getLogger(__name__)

READY_PHASES = ("event", "communication", "resolution")


class Transport(Protocol):
    async def send(self, participant_id: str, event: str, payload: dict[str, Any]) -> None: ...


class ActionError(Exception):
    """A participant action that is not allowed right now (returned to the client, logged)."""


def seat_label(seat: int) -> str:
    return f"Islander {string.ascii_uppercase[seat]}"


def phases_for(condition: str) -> list[str]:
    return ["event", "communication", "decision", "resolution"] if condition == "none" else \
        ["event", "policy", "communication", "decision", "resolution"]


class GroupRuntime:
    def __init__(self, *, group_id: str, session_id: str, condition: str, seed: int, cfg: Config,
                 seats: list[str], store: EventStore, transport: Transport, code_version: str = "",
                 on_finish: Callable[["GroupRuntime"], Awaitable[None]] | None = None,
                 clock: Callable[[], float] = time.time):
        if condition != "none":
            raise ValueError(f"condition {condition!r} is not available yet (Milestone 4)")
        if len(seats) != cfg.n_players:
            raise ValueError(f"need {cfg.n_players} players, got {len(seats)}")
        self.group_id, self.session_id, self.condition, self.seed = group_id, session_id, condition, seed
        self.cfg, self.store, self.transport = cfg, store, transport
        self.seats = list(seats)
        self.code_version = code_version
        self.on_finish = on_finish
        self.clock = clock

        self.setup = draw_group_setup(seed, cfg)
        self.state = initial_state(self.setup, cfg)
        self.policy = default_policy(cfg)
        self.ledgers: list[RoundLedger] = []
        self.current_event = None
        self.phase = "starting"
        self.round = 0
        self.phase_started = 0.0
        self.deadline = 0.0
        self.submissions: dict[int, tuple[Decision, dict[str, Any]]] = {}
        self.ready: set[int] = set()
        self.ratings: dict[tuple[int, int], int] = {}
        self.settlement = None
        self.status = "running"
        self._advance = asyncio.Event()
        self.task: asyncio.Task | None = None

    # ------------------------------------------------------------------ helpers

    def seat_of(self, participant_id: str) -> int:
        try:
            return self.seats.index(participant_id)
        except ValueError:
            raise ActionError("not a member of this group") from None

    async def _log(self, kind: str, payload: dict[str, Any] | None = None, *, participant_id: str | None = None,
                   round: int | None = None) -> None:
        await self.store.append(kind, session_id=self.session_id, group_id=self.group_id,
                                round=self.round if round is None else round, participant_id=participant_id,
                                payload=payload or {})

    def _active_seats(self) -> list[int]:
        return list(range(len(self.seats)))

    def _all_done(self) -> bool:
        done = set(self.submissions) if self.phase == "decision" else self.ready
        return all(s in done for s in self._active_seats())

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> asyncio.Task:
        self.task = asyncio.create_task(self.run(), name=f"group:{self.group_id}")
        return self.task

    async def run(self) -> None:
        try:
            await self._log("group_started", {
                "condition": self.condition, "seed": self.seed, "n_rounds": self.setup.n_rounds,
                "params_sha256": self.cfg.sha256, "code_version": self.code_version,
                "seats": {str(i): pid for i, pid in enumerate(self.seats)},
                "wealth0": list(self.setup.wealth0), "skills": list(self.setup.skills),
                "events": list(self.setup.events), "policy": self.policy.to_dict(),
            }, round=0)
            for t in range(1, self.setup.n_rounds + 1):
                self.current_event = self.setup.event_for(self.cfg, t)
                for phase in phases_for(self.condition):
                    if phase == "resolution":
                        await self._resolve(t)
                    await self._run_phase(phase, t)
            await self._finish()
        except asyncio.CancelledError:
            self.status = "aborted"
            await self._log("group_aborted", {"reason": "cancelled"})
            raise
        except Exception as exc:  # never let one group take the server down
            log.exception("group %s crashed", self.group_id)
            self.status = "aborted"
            await self._log("runtime_error", {"error": repr(exc), "phase": self.phase})
            await self.broadcast()

    async def _run_phase(self, phase: str, t: int) -> None:
        self.phase, self.round = phase, t
        seconds = self.cfg.phase_seconds[phase]
        self.phase_started = self.clock()
        self.deadline = self.phase_started + seconds
        self.ready = set()
        if phase == "decision":
            self.submissions = {}
        self._advance = asyncio.Event()
        await self._log("phase_started", {"phase": phase, "seconds": seconds, "deadline": self.deadline,
                                          "event": self.current_event.name if self.current_event else None})
        await self.broadcast()
        grace = self.cfg.phase_grace_seconds if phase == "decision" else 0.0
        ended_by = "all_ready"
        try:
            if self.cfg.phase_end_when_all_ready.get(phase, False):
                await asyncio.wait_for(self._advance.wait(), timeout=seconds + grace)
            else:
                await asyncio.sleep(seconds + grace)
                ended_by = "timer"
        except TimeoutError:
            ended_by = "timeout"
        await self._log("phase_ended", {"phase": phase, "ended_by": ended_by,
                                        "elapsed": self.clock() - self.phase_started,
                                        "n_done": len(self.submissions) if phase == "decision" else len(self.ready)})

    async def _resolve(self, t: int) -> None:
        decisions = []
        for seat in range(len(self.seats)):
            if seat in self.submissions:
                decisions.append(self.submissions[seat][0])
            else:
                d = timeout_decision(self.state.last_allocation[seat], self.cfg)
                decisions.append(d)
                await self._log("decision", {**self._decision_payload(seat, d), "timeout": True},
                                participant_id=self.seats[seat])
        new_state, ledger = resolve_round(self.state, decisions, self.policy, self.current_event,
                                          round_rng(self.seed, t), cfg=self.cfg, bribes=())
        self.state = new_state
        self.ledgers.append(ledger)
        await self._log("round_resolved", {"policy": self.policy.to_dict(), "ledger": ledger.to_dict()})
        await self._log("state", {"state": new_state.to_dict(), "gini": ledger.group.gini,
                                  "welfare": ledger.group.welfare})

    async def _finish(self) -> None:
        self.settlement = settle_game(self.state, self.cfg, has_coordinator=self.condition != "none")
        self.phase, self.status = "finished", "finished"
        await self._log("game_finished", {"settlement": asdict(self.settlement)})
        await self.broadcast()
        if self.on_finish:
            await self.on_finish(self)

    # ------------------------------------------------------------------ participant actions

    def _decision_payload(self, seat: int, d: Decision) -> dict[str, Any]:
        return {"seat": seat, "harvest": d.harvest, "contribute": d.contribute, "save": d.save,
                "transfer_to": d.transfer_to,
                "transfer_to_participant": self.seats[d.transfer_to] if d.transfer_to is not None else None,
                "transfer_amount": d.transfer_amount}

    async def submit_decision(self, participant_id: str, data: dict[str, Any]) -> dict[str, Any]:
        seat = self.seat_of(participant_id)
        now = self.clock()
        try:
            if self.phase != "decision":
                raise ActionError("decisions can only be submitted in the decision phase")
            if int(data.get("round", self.round)) != self.round:
                raise ActionError("decision is for a different round")
            if seat in self.submissions:
                raise ActionError("decision already submitted")
            if now > self.deadline + self.cfg.phase_grace_seconds:
                raise ActionError("the decision phase is over")
            to = data.get("transfer_to")
            amount = float(data.get("transfer_amount") or 0)
            d = Decision(_int(data.get("harvest")), _int(data.get("contribute")), _int(data.get("save")),
                         transfer_to=_int(to) if to not in (None, "") and amount > 0 else None,
                         transfer_amount=amount)
            validate_decision(d, self.cfg, seat=seat, n_players=len(self.seats),
                              available_wealth=self.state.wealth[seat])
        except (ActionError, ValidationError, TypeError, ValueError) as exc:
            await self._log("action_rejected", {"action": "submit_decision", "error": str(exc), "data": data},
                            participant_id=participant_id)
            raise ActionError(str(exc)) from None
        meta = {
            "response_ms": round((now - self.phase_started) * 1000),
            "client_response_ms": _opt_int(data.get("client_response_ms")),
            "slider_changes": _opt_int(data.get("slider_changes")),
        }
        self.submissions[seat] = (d, meta)
        await self._log("decision", {**self._decision_payload(seat, d), "timeout": False, **meta},
                        participant_id=participant_id)
        if self._all_done():
            self._advance.set()
        await self.broadcast()
        return {"ok": True}

    async def mark_ready(self, participant_id: str, phase: str) -> dict[str, Any]:
        seat = self.seat_of(participant_id)
        if phase != self.phase or phase not in READY_PHASES:
            raise ActionError("not in that phase")
        if seat not in self.ready:
            self.ready.add(seat)
            await self._log("ready", {"phase": phase, "seconds_into_phase": self.clock() - self.phase_started},
                            participant_id=participant_id)
            if self._all_done():
                self._advance.set()
            await self.broadcast()
        return {"ok": True}

    async def submit_rating(self, participant_id: str, data: dict[str, Any]) -> dict[str, Any]:
        seat = self.seat_of(participant_id)
        try:
            rnd = int(data.get("round"))
            rating = int(data.get("rating"))
        except (TypeError, ValueError):
            raise ActionError("invalid rating") from None
        if self.phase != "resolution" or rnd != self.round:
            raise ActionError("ratings can only be given on the results screen of the current round")
        if not 1 <= rating <= 7:
            raise ActionError("rating must be between 1 and 7")
        self.ratings[(rnd, seat)] = rating
        await self._log("fairness_rating", {"seat": seat, "rating": rating}, participant_id=participant_id, round=rnd)
        await self.broadcast(only=[seat])
        return {"ok": True}

    # ------------------------------------------------------------------ what participants see

    async def broadcast(self, only: list[int] | None = None) -> None:
        seats = only if only is not None else range(len(self.seats))
        await asyncio.gather(*(self.transport.send(self.seats[s], "state", self.snapshot_for(s)) for s in seats))

    def snapshot_for(self, seat: int) -> dict[str, Any]:
        last = self.ledgers[-1] if self.ledgers else None
        obs = player_observation(seat, self.state, self.policy, self.cfg, event=self.current_event,
                                 last_ledger=last).to_dict()
        ev = self.current_event
        mine = self.submissions.get(seat) if self.phase == "decision" else None
        snap: dict[str, Any] = {
            "view": "game",
            "status": self.status,
            "condition": self.condition,
            "has_coordinator": self.condition != "none",
            "seat": seat,
            "label": seat_label(seat),
            "labels": [seat_label(i) for i in range(len(self.seats))],
            "phases": phases_for(self.condition),
            "phase": self.phase,
            "round": self.round,
            "phase_seconds": self.cfg.phase_seconds.get(self.phase),
            "deadline_ms": int(self.deadline * 1000),
            "server_now_ms": int(self.clock() * 1000),
            "done": (seat in self.submissions) if self.phase == "decision" else (seat in self.ready),
            "n_done": len(self.submissions) if self.phase == "decision" else len(self.ready),
            "n_players": len(self.seats),
            "observation": obs,
            "preview": {
                "catchability": self.cfg.catchability, "price": self.cfg.price,
                "harvest_mult": ev.harvest_mult if ev else 1.0, "price_mult": ev.price_mult if ev else 1.0,
                "saving_return_per_point": self.cfg.saving_return_per_point,
                "interest_rate": self.cfg.interest_rate, "tax_rate": self.policy.tax_rate,
                "quota": self.policy.quota, "insurance_premium": self.cfg.insurance_premium if self.policy.insurance else 0,
                "effort_points": self.cfg.effort_points,
            },
            "policy": public_policy(self.policy),
            "my_decision": ({"harvest": mine[0].harvest, "contribute": mine[0].contribute, "save": mine[0].save,
                             "transfer_to": mine[0].transfer_to, "transfer_amount": mine[0].transfer_amount}
                            if mine else None),
            "my_rating": self.ratings.get((self.round, seat)),
            "history": self._history_for(seat),
            "final": None,
            "currency": self.cfg.currency,
        }
        if self.settlement is not None:
            snap["final"] = {
                "payoff_coins": self.settlement.payoff_coins[seat],
                "payoff_money": self.settlement.payoff_money[seat],
                "pool_refund": self.settlement.pool_refund[seat],
                "wealth": self.state.wealth[seat], "capital": self.state.capital[seat],
                "coins_per_currency_unit": self.cfg.coins_per_currency_unit,
            }
        return snap

    def _history_for(self, seat: int) -> list[dict[str, Any]]:
        """Own results per past round plus public group figures."""
        out = []
        for led in self.ledgers:
            p = led.players[seat]
            out.append({
                "round": led.group.round, "event": led.group.event,
                "harvest_effort": p.harvest_effort, "contribute_effort": p.contribute_effort,
                "save_effort": p.save_effort, "timeout": p.timeout, "harvest": p.harvest,
                "harvest_income": p.harvest_income, "saving_added": p.saving_added, "interest": p.interest,
                "wealth_after": p.wealth_after, "capital_after": p.capital_after,
                "round_earnings": (p.wealth_after + p.capital_after) - (p.wealth_before + p.capital_before),
                "stock_after": led.group.stock_after, "infra_after": led.group.infra_after,
            })
        return out


def _int(v: Any) -> int:
    if isinstance(v, bool):
        raise ValueError("expected an integer")
    if isinstance(v, float) and not v.is_integer():
        raise ValueError("expected an integer")
    return int(v)


def _opt_int(v: Any) -> int | None:
    try:
        return max(0, int(v)) if v is not None else None
    except (TypeError, ValueError):
        return None
