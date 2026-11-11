"""Chat, direct messages, bribe escrow, favors, the bribe cap and detection (section 8)."""

import asyncio
import json

import pytest

from app.coordinator.interface import ScriptedCoordinator
from app.game.runtime import ActionError, GroupRuntime
from app.game.store import MemoryEventStore

from .test_coordinator_runtime import COORD, make_human
from .test_runtime import FAST, SEATS, FakeTransport, make_runtime, wait_for_phase

COMM = {**FAST, "phases.communication.seconds": 5, "phases.policy.seconds": 0.05,
        "communication.rate_limit_messages": 5, "communication.rate_limit_window_seconds": 60}


async def in_comm(cfg, **kw):
    transport, store = FakeTransport(), MemoryEventStore()
    rt = make_human(cfg, transport, store, **kw)
    rt.start()
    await wait_for_phase(rt, "communication", 1)
    return rt, transport, store


async def finish_comm(rt):
    for pid in rt.members():
        await rt.mark_ready(pid, "communication")


async def test_public_and_direct_message_visibility(make_cfg):
    rt, transport, _store = await in_comm(make_cfg(COMM))
    await rt.send_message("p_a", {"channel": "public", "text": "hello all"})
    await rt.send_message("p_a", {"channel": "direct", "to": "p1", "text": "secret-for-B"})
    await rt.send_message("p_c", {"channel": "direct", "to": "coordinator", "text": "secret-for-C"})
    await rt.send_message(COORD, {"channel": "direct", "to": "p3", "text": "secret-for-D"})
    seen = {pid: json.dumps(rt.snapshot_for_participant(pid)) for pid in rt.members()}
    assert all("hello all" in t for t in seen.values())
    assert "secret-for-B" in seen["p_a"] and "secret-for-B" in seen["p_b"]
    assert not any("secret-for-B" in seen[p] for p in ("p_c", "p_d", COORD))
    assert "secret-for-C" in seen[COORD] and "secret-for-C" in seen["p_c"]
    assert not any("secret-for-C" in seen[p] for p in ("p_a", "p_b", "p_d"))
    assert "secret-for-D" in seen["p_d"] and not any("secret-for-D" in seen[p] for p in ("p_a", "p_b", "p_c"))
    inbox = rt.coordinator_snapshot()["observation"]["inbox"]
    assert [m["text"] for m in inbox if m["type"] == "message"] == ["secret-for-C"]
    # Nothing ever sent over the wire leaks a DM to someone else.
    for pid, _e, payload in transport.sent:
        text = json.dumps(payload)
        if pid not in ("p_a", "p_b"):
            assert "secret-for-B" not in text
    rt.task.cancel()


async def test_message_validation_and_limits(make_cfg):
    rt, _t, store = await in_comm(make_cfg({**COMM, "communication.message_max_chars": 20,
                                            "communication.max_messages_per_round": 4}))
    for bad in ({"channel": "public", "text": ""}, {"channel": "public", "text": "   \x07 "},
                {"channel": "public", "text": "x" * 21}, {"channel": "shout", "text": "hi"},
                {"channel": "direct", "to": "p0", "text": "me"}, {"channel": "direct", "to": "p9", "text": "hi"},
                {"channel": "public", "text": 5}, "not a dict"):
        with pytest.raises(ActionError):
            await rt.send_message("p_a", bad)
    await rt.send_message("p_a", {"channel": "public", "text": "  <b>hi</b>\x00\n\n\n\nyo "})
    assert rt.comms.messages[-1]["text"] == "<b>hi</b>\n\nyo"           # stored as plain text
    for _ in range(3):
        await rt.send_message("p_a", {"channel": "public", "text": "ok"})
    with pytest.raises(ActionError, match="limit for this round"):
        await rt.send_message("p_a", {"channel": "public", "text": "again"})
    assert len(store.of_kind("message")) == 4
    rt.task.cancel()


async def test_rate_limit(make_cfg):
    rt, _t, _s = await in_comm(make_cfg({**COMM, "communication.rate_limit_messages": 2}))
    await rt.send_message("p_b", {"channel": "public", "text": "1"})
    await rt.send_message("p_b", {"channel": "public", "text": "2"})
    with pytest.raises(ActionError, match="too quickly"):
        await rt.send_message("p_b", {"channel": "public", "text": "3"})
    await rt.send_message("p_c", {"channel": "public", "text": "other people are not limited"})
    rt.task.cancel()


