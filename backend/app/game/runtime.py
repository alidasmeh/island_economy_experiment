"""Live group runtime: round timeline, server-side timers, submissions, timeouts.

One ``GroupRuntime`` per group runs as an asyncio task. All mutations happen on
the event loop, so no locking is needed. The runtime talks to the outside world
only through two small interfaces:

* ``EventStore.append`` — append-only logging of everything that happens;
* ``Transport.send``   — push a JSON message to one participant.

What a participant receives is built by ``snapshot_for_participant``, which uses
the engine's observation functions; nothing else about other players is ever sent.

Coordinator (``human`` condition): a fifth participant who has no seat. In the
policy phase their dashboard input is turned into a ``CoordinatorAction`` and
applied when the phase ends; if nothing arrives, the previous policy stays
(logged ``timeout=true``). A non-human ``CoordinatorBackend`` (e.g. the scripted
stub used in tests) can fill the same slot through ``act(observation)``.
"""

from __future__ import annotations

import asyncio
import logging
import re
import string
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict
from typing import Any, Protocol

from app.engine import (
    Config,
    Decision,
    Policy,
    ValidationError,
    default_policy,
    draw_group_setup,
    initial_state,
    policy_preview,
    resolve_round,
    round_rng,
    settle_game,
    timeout_decision,
    validate_decision,
    validate_policy,
)
from app.engine.observation import coordinator_observation, group_summary, player_observation, public_policy
from app.engine.types import BribeOffer, Favors, RoundLedger

from app.coordinator.interface import CoordinatorAction, CoordinatorBackend

from .communication import COORDINATOR, Comms, FAVOR_KINDS, actor_of_seat
from .errors import ActionError
from .store import EventStore

log = logging.getLogger(__name__)

READY_PHASES = ("event", "communication", "resolution")
COORDINATOR_LABEL = "Coordinator"
POLICY_LEVERS = ("quota", "tax_rate", "redistribution", "match_rate", "fine", "audit_prob", "insurance",
                 "info_policy", "announcement")
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class Transport(Protocol):
    async def send(self, participant_id: str, event: str, payload: dict[str, Any]) -> None: ...


def seat_label(seat: int) -> str:
    return f"Islander {string.ascii_uppercase[seat]}"


def phases_for(condition: str) -> list[str]:
    return ["event", "communication", "decision", "resolution"] if condition == "none" else \
        ["event", "policy", "communication", "decision", "resolution"]


