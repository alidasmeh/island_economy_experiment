"""Communication and bribery state of one group (section 8).

Pure bookkeeping, no I/O: the GroupRuntime calls these methods, logs what they
return and decides who receives which snapshot. Everything here is plain text;
nothing is ever rendered as HTML.

Actors are ``"p0" .. "p{N-1}"`` (islanders by seat) and ``"coordinator"``.

* Public chat: everyone in the group, including the coordinator.
* Direct messages: any member to any other member; only sender and recipient see them.
* Bribe offers (human condition): an islander offers coins to the coordinator with an
  optional note. The amount is held in escrow (unavailable for transfers) until the
  coordinator accepts or refuses; offers still pending when the communication phase
  ends are refused automatically. Accepted offers are paid in resolution step 10.
* The coordinator's bribe income is capped per game; an offer that would exceed the
  cap cannot be accepted.
"""

from __future__ import annotations

import math
import re
from collections import deque
from typing import Any

from app.engine.config import Config

from .errors import ActionError

COORDINATOR = "coordinator"
FAVOR_KINDS = ("quota_exempt", "audit_immune", "double_redistribution_weight")
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_MANY_NEWLINES = re.compile(r"\n{3,}")
EPS = 1e-9


def actor_of_seat(seat: int) -> str:
    return f"p{seat}"


def clean_text(value: Any, max_chars: int, *, what: str, allow_empty: bool = False) -> str:
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ActionError(f"{what} must be text")
    text = _MANY_NEWLINES.sub("\n\n", _CONTROL.sub("", value.replace("\r\n", "\n"))).strip()
    if not text and not allow_empty:
        raise ActionError(f"{what} is empty")
    if len(text) > max_chars:
        raise ActionError(f"{what} is longer than {max_chars} characters")
    return text