async def test_only_in_communication_step(make_cfg):
    cfg = make_cfg({**COMM, "phases.event.seconds": 2})
    rt = make_human(cfg)
    rt.start()
    await wait_for_phase(rt, "event", 1)
    with pytest.raises(ActionError, match="communication step"):
        await rt.send_message("p_a", {"channel": "public", "text": "early"})
    with pytest.raises(ActionError, match="communication step"):
        await rt.offer_bribe("p_a", {"amount": 5})
    rt.task.cancel()


async def test_no_coordinator_condition_has_no_bribes(make_cfg):
    rt = make_runtime(make_cfg(COMM))
    rt.start()
    await wait_for_phase(rt, "communication", 1)
    with pytest.raises(ActionError, match="no coordinator"):
        await rt.offer_bribe("p_a", {"amount": 5})
    with pytest.raises(ActionError, match="recipient"):
        await rt.send_message("p_a", {"channel": "direct", "to": "coordinator", "text": "hi"})
    await rt.send_message("p_a", {"channel": "direct", "to": "p2", "text": "fine"})
    rt.task.cancel()


async def test_escrow_blocks_spending_and_expiry_refunds(make_cfg):
    cfg = make_cfg({**COMM, "phases.decision.seconds": 2, "bribery.max_offers_per_round": 5})
    rt, _t, store = await in_comm(cfg)
    w = rt.state.wealth[0]
    for bad in ({"amount": 0.5}, {"amount": w + 1}, {"amount": "10"}, {"amount": float("nan")}, {"amount": True},
                {"amount": 5, "note": "x" * (cfg.bribe_note_max_chars + 1)}):
        with pytest.raises(ActionError):
            await rt.offer_bribe("p_a", bad)
    await rt.offer_bribe("p_a", {"amount": w - 10, "note": "please"})
    assert rt.snapshot_for(0)["escrow"] == pytest.approx(w - 10)
    with pytest.raises(ActionError, match="available"):
        await rt.offer_bribe("p_a", {"amount": 11})
    with pytest.raises(ActionError, match="only islanders"):
        await rt.offer_bribe(COORD, {"amount": 5})
    with pytest.raises(ActionError, match="only the coordinator"):
        await rt.respond_bribe("p_b", {"offer_id": "b1", "accept": True})
    # Other islanders never see the offer.
    for pid in ("p_b", "p_c", "p_d"):
        assert "please" not in json.dumps(rt.snapshot_for_participant(pid))
    assert any(i["type"] == "bribe" and i["note"] == "please" for i in rt.coordinator_snapshot()["observation"]["inbox"])
    await finish_comm(rt)
    await wait_for_phase(rt, "decision", 1)
    assert rt.comms.offers["b1"]["status"] == "expired" and rt.snapshot_for(0)["escrow"] == 0
    assert store.of_kind("bribe_expired")[0]["payload"]["offer_id"] == "b1"
    rt.task.cancel()


async def test_escrow_limits_transfers(make_cfg):
    cfg = make_cfg({**COMM, "phases.decision.seconds": 2})
    rt, _t, _s = await in_comm(cfg)
    w = rt.state.wealth[0]
    await rt.offer_bribe("p_a", {"amount": 20})
    await rt.respond_bribe(COORD, {"offer_id": "b1", "accept": True})
    await finish_comm(rt)
    await wait_for_phase(rt, "decision", 1)
    with pytest.raises(ActionError, match="exceeds available"):
        await rt.submit_decision("p_a", {"round": 1, "harvest": 4, "contribute": 3, "save": 3,
                                         "transfer_to": 1, "transfer_amount": w - 19})
    await rt.submit_decision("p_a", {"round": 1, "harvest": 4, "contribute": 3, "save": 3,
                                     "transfer_to": 1, "transfer_amount": w - 20})
    rt.task.cancel()


async def test_accepted_bribe_is_paid_with_favor(make_cfg):
    cfg = make_cfg({**COMM, "bribery.detection_prob": 0.0, "phases.resolution.seconds": 2})
    rt, transport, store = await in_comm(cfg)
    w0 = rt.state.wealth[0]
    await rt.offer_bribe("p_a", {"amount": 20, "note": "let me fish more"})
    with pytest.raises(ActionError, match="favor"):
        await rt.respond_bribe(COORD, {"offer_id": "b1", "accept": True, "favor": "free_fish"})
    await rt.respond_bribe(COORD, {"offer_id": "b1", "accept": True, "favor": "quota_exempt", "reply": "deal"})
    with pytest.raises(ActionError, match="already"):
        await rt.respond_bribe(COORD, {"offer_id": "b1", "accept": False})
    assert rt.policy.favors_for(0).quota_exempt
    assert rt.snapshot_for(0)["my_offers"][0]["reply"] == "deal"
    assert rt.snapshot_for(0)["observation"]["own_favors"]["quota_exempt"]
    for seat in (1, 2, 3):
        snap = json.dumps(rt.snapshot_for(seat))
        assert "deal" not in snap and '"quota_exempt": true' not in snap
    await finish_comm(rt)
    await wait_for_phase(rt, "resolution", 1)
    led = rt.ledgers[0]
    assert led.bribes[0].executed and led.players[0].bribes_paid == pytest.approx(20)
    assert rt.state.coordinator.bribe_income == pytest.approx(cfg.bribe_income_rate * 20)
    assert rt.state.wealth[0] < w0 + led.players[0].harvest_income   # paid out of wealth
    settled = store.of_kind("bribe_settled")[0]["payload"]
    assert settled["executed"] and not settled["detected"] and settled["favor"] == "quota_exempt"
    assert store.of_kind("favor_granted")[0]["payload"]["seat"] == 0
    rt.task.cancel()


