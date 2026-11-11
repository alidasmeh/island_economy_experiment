"""Section 7: live preview + logging of every lever change; section 2: coordinator dropout."""

import asyncio
import json

import pytest

from app.game.runtime import ActionError
from app.game.store import MemoryEventStore

from .test_coordinator_runtime import COORD, make_human
from .test_runtime import FAST, SEATS, FakeTransport, wait_for_phase


async def test_drafts_are_logged_and_previewed(make_cfg):
    cfg = make_cfg({**FAST, "phases.policy.seconds": 5})
    store = MemoryEventStore()
    rt = make_human(cfg, store=store)
    rt.start()
    await wait_for_phase(rt, "policy", 1)
    snap = rt.coordinator_snapshot()
    assert snap["preview"]["estimate"] and snap["preview"]["pot_collected"] == 0
    ack = await rt.draft_policy(COORD, {"round": 1, "tax_rate": 0.2})
    assert ack["preview"]["pot_collected"] > 0
    await rt.draft_policy(COORD, {"round": 1, "tax_rate": 0.3})
    await rt.draft_policy(COORD, {"round": 1, "tax_rate": 0.3, "quota": 4})
    drafts = [d["payload"] for d in store.of_kind("policy_draft")]
    assert [d["changed"] for d in drafts] == [["tax_rate"], ["tax_rate"], ["quota"]]
    assert all(d["ms_into_phase"] >= 0 for d in drafts) and [d["n"] for d in drafts] == [1, 2, 3]
    assert rt.policy.tax_rate == 0                       # drafts never take effect by themselves
    for bad in ({"round": 1, "tax_rate": 0.07}, {"round": 2, "tax_rate": 0.1}, "x"):
        with pytest.raises(ActionError):
            await rt.draft_policy(COORD, bad)
    with pytest.raises(ActionError, match="only the coordinator"):
        await rt.draft_policy("p_a", {"round": 1, "tax_rate": 0.1})
    await rt.submit_policy(COORD, {"round": 1, "tax_rate": 0.3, "quota": 4})
    with pytest.raises(ActionError):                     # no drafting after confirming
        await rt.draft_policy(COORD, {"round": 1, "tax_rate": 0.1})
    rt.task.cancel()


async def test_draft_limit(make_cfg):
    cfg = make_cfg({**FAST, "phases.policy.seconds": 5, "decision_support.max_drafts_per_phase": 2})
    rt = make_human(cfg)
    rt.start()
    await wait_for_phase(rt, "policy", 1)
    await rt.draft_policy(COORD, {"round": 1, "tax_rate": 0.1})
    await rt.draft_policy(COORD, {"round": 1, "tax_rate": 0.2})
    with pytest.raises(ActionError, match="too many"):
        await rt.draft_policy(COORD, {"round": 1, "tax_rate": 0.3})
    rt.task.cancel()


async def test_players_never_see_drafts_or_preview(make_cfg):
    cfg = make_cfg({**FAST, "phases.policy.seconds": 5})
    transport = FakeTransport()
    rt = make_human(cfg, transport)
    rt.start()
    await wait_for_phase(rt, "policy", 1)
    await rt.draft_policy(COORD, {"round": 1, "tax_rate": 0.45, "announcement": "draft-only-text"})
    for seat in range(4):
        text = json.dumps(rt.snapshot_for(seat))
        assert "draft-only-text" not in text and '"preview": {"estimate"' not in text
    for pid, _e, payload in transport.sent:
        if pid != COORD:
            assert "draft-only-text" not in json.dumps(payload)
    rt.task.cancel()


async def test_coordinator_dropout_freezes_rules_and_flags(make_cfg):
    flagged = []

    async def on_flag(_rt, flag):
        flagged.append(flag)

    cfg = make_cfg({**FAST, "group.rounds_min": 4, "group.rounds_max": 4, "phases.policy.seconds": 0.3,
                    "phases.event.seconds": 2, "phases.communication.seconds": 2, "phases.resolution.seconds": 2})
    store, transport = MemoryEventStore(), FakeTransport()
    rt = make_human(cfg, transport, store, on_flag=on_flag)
    rt.start()
    # Round 1: the coordinator sets a tax, then disappears.
    await wait_for_phase(rt, "event", 1)
    for pid in rt.members():
        await rt.mark_ready(pid, "event")
    await wait_for_phase(rt, "policy", 1)
    await rt.submit_policy(COORD, {"round": 1, "tax_rate": 0.2})
    for t in (1, 2, 3):
        await wait_for_phase(rt, "communication", t)
        if t == 3:
            with pytest.raises(ActionError, match="left"):
                await rt.offer_bribe("p_a", {"amount": 5})
        for pid in SEATS:                                 # islanders only: a dropped coordinator is not awaited
            await rt.mark_ready(pid, "communication")
        await wait_for_phase(rt, "resolution", t)
        for pid in SEATS:
            await rt.mark_ready(pid, "resolution")
        await wait_for_phase(rt, "event", t + 1)
        for pid in SEATS:
            await rt.mark_ready(pid, "event")
    await wait_for_phase(rt, "communication", 4)
    assert rt.coordinator_dropped and flagged == [{"type": "coordinator_dropout", "round": 3}]
    assert rt.policy.tax_rate == 0.2                      # rules stay fixed
    snap = rt.snapshot_for(0)
    assert snap["coordinator_left"] and "policy" not in snap["phases"] and snap["n_members"] == 4
    assert "policy" not in [e["payload"]["phase"] for e in store.of_kind("phase_started") if e["round"] == 4]
    rt.task.cancel()