class Comms:
    def __init__(self, cfg: Config, n_players: int, has_coordinator: bool):
        self.cfg = cfg
        self.n_players = n_players
        self.has_coordinator = has_coordinator
        self.messages: list[dict[str, Any]] = []
        self.offers: dict[str, dict[str, Any]] = {}
        self._recent: dict[str, deque[float]] = {}
        self._per_round: dict[tuple[str, int], int] = {}

    # ------------------------------------------------------------------ helpers

    def actors(self) -> list[str]:
        return [actor_of_seat(i) for i in range(self.n_players)] + ([COORDINATOR] if self.has_coordinator else [])

    def _limit(self, actor: str, rnd: int, now: float) -> None:
        q = self._recent.setdefault(actor, deque())
        while q and q[0] <= now - self.cfg.rate_limit_window_seconds:
            q.popleft()
        if len(q) >= self.cfg.rate_limit_messages:
            raise ActionError("you are sending messages too quickly; please wait a moment")
        if self._per_round.get((actor, rnd), 0) >= self.cfg.max_messages_per_round:
            raise ActionError("you have reached the message limit for this round")

    def _count(self, actor: str, rnd: int, now: float) -> None:
        self._recent.setdefault(actor, deque()).append(now)
        self._per_round[(actor, rnd)] = self._per_round.get((actor, rnd), 0) + 1

    # ------------------------------------------------------------------ messages

    def add_message(self, sender: str, data: dict[str, Any], rnd: int, now: float) -> dict[str, Any]:
        channel = data.get("channel")
        if channel not in ("public", "direct"):
            raise ActionError("unknown channel")
        to = None
        if channel == "direct":
            to = data.get("to")
            if to not in self.actors() or to == sender:
                raise ActionError("unknown recipient")
        text = clean_text(data.get("text"), self.cfg.message_max_chars, what="message")
        self._limit(sender, rnd, now)
        self._count(sender, rnd, now)
        msg = {"id": f"m{len(self.messages) + 1}", "round": rnd, "ts_ms": int(now * 1000), "channel": channel,
               "from": sender, "to": to, "text": text}
        self.messages.append(msg)
        return msg

    def visible_messages(self, actor: str) -> list[dict[str, Any]]:
        mine = [m for m in self.messages if m["channel"] == "public" or actor in (m["from"], m["to"])]
        return mine[-self.cfg.snapshot_max_messages:]

    # ------------------------------------------------------------------ bribes

    def escrow(self, seat: int, rnd: int) -> float:
        return sum(o["amount"] for o in self.offers.values()
                   if o["from"] == seat and o["round"] == rnd and o["status"] in ("pending", "accepted"))

    def round_offers(self, rnd: int) -> list[dict[str, Any]]:
        return [o for o in self.offers.values() if o["round"] == rnd]

    def add_offer(self, seat: int, data: dict[str, Any], rnd: int, now: float, wealth: float) -> dict[str, Any]:
        if not self.has_coordinator:
            raise ActionError("there is no coordinator in this group")
        actor = actor_of_seat(seat)
        amount = data.get("amount")
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or not math.isfinite(amount):
            raise ActionError("amount must be a number")
        amount = round(float(amount), 2)
        if amount < self.cfg.bribe_min_amount:
            raise ActionError(f"the smallest offer is {self.cfg.bribe_min_amount:g} coins")
        if amount > wealth - self.escrow(seat, rnd) + EPS:
            raise ActionError("you do not have that many coins available")
        n_this_round = sum(1 for o in self.round_offers(rnd) if o["from"] == seat)
        if n_this_round >= self.cfg.bribe_max_offers_per_round:
            raise ActionError(f"at most {self.cfg.bribe_max_offers_per_round} offers per round")
        note = clean_text(data.get("note"), self.cfg.bribe_note_max_chars, what="note", allow_empty=True)
        self._limit(actor, rnd, now)
        self._count(actor, rnd, now)
        offer = {"id": f"b{len(self.offers) + 1}", "round": rnd, "ts_ms": int(now * 1000), "from": seat,
                 "amount": amount, "note": note, "status": "pending", "reply": "", "favor": None,
                 "responded_ms": None, "settled": None}
        self.offers[offer["id"]] = offer
        return offer

    def committed_income(self, rnd: int, income_so_far: float) -> float:
        """Coordinator bribe income already earned plus income from offers accepted this round."""
        accepted = sum(o["amount"] for o in self.round_offers(rnd) if o["status"] == "accepted")
        return income_so_far + self.cfg.bribe_income_rate * accepted

    def respond(self, data: dict[str, Any], rnd: int, now: float, income_so_far: float) -> dict[str, Any]:
        offer = self.offers.get(data.get("offer_id"))
        if offer is None or offer["round"] != rnd:
            raise ActionError("unknown offer")
        if offer["status"] != "pending":
            raise ActionError("this offer has already been answered")
        accept = data.get("accept")
        if not isinstance(accept, bool):
            raise ActionError("accept must be true or false")
        favor = data.get("favor") or None
        if favor is not None and (favor not in FAVOR_KINDS or not accept):
            raise ActionError("a favor can only be one of the listed kinds, granted with an accepted offer")
        reply = clean_text(data.get("reply"), self.cfg.message_max_chars, what="reply", allow_empty=True)
        if accept:
            room = self.cfg.bribe_income_cap - self.committed_income(rnd, income_so_far)
            if self.cfg.bribe_income_rate * offer["amount"] > room + EPS:
                raise ActionError("accepting this offer would go over your limit for bribe income")
        offer.update(status="accepted" if accept else "refused", reply=reply, favor=favor,
                     responded_ms=int(now * 1000))
        return offer

    def expire_pending(self, rnd: int, now: float) -> list[dict[str, Any]]:
        out = []
        for o in self.round_offers(rnd):
            if o["status"] == "pending":
                o.update(status="expired", responded_ms=int(now * 1000))
                out.append(o)
        return out

    def offers_from(self, seat: int) -> list[dict[str, Any]]:
        return [o for o in self.offers.values() if o["from"] == seat]

    # ------------------------------------------------------------------ coordinator observation

    def coordinator_inbox(self) -> list[dict[str, Any]]:
        """Direct messages to the coordinator and every bribe offer, oldest first."""
        items = [{"type": "message", "id": m["id"], "round": m["round"], "ts_ms": m["ts_ms"], "from": m["from"],
                  "text": m["text"]} for m in self.messages if m["to"] == COORDINATOR]
        items += [{"type": "bribe", "offer_id": o["id"], "round": o["round"], "ts_ms": o["ts_ms"],
                   "from": actor_of_seat(o["from"]), "amount": o["amount"], "note": o["note"],
                   "status": o["status"], "reply": o["reply"], "favor": o["favor"], "settled": o["settled"]}
                  for o in self.offers.values()]
        items.sort(key=lambda x: x["ts_ms"])
        return items[-self.cfg.snapshot_max_messages:]

    def public_chat(self) -> list[dict[str, Any]]:
        return [m for m in self.messages if m["channel"] == "public"][-self.cfg.snapshot_max_messages:]
