"""GroupRuntime: phases, timers, timeouts, validation and what each participant receives."""

import asyncio
import json

import pytest

from app.game.runtime import ActionError, GroupRuntime
from app.game.store import MemoryEventStore

FAST = {
    "group.rounds_min": 3, "group.rounds_max": 3,
    "phases.event.seconds": 0.05, "phases.policy.seconds": 0.05, "phases.communication.seconds": 0.05,
    "phases.decision.seconds": 0.08, "phases.resolution.seconds": 0.05, "phases.grace_seconds": 0.02,
}
SEATS = ["p_a", "p_b", "p_c", "p_d"]


class FakeTransport:
    def __init__(self):
        self.sent = []          # (participant_id, event, payload)
        self.listeners = []

    async def send(self, pid, event, payload):
        self.sent.append((pid, event, payload))
        for fn in self.listeners:
            fn(pid, payload)

    def last(self, pid):
        return next(p for q, _e, p in reversed(self.sent) if q == pid)


@pytest.fixture
def fast_cfg(make_cfg):
    return make_cfg(FAST)


def make_runtime(cfg, transport=None, store=None, seed=7):
    return GroupRuntime(group_id="S-g001", session_id="S", condition="none", seed=seed, cfg=cfg, seats=SEATS,
                        store=store or MemoryEventStore(), transport=transport or FakeTransport())


async def wait_for_phase(rt, phase, rnd=None, timeout=3.0):
    async def _w():
        while not (rt.phase == phase and (rnd is None or rt.round == rnd)):
            await asyncio.sleep(0.002)
    await asyncio.wait_for(_w(), timeout)


async def test_all_timeouts_game_completes(fast_cfg):
    store = MemoryEventStore()
    rt = make_runtime(fast_cfg, store=store)
    await asyncio.wait_for(rt.start(), 5)
    assert rt.status == "finished" and len(rt.ledgers) == 3
    decisions = store.of_kind("decision")
    assert len(decisions) == 12 and all(d["payload"]["timeout"] for d in decisions)
    first = [d for d in decisions if d["round"] == 1][0]["payload"]
    a = fast_cfg.timeout_default_allocation
    assert (first["harvest"], first["contribute"], first["save"]) == (a["harvest"], a["contribute"], a["save"])
    ended = store.of_kind("phase_ended")
    assert {e["payload"]["ended_by"] for e in ended} == {"timeout"}
    assert [e["payload"]["phase"] for e in ended[:4]] == ["event", "communication", "decision", "resolution"]
    assert len(store.of_kind("game_finished")) == 1 and len(store.of_kind("round_resolved")) == 3


async def test_phases_end_early_when_everyone_is_done(make_cfg):
    cfg = make_cfg({**FAST, **{f"phases.{p}.seconds": 30 for p in ("event", "communication", "decision", "resolution")}})
    transport, store = FakeTransport(), MemoryEventStore()
    rt = make_runtime(cfg, transport, store)
    rt.start()
    for t in (1, 2, 3):
        for phase in ("event", "communication"):
            await wait_for_phase(rt, phase, t)
            for pid in SEATS:
                await rt.mark_ready(pid, phase)
        await wait_for_phase(rt, "decision", t)
        for i, pid in enumerate(SEATS):
            await rt.submit_decision(pid, {"round": t, "harvest": i, "contribute": 10 - i, "save": 0,
                                           "slider_changes": 3, "client_response_ms": 1500})
        await wait_for_phase(rt, "resolution", t)
        for pid in SEATS:
            await rt.submit_rating(pid, {"round": t, "rating": 5})
            await rt.mark_ready(pid, "resolution")
    await asyncio.wait_for(rt.task, 3)
    assert rt.status == "finished"
    assert {e["payload"]["ended_by"] for e in store.of_kind("phase_ended")} == {"all_ready"}
    dec = store.of_kind("decision")
    assert len(dec) == 12 and not any(d["payload"]["timeout"] for d in dec)
    assert dec[0]["payload"]["slider_changes"] == 3 and dec[0]["payload"]["response_ms"] >= 0
    assert len(store.of_kind("fairness_rating")) == 12
    assert rt.ledgers[0].players[3].contribute_effort == 7
    final = transport.last("p_a")["final"]
    assert final["payoff_coins"] == pytest.approx(rt.settlement.payoff_coins[0])


async def test_timeout_repeats_last_allocation(make_cfg):
    cfg = make_cfg({**FAST, "phases.decision.seconds": 0.3})
    store = MemoryEventStore()
    rt = make_runtime(cfg, store=store)
    rt.start()
    await wait_for_phase(rt, "decision", 1)
    await rt.submit_decision("p_a", {"round": 1, "harvest": 9, "contribute": 1, "save": 0})
    await asyncio.wait_for(rt.task, 5)
    r2 = [d["payload"] for d in store.of_kind("decision") if d["round"] == 2 and d["payload"]["seat"] == 0][0]
    assert r2["timeout"] and (r2["harvest"], r2["contribute"], r2["save"]) == (9, 1, 0)