async def test_bribe_cap_enforced(make_cfg):
    cfg = make_cfg({**COMM, "coordinator_pay.bribe_income_cap": 10, "coordinator_pay.bribe_income_rate": 0.5})
    rt, _t, _s = await in_comm(cfg)
    await rt.offer_bribe("p_a", {"amount": 15})
    await rt.offer_bribe("p_b", {"amount": 6})
    await rt.offer_bribe("p_c", {"amount": 5})
    await rt.respond_bribe(COORD, {"offer_id": "b1", "accept": True})        # income 7.5 of 10
    with pytest.raises(ActionError, match="limit"):
        await rt.respond_bribe(COORD, {"offer_id": "b2", "accept": True})    # would be 10.5
    await rt.respond_bribe(COORD, {"offer_id": "b3", "accept": True})        # exactly 10
    await rt.respond_bribe(COORD, {"offer_id": "b2", "accept": False})       # refusing is always possible
    assert rt.coordinator_snapshot()["bribe_income_committed"] == pytest.approx(10)
    rt.task.cancel()


async def test_detected_bribe_fines_both_sides(make_cfg):
    cfg = make_cfg({**COMM, "bribery.detection_prob": 1.0, "phases.resolution.seconds": 2})
    rt, _t, store = await in_comm(cfg)
    await rt.offer_bribe("p_b", {"amount": 10})
    await rt.respond_bribe(COORD, {"offer_id": "b1", "accept": True})
    await finish_comm(rt)
    await wait_for_phase(rt, "resolution", 1)
    rec = rt.ledgers[0].bribes[0]
    assert rec.detected and rt.state.coordinator.fines == pytest.approx(cfg.bribe_fine)
    assert rt.ledgers[0].players[1].bribe_fine_assessed == pytest.approx(cfg.bribe_fine)
    assert store.of_kind("bribe_settled")[0]["payload"]["detected"]
    assert rt.snapshot_for(1)["my_offers"][0]["settled"]["detected"]
    rt.task.cancel()


async def test_favors_set_and_cleared_in_policy_form(make_cfg):
    cfg = make_cfg({**FAST, "phases.policy.seconds": 3})
    rt = make_human(cfg)
    rt.start()
    await wait_for_phase(rt, "policy", 1)
    with pytest.raises(ActionError):
        await rt.submit_policy(COORD, {"round": 1, "favors": {"7": {"audit_immune": True}}})
    with pytest.raises(ActionError):
        await rt.submit_policy(COORD, {"round": 1, "favors": {"1": {"fly": True}}})
    await rt.submit_policy(COORD, {"round": 1, "favors": {"1": {"audit_immune": True}}})
    await wait_for_phase(rt, "communication", 1)
    assert rt.policy.favors_for(1).audit_immune and not rt.policy.favors_for(0).any()
    await wait_for_phase(rt, "policy", 2)
    await rt.submit_policy(COORD, {"round": 2, "favors": {}})
    await wait_for_phase(rt, "communication", 2)
    assert not rt.policy.favors_for(1).any()
    rt.task.cancel()


async def test_scripted_coordinator_answers_offers(make_cfg):
    cfg = make_cfg({**COMM, "bribery.detection_prob": 0.0, "phases.communication.seconds": 0.2})
    store = MemoryEventStore()
    rt = make_human(cfg, store=store,
                    coordinator_backend=ScriptedCoordinator(cfg.default_policy, accept_bribes=True))
    rt.start()
    await wait_for_phase(rt, "communication", 1)
    await rt.offer_bribe("p_d", {"amount": 3})
    await wait_for_phase(rt, "decision", 1)
    assert rt.comms.offers["b1"]["status"] == "accepted"
    assert not store.of_kind("action_rejected")
    rt.task.cancel()