class GroupRuntime:
    def __init__(self, *, group_id: str, session_id: str, condition: str, seed: int, cfg: Config,
                 seats: list[str], store: EventStore, transport: Transport, code_version: str = "",
                 coordinator: str | None = None, coordinator_backend: CoordinatorBackend | None = None,
                 on_finish: Callable[["GroupRuntime"], Awaitable[None]] | None = None,
                 on_flag: Callable[["GroupRuntime", dict[str, Any]], Awaitable[None]] | None = None,
                 clock: Callable[[], float] = time.time):
        if condition not in ("none", "human"):
            raise ValueError(f"unknown condition {condition!r}")
        if len(seats) != cfg.n_players:
            raise ValueError(f"need {cfg.n_players} players, got {len(seats)}")
        if condition == "none" and (coordinator or coordinator_backend):
            raise ValueError("the no-coordinator condition has no coordinator")
        if condition == "human" and (coordinator is None) == (coordinator_backend is None):
            raise ValueError("the human condition needs exactly one coordinator (participant or backend)")
        self.group_id, self.session_id, self.condition, self.seed = group_id, session_id, condition, seed
        self.cfg, self.store, self.transport = cfg, store, transport
        self.seats = list(seats)
        self.coordinator = coordinator
        self.coordinator_backend = coordinator_backend
        self.code_version = code_version
        self.on_finish = on_finish
        self.on_flag = on_flag
        self.flags: list[dict[str, Any]] = []
        self.coordinator_missed = 0              # consecutive policy steps without confirmed rules
        self.coordinator_dropped = False
        self.drafts_this_phase = 0
        self.last_draft: dict[str, Any] | None = None
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
        self.pending_action: tuple[CoordinatorAction, dict[str, Any]] | None = None
        self.ready: set[str] = set()                      # participant ids done with the current phase
        self.comms = Comms(cfg, len(seats), has_coordinator=condition == "human")
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
            if participant_id == self.coordinator:
                raise ActionError("only islanders can do this") from None
            raise ActionError("not a member of this group") from None

    def members(self) -> list[str]:
        return self.seats + ([self.coordinator] if self.coordinator else [])

    def is_coordinator(self, participant_id: str) -> bool:
        return self.coordinator is not None and participant_id == self.coordinator

    def actor_of(self, participant_id: str) -> str:
        if self.is_coordinator(participant_id):
            return COORDINATOR
        return actor_of_seat(self.seat_of(participant_id))

    def participant_of(self, actor: str | None) -> str | None:
        if actor is None:
            return None
        return self.coordinator if actor == COORDINATOR else self.seats[int(actor[1:])]

    async def _log(self, kind: str, payload: dict[str, Any] | None = None, *, participant_id: str | None = None,
                   round: int | None = None) -> None:
        await self.store.append(kind, session_id=self.session_id, group_id=self.group_id,
                                round=self.round if round is None else round, participant_id=participant_id,
                                payload=payload or {})

    def _active_seats(self) -> list[int]:
        return list(range(len(self.seats)))

    def _ready_members(self) -> list[str]:
        """Who must be done for a ready-step to end early (a dropped-out coordinator is not waited for)."""
        return [pid for pid in self.members() if not (self.coordinator_dropped and pid == self.coordinator)]

    def phases(self) -> list[str]:
        ph = phases_for(self.condition)
        return [p for p in ph if p != "policy"] if self.coordinator_dropped else ph

    def _all_done(self) -> bool:
        if self.phase == "decision":
            return all(s in self.submissions for s in self._active_seats())
        if self.phase == "policy":
            return self.pending_action is not None
        return all(pid in self.ready for pid in self._ready_members())

    def _n_done(self) -> int:
        if self.phase == "decision":
            return len(self.submissions)
        if self.phase == "policy":
            return int(self.pending_action is not None)
        return len(self.ready)

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
                "coordinator": self.coordinator,
                "coordinator_backend": type(self.coordinator_backend).__name__ if self.coordinator_backend else None,
            }, round=0)
            for t in range(1, self.setup.n_rounds + 1):
                self.current_event = self.setup.event_for(self.cfg, t)
                for phase in phases_for(self.condition):
                    if phase == "policy" and self.coordinator_dropped:
                        continue          # rules stay fixed for the rest of the game
                    if phase == "resolution":
                        await self._resolve(t)
                    await self._run_phase(phase, t)
                    if phase == "policy":
                        await self._apply_policy()
                    elif phase == "communication":
                        await self._close_offers(t)
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
        if phase == "policy":
            self.pending_action = None
            self.drafts_this_phase = 0
            self.last_draft = None
        self._advance = asyncio.Event()
        await self._log("phase_started", {"phase": phase, "seconds": seconds, "deadline": self.deadline,
                                          "event": self.current_event.name if self.current_event else None})
        await self.broadcast()
        if phase == "policy" and self.coordinator_backend is not None:
            action = self.coordinator_backend.act(self.coordinator_view())
            self.pending_action = (action, {"response_ms": 0, "backend": type(self.coordinator_backend).__name__})
            self._advance.set()
        grace = self.cfg.phase_grace_seconds if phase in ("decision", "policy") else 0.0
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
                                        "n_done": self._n_done()})

    async def _apply_policy(self) -> None:
        """End of the policy phase: the submitted action takes effect, or the old policy stays."""
        if self.pending_action is None:
            self.coordinator_missed += 1
            await self._log("policy", {"timeout": True, "policy": self.policy.to_dict(), "changed": [],
                                       "missed_in_a_row": self.coordinator_missed},
                            participant_id=self.coordinator)
            if self.coordinator_missed >= self.cfg.coordinator_missed_policy_phases and self.coordinator:
                await self._coordinator_dropout()
            return
        self.coordinator_missed = 0
        action, meta = self.pending_action
        before = self.policy.to_dict()
        self.policy = action.policy
        after = self.policy.to_dict()
        await self._log("policy", {"timeout": False, "policy": after,
                                   "changed": [k for k in after if after[k] != before[k]], **meta},
                        participant_id=self.coordinator)

    async def _coordinator_dropout(self) -> None:
        """Section 2: the current policy stays fixed for the remaining rounds; the group is flagged."""
        self.coordinator_dropped = True
        await self._log("coordinator_dropout", {"missed_policy_steps": self.coordinator_missed,
                                                "policy_frozen": self.policy.to_dict()},
                        participant_id=self.coordinator)
        await self.add_flag({"type": "coordinator_dropout", "round": self.round})
        await self.broadcast()

    async def add_flag(self, flag: dict[str, Any]) -> None:
        self.flags.append(flag)
        await self._log("group_flagged", flag)
        if self.on_flag:
            await self.on_flag(self, flag)

    async def _close_offers(self, t: int) -> None:
        """End of communication: a scripted coordinator answers its inbox; unanswered offers are refused."""
        if self.coordinator_backend is not None:
            action = self.coordinator_backend.act(self.coordinator_view())
            for offer_id, resp in action.bribe_responses.items():
                try:
                    await self._respond(None, {"offer_id": offer_id, "accept": resp.accept, "reply": resp.reply})
                except ActionError as exc:
                    await self._log("action_rejected", {"action": "respond_bribe", "error": str(exc),
                                                        "offer_id": offer_id, "backend": True})
        for o in self.comms.expire_pending(t, self.clock()):
            await self._log("bribe_expired", {"offer_id": o["id"], "sender_seat": o["from"], "amount": o["amount"]},
                            participant_id=self.seats[o["from"]])

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
        offers = self.comms.round_offers(t)
        bribes = [BribeOffer(offer_id=o["id"], sender=o["from"], amount=o["amount"],
                             accepted=o["status"] == "accepted") for o in offers]
        new_state, ledger = resolve_round(self.state, decisions, self.policy, self.current_event,
                                          round_rng(self.seed, t), cfg=self.cfg, bribes=bribes)
        self.state = new_state
        self.ledgers.append(ledger)
        for rec in ledger.bribes:
            o = self.comms.offers[rec.offer_id]
            o["settled"] = {"executed": rec.executed, "paid": rec.paid, "detected": rec.detected,
                            "reason": rec.rejected_reason, "coordinator_income": rec.coordinator_income}
            await self._log("bribe_settled", {"offer_id": rec.offer_id, "sender_seat": rec.sender,
                                              "amount": rec.amount, "accepted": rec.accepted, **o["settled"],
                                              "favor": o["favor"]},
                            participant_id=self.seats[rec.sender])
        await self._log("round_resolved", {"policy": self.policy.to_dict(), "ledger": ledger.to_dict()})
        await self._log("state", {"state": new_state.to_dict(), "gini": ledger.group.gini,
                                  "welfare": ledger.group.welfare})

    async def _finish(self) -> None:
        self.settlement = settle_game(self.state, self.cfg, has_coordinator=self.condition == "human")
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
                              available_wealth=self.state.wealth[seat] - self.comms.escrow(seat, self.round))
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

    def coordinator_view(self):
        """The coordinator's observation (the one function both human and scripted coordinators get)."""
        return coordinator_observation(self.state, self.policy, self.cfg, ledgers=self.ledgers,
                                       event=self.current_event, inbox=self.comms.coordinator_inbox(),
                                       public_chat=self.comms.public_chat())

    async def draft_policy(self, participant_id: str, data: Any) -> dict[str, Any]:
        """A rule change in the coordinator's form: logged with a timestamp, answered with a preview.

        Nothing takes effect until ``submit_policy``. Every draft is logged (``policy_draft``) so
        the analysis can follow how the coordinator explored the levers (section 7).
        """
        if participant_id not in self.members():
            raise ActionError("not a member of this group")
        now = self.clock()
        try:
            if not self.is_coordinator(participant_id):
                raise ActionError("only the coordinator can set the rules")
            if not isinstance(data, dict):
                raise ActionError("invalid request")
            if self.phase != "policy" or self.pending_action is not None:
                raise ActionError("rules can only be drafted in the policy phase, before confirming")
            if int(data.get("round", self.round)) != self.round:
                raise ActionError("draft is for a different round")
            if self.drafts_this_phase >= self.cfg.max_drafts_per_phase:
                raise ActionError("too many changes in this step")
            policy = _parse_policy(data, self.policy, n_players=len(self.seats))
            validate_policy(policy, self.cfg, n_players=len(self.seats))
        except (ActionError, ValidationError, TypeError, ValueError) as exc:
            await self._log("action_rejected", {"action": "draft_policy", "error": str(exc),
                                                "data": data if isinstance(data, dict) else None},
                            participant_id=participant_id)
            raise ActionError(str(exc)) from None
        self.drafts_this_phase += 1
        draft = policy.to_dict()
        before = self.last_draft or self.policy.to_dict()
        self.last_draft = draft
        await self._log("policy_draft", {"policy": draft, "changed": [k for k in draft if draft[k] != before[k]],
                                         "ms_into_phase": round((now - self.phase_started) * 1000),
                                         "n": self.drafts_this_phase}, participant_id=participant_id)
        return {"ok": True, "preview": policy_preview(self.state, policy, self.current_event, self.cfg)}

    async def submit_policy(self, participant_id: str, data: dict[str, Any]) -> dict[str, Any]:
        """Coordinator dashboard input -> validated CoordinatorAction, applied when the phase ends.

        Levers not included keep their current value, and so do favors unless ``favors`` is
        sent (a full map seat -> {quota_exempt, audit_immune, double_redistribution_weight}).
        """
        if participant_id not in self.members():
            raise ActionError("not a member of this group")
        now = self.clock()
        try:
            if not self.is_coordinator(participant_id):
                raise ActionError("only the coordinator can set the rules")
            if self.phase != "policy":
                raise ActionError("rules can only be set in the policy phase")
            if int(data.get("round", self.round)) != self.round:
                raise ActionError("policy is for a different round")
            if self.pending_action is not None:
                raise ActionError("rules already submitted for this round")
            if now > self.deadline + self.cfg.phase_grace_seconds:
                raise ActionError("the policy phase is over")
            policy = _parse_policy(data, self.policy, n_players=len(self.seats))
            validate_policy(policy, self.cfg, n_players=len(self.seats))
        except (ActionError, ValidationError, TypeError, ValueError) as exc:
            await self._log("action_rejected", {"action": "submit_policy", "error": str(exc), "data": data},
                            participant_id=participant_id)
            raise ActionError(str(exc)) from None
        meta = {"response_ms": round((now - self.phase_started) * 1000),
                "client_response_ms": _opt_int(data.get("client_response_ms")),
                "lever_changes": _opt_int(data.get("lever_changes"))}
        self.pending_action = (CoordinatorAction(policy=policy), meta)
        await self._log("policy_submitted", {"policy": policy.to_dict(), **meta}, participant_id=participant_id)
        if self._all_done():
            self._advance.set()
        await self.broadcast()
        return {"ok": True}

    async def _comm_action(self, participant_id: str, action: str, data: Any, fn) -> dict[str, Any]:
        if participant_id not in self.members():
            raise ActionError("not a member of this group")
        try:
            if not isinstance(data, dict):
                raise ActionError("invalid request")
            if self.phase != "communication":
                raise ActionError("this is only possible in the communication step")
            result = await fn()
        except ActionError as exc:
            await self._log("action_rejected", {"action": action, "error": str(exc),
                                                "data": data if isinstance(data, dict) else None},
                            participant_id=participant_id)
            raise
        await self.broadcast()
        return {"ok": True, **(result or {})}

    async def send_message(self, participant_id: str, data: Any) -> dict[str, Any]:
        async def go():
            msg = self.comms.add_message(self.actor_of(participant_id), data, self.round, self.clock())
            await self._log("message", {**msg, "from_participant": participant_id,
                                        "to_participant": self.participant_of(msg["to"])},
                            participant_id=participant_id)
            return {"id": msg["id"]}
        return await self._comm_action(participant_id, "send_message", data, go)

    async def offer_bribe(self, participant_id: str, data: Any) -> dict[str, Any]:
        async def go():
            if self.is_coordinator(participant_id):
                raise ActionError("only islanders can make offers")
            if self.coordinator_dropped:
                raise ActionError("the coordinator has left the game")
            seat = self.seat_of(participant_id)
            o = self.comms.add_offer(seat, data, self.round, self.clock(), self.state.wealth[seat])
            await self._log("bribe_offered", {"offer_id": o["id"], "sender_seat": seat, "amount": o["amount"],
                                              "note": o["note"], "escrow_after": self.comms.escrow(seat, self.round)},
                            participant_id=participant_id)
            return {"offer_id": o["id"]}
        return await self._comm_action(participant_id, "offer_bribe", data, go)

    async def respond_bribe(self, participant_id: str, data: Any) -> dict[str, Any]:
        async def go():
            if not self.is_coordinator(participant_id):
                raise ActionError("only the coordinator can answer offers")
            await self._respond(participant_id, data)
        return await self._comm_action(participant_id, "respond_bribe", data, go)

    async def _respond(self, participant_id: str | None, data: dict[str, Any]) -> None:
        o = self.comms.respond(data, self.round, self.clock(), self.state.coordinator.bribe_income)
        await self._log("bribe_response", {"offer_id": o["id"], "sender_seat": o["from"], "amount": o["amount"],
                                           "accepted": o["status"] == "accepted", "reply": o["reply"],
                                           "favor": o["favor"]}, participant_id=self.coordinator)
        if o["favor"]:
            seat = o["from"]
            current = self.policy.favors_for(seat)
            self.policy.favors[seat] = Favors(**{**current.__dict__, o["favor"]: True})
            await self._log("favor_granted", {"seat": seat, "favor": o["favor"], "offer_id": o["id"],
                                              "favors": self.policy.favors[seat].__dict__},
                            participant_id=self.coordinator)

    async def mark_ready(self, participant_id: str, phase: str) -> dict[str, Any]:
        if participant_id not in self.members():
            raise ActionError("not a member of this group")
        if phase != self.phase or phase not in READY_PHASES:
            raise ActionError("not in that phase")
        if participant_id not in self.ready:
            self.ready.add(participant_id)
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
        sends = [self.transport.send(self.seats[s], "state", self.snapshot_for(s)) for s in seats]
        if only is None and self.coordinator:
            sends.append(self.transport.send(self.coordinator, "state", self.coordinator_snapshot()))
        await asyncio.gather(*sends)

    def snapshot_for_participant(self, participant_id: str) -> dict[str, Any]:
        if self.is_coordinator(participant_id):
            return self.coordinator_snapshot()
        return self.snapshot_for(self.seat_of(participant_id))

    def _common_snapshot(self) -> dict[str, Any]:
        return {
            "view": "game",
            "status": self.status,
            "condition": self.condition,
            "has_coordinator": self.condition == "human",
            "labels": [seat_label(i) for i in range(len(self.seats))],
            "phases": self.phases(),
            "coordinator_left": self.coordinator_dropped,
            "phase": self.phase,
            "round": self.round,
            "phase_seconds": self.cfg.phase_seconds.get(self.phase),
            "deadline_ms": int(self.deadline * 1000),
            "server_now_ms": int(self.clock() * 1000),
            "n_done": self._n_done(),
            "n_players": len(self.seats),
            "n_members": len(self._ready_members()),     # players + coordinator (who must be ready)
            "policy": public_policy(self.policy),
            "currency": self.cfg.currency,
            "limits": {"message_max_chars": self.cfg.message_max_chars,
                       "note_max_chars": self.cfg.bribe_note_max_chars,
                       "bribe_min_amount": self.cfg.bribe_min_amount,
                       "bribe_max_offers_per_round": self.cfg.bribe_max_offers_per_round,
                       "bribe_detection_prob": self.cfg.bribe_detection_prob,
                       "bribe_fine": self.cfg.bribe_fine},
        }

    def coordinator_snapshot(self) -> dict[str, Any]:
        """Everything the coordinator's dashboard shows; built from coordinator_observation."""
        obs = self.coordinator_view().to_dict()
        last = self.ledgers[-1] if self.ledgers else None
        pending = self.pending_action[0].policy.to_dict() if (self.phase == "policy" and self.pending_action) else None
        snap = {
            **self._common_snapshot(),
            "role": "coordinator",
            "actor": COORDINATOR,
            "seat": None,
            "label": COORDINATOR_LABEL,
            "done": (pending is not None) if self.phase == "policy" else (self.coordinator in self.ready),
            "observation": obs,
            "full_policy": self.policy.to_dict(),
            "messages": self.comms.visible_messages(COORDINATOR),
            "bribe_income_committed": self.comms.committed_income(self.round, self.state.coordinator.bribe_income),
            "bribe_income_cap": self.cfg.bribe_income_cap,
            "bribe_income_rate": self.cfg.bribe_income_rate,
            "submitted_policy": pending,
            "preview": (policy_preview(self.state, self.policy, self.current_event, self.cfg)
                        if self.phase == "policy" and self.current_event is not None else None),
            "missed_in_a_row": self.coordinator_missed,
            "missed_limit": self.cfg.coordinator_missed_policy_phases,
            "last_round_group": group_summary(last) if last else None,
            "final": None,
        }
        if self.settlement is not None:
            st = self.settlement
            snap["final"] = {
                "group_payoff_coins": sum(st.payoff_coins),
                "welfare_bonus_rate": self.cfg.welfare_bonus_rate,
                "welfare_bonus": st.coordinator_welfare_bonus,
                "bribe_income": st.coordinator_bribe_income,
                "fines": st.coordinator_fines,
                "payoff_coins": st.coordinator_payoff_coins,
                "payoff_money": st.coordinator_payoff_money,
                "coins_per_currency_unit": self.cfg.coins_per_currency_unit,
            }
        return snap

    def snapshot_for(self, seat: int) -> dict[str, Any]:
        last = self.ledgers[-1] if self.ledgers else None
        obs = player_observation(seat, self.state, self.policy, self.cfg, event=self.current_event,
                                 last_ledger=last).to_dict()
        ev = self.current_event
        mine = self.submissions.get(seat) if self.phase == "decision" else None
        snap: dict[str, Any] = {
            **self._common_snapshot(),
            "role": "player",
            "actor": actor_of_seat(seat),
            "seat": seat,
            "label": seat_label(seat),
            "done": (seat in self.submissions) if self.phase == "decision" else (self.seats[seat] in self.ready),
            "observation": obs,
            "messages": self.comms.visible_messages(actor_of_seat(seat)),
            "my_offers": self.comms.offers_from(seat),
            "escrow": self.comms.escrow(seat, self.round),
            "preview": {
                "catchability": self.cfg.catchability, "price": self.cfg.price,
                "harvest_mult": ev.harvest_mult if ev else 1.0, "price_mult": ev.price_mult if ev else 1.0,
                "saving_return_per_point": self.cfg.saving_return_per_point,
                "interest_rate": self.cfg.interest_rate, "tax_rate": self.policy.tax_rate,
                "quota": self.policy.quota, "insurance_premium": self.cfg.insurance_premium if self.policy.insurance else 0,
                "effort_points": self.cfg.effort_points,
            },
            "my_decision": ({"harvest": mine[0].harvest, "contribute": mine[0].contribute, "save": mine[0].save,
                             "transfer_to": mine[0].transfer_to, "transfer_amount": mine[0].transfer_amount}
                            if mine else None),
            "my_rating": self.ratings.get((self.round, seat)),
            "history": self._history_for(seat),
            "final": None,
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


def _parse_policy(data: dict[str, Any], current: Policy, *, n_players: int) -> Policy:
    """Dashboard input -> Policy. Missing levers keep their current value; so do favors unless sent."""
    d = current.to_dict()
    if data.get("favors") is not None:
        fav = data["favors"]
        if not isinstance(fav, dict):
            raise ValueError("favors must be a mapping")
        parsed = {}
        for k, v in fav.items():
            seat = _int(k)
            if not 0 <= seat < n_players:
                raise ValueError("favor for unknown islander")
            if not isinstance(v, dict) or set(v) - set(FAVOR_KINDS) or not all(isinstance(x, bool) for x in v.values()):
                raise ValueError("invalid favors")
            if any(v.values()):
                parsed[str(seat)] = {k2: bool(v.get(k2, False)) for k2 in FAVOR_KINDS}
        d["favors"] = parsed
    for k in POLICY_LEVERS:
        if k not in data or data[k] is None:
            continue
        v = data[k]
        if k == "quota":
            d[k] = _int(v)
        elif k in ("tax_rate", "match_rate", "fine", "audit_prob"):
            if isinstance(v, bool):
                raise ValueError(f"{k} must be a number")
            d[k] = float(v)
        elif k == "insurance":
            if not isinstance(v, bool):
                raise ValueError("insurance must be on/off")
            d[k] = v
        else:
            if not isinstance(v, str):
                raise ValueError(f"{k} must be text")
            d[k] = _CONTROL_CHARS.sub("", v).strip() if k == "announcement" else v
    return Policy.from_dict(d)


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