async def test_invalid_actions_rejected_and_logged(make_cfg):
    cfg = make_cfg({**FAST, "phases.event.seconds": 0.3, "phases.decision.seconds": 1.0})
    store = MemoryEventStore()
    rt = make_runtime(cfg, store=store)
    rt.start()
    await wait_for_phase(rt, "event", 1)
    with pytest.raises(ActionError, match="decision phase"):
        await rt.submit_decision("p_a", {"round": 1, "harvest": 4, "contribute": 3, "save": 3})
    with pytest.raises(ActionError):
        await rt.mark_ready("p_a", "decision")
    with pytest.raises(ActionError, match="not a member"):
        await rt.mark_ready("p_zzz", "event")
    await wait_for_phase(rt, "decision", 1)
    bad = [
        {"round": 1, "harvest": 4, "contribute": 3, "save": 4},
        {"round": 1, "harvest": 4.5, "contribute": 3, "save": 2.5},
        {"round": 1, "harvest": "x", "contribute": 3, "save": 3},
        {"round": 2, "harvest": 4, "contribute": 3, "save": 3},
        {"round": 1, "harvest": 4, "contribute": 3, "save": 3, "transfer_to": 0, "transfer_amount": 5},
        {"round": 1, "harvest": 4, "contribute": 3, "save": 3, "transfer_to": 1, "transfer_amount": 1e9},
        {"round": 1, "harvest": True, "contribute": 3, "save": 6},
    ]
    for data in bad:
        with pytest.raises(ActionError):
            await rt.submit_decision("p_a", data)
    assert len(store.of_kind("action_rejected")) == len(bad) + 1
    await rt.submit_decision("p_a", {"round": 1, "harvest": 4, "contribute": 3, "save": 3,
                                     "transfer_to": 2, "transfer_amount": 10})
    with pytest.raises(ActionError, match="already"):
        await rt.submit_decision("p_a", {"round": 1, "harvest": 4, "contribute": 3, "save": 3})
    with pytest.raises(ActionError):
        await rt.submit_rating("p_a", {"round": 1, "rating": 5})
    rt.task.cancel()


async def test_rating_validation(make_cfg):
    cfg = make_cfg({**FAST, "phases.resolution.seconds": 1.0})
    rt = make_runtime(cfg)
    rt.start()
    await wait_for_phase(rt, "resolution", 1)
    for bad in ({"round": 1, "rating": 0}, {"round": 1, "rating": 8}, {"round": 2, "rating": 4}, {"round": 1}):
        with pytest.raises(ActionError):
            await rt.submit_rating("p_b", bad)
    await rt.submit_rating("p_b", {"round": 1, "rating": 7})
    assert rt.snapshot_for(1)["my_rating"] == 7 and rt.snapshot_for(0)["my_rating"] is None
    rt.task.cancel()


async def test_no_one_sees_another_players_pending_decision(make_cfg):
    """Authorization: during the decision phase only the submitter sees their own choice."""
    cfg = make_cfg({**FAST, "phases.decision.seconds": 1.0})
    transport = FakeTransport()
    rt = make_runtime(cfg, transport)
    rt.start()
    await wait_for_phase(rt, "decision", 1)
    await rt.submit_decision("p_a", {"round": 1, "harvest": 1, "contribute": 2, "save": 7,
                                     "transfer_to": 3, "transfer_amount": 12.345})
    for seat in (1, 2, 3):
        snap = rt.snapshot_for(seat)
        assert snap["my_decision"] is None
        assert "12.345" not in json.dumps(snap)
    assert rt.snapshot_for(0)["my_decision"]["transfer_amount"] == 12.345
    # Messages actually sent to others after the submission do not contain it either.
    for pid, _e, payload in transport.sent:
        if pid != "p_a":
            assert "12.345" not in json.dumps(payload)
    rt.task.cancel()


async def test_snapshot_never_reveals_hidden_information(fast_cfg):
    rt = make_runtime(fast_cfg)
    await asyncio.wait_for(rt.start(), 5)
    for seat in range(4):
        snap = rt.snapshot_for(seat)
        text = json.dumps(snap)
        assert "n_rounds" not in text and "seed" not in text
        for other in range(4):
            if other != seat:
                assert repr(rt.state.wealth[other]) not in text and SEATS[other] not in text
        assert snap["observation"]["wealth"] == rt.state.wealth[seat]


async def test_runtime_checks_condition_and_coordinator(fast_cfg):
    kw = dict(group_id="g", session_id="S", seed=1, cfg=fast_cfg, seats=SEATS, store=MemoryEventStore(),
              transport=FakeTransport())
    with pytest.raises(ValueError, match="unknown condition"):
        GroupRuntime(condition="ai", **kw)
    with pytest.raises(ValueError, match="exactly one coordinator"):
        GroupRuntime(condition="human", **kw)
    with pytest.raises(ValueError, match="no coordinator"):
        GroupRuntime(condition="none", coordinator="p_c", **kw)
