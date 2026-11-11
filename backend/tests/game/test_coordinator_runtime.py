"""Human-coordinator condition: policy phase, validation, timeouts, what the coordinator sees."""

import asyncio
import json

import pytest

from app.coordinator.interface import ScriptedCoordinator
from app.game.runtime import ActionError, GroupRuntime
from app.game.store import MemoryEventStore

from .test_runtime import FAST, SEATS, FakeTransport, wait_for_phase

COORD = "p_coord"


def make_human(cfg, transport=None, store=None, seed=7, **kw):
    if "coordinator_backend" not in kw:
        kw["coordinator"] = COORD
    return GroupRuntime(group_id="S-g002", session_id="S", condition="human", seed=seed, cfg=cfg, seats=SEATS,
                        store=store or MemoryEventStore(), transport=transport or FakeTransport(), **kw)


GOOD = {"quota": 6, "tax_rate": 0.2, "redistribution": "need", "match_rate": 0.5, "fine": 10, "audit_prob": 0.3,
        "insurance": True, "info_policy": "totals_only", "announcement": "Fish less, share more."}


async def test_all_timeouts_keep_default_policy_and_finish(make_cfg):
    store, transport = MemoryEventStore(), FakeTransport()
    rt = make_human(make_cfg(FAST), transport, store)
    await asyncio.wait_for(rt.start(), 5)
    assert rt.status == "finished"
    ended = [e["payload"]["phase"] for e in store.of_kind("phase_ended")]
    assert ended[:5] == ["event", "policy", "communication", "decision", "resolution"]
    pol = store.of_kind("policy")
    assert len(pol) == 3 and all(p["payload"]["timeout"] and p["participant_id"] == COORD for p in pol)
    assert rt.policy.to_dict() == make_human(make_cfg(FAST)).policy.to_dict()
    final = transport.last(COORD)["final"]
    assert final["welfare_bonus"] == pytest.approx(rt.cfg.welfare_bonus_rate * final["group_payoff_coins"])
    assert final["payoff_coins"] == pytest.approx(final["welfare_bonus"])


async def test_submitted_policy_takes_effect_and_is_announced(make_cfg):
    cfg = make_cfg({**FAST, "phases.policy.seconds": 5})
    store, transport = MemoryEventStore(), FakeTransport()
    rt = make_human(cfg, transport, store)
    rt.start()
    await wait_for_phase(rt, "policy", 1)
    await rt.submit_policy(COORD, {"round": 1, **GOOD, "lever_changes": 7})
    await wait_for_phase(rt, "communication", 1)   # phase ended early: the coordinator is done
    assert rt.policy.tax_rate == 0.2 and rt.policy.quota == 6 and rt.policy.insurance
    for seat in range(4):
        snap = rt.snapshot_for(seat)
        assert snap["policy"]["announcement"] == "Fish less, share more." and snap["policy"]["tax_rate"] == 0.2
        assert snap["observation"]["policy"]["info_policy"] == "totals_only"
    logged = store.of_kind("policy")[0]["payload"]
    assert not logged["timeout"] and logged["lever_changes"] == 7
    assert set(logged["changed"]) == set(GOOD)
    await wait_for_phase(rt, "resolution", 1)
    led = rt.ledgers[0]
    assert led.group.pot_collected > 0
    # totals_only: players no longer see individual rows; the coordinator always does.
    assert rt.snapshot_for(0)["observation"]["last_round_individual"] is None
    assert len(rt.coordinator_snapshot()["observation"]["last_round_players"]) == 4
    # Round 2: levers not sent keep their value.
    await wait_for_phase(rt, "policy", 2)
    await rt.submit_policy(COORD, {"round": 2, "tax_rate": 0.1})
    await wait_for_phase(rt, "communication", 2)
    assert rt.policy.tax_rate == 0.1 and rt.policy.quota == 6 and rt.policy.announcement == GOOD["announcement"]
    rt.task.cancel()


async def test_policy_authorization_and_validation(make_cfg):
    cfg = make_cfg({**FAST, "phases.event.seconds": 0.3, "phases.policy.seconds": 2, "phases.decision.seconds": 2})
    store = MemoryEventStore()
    rt = make_human(cfg, store=store)
    rt.start()
    await wait_for_phase(rt, "event", 1)
    with pytest.raises(ActionError, match="policy phase"):
        await rt.submit_policy(COORD, {"round": 1, **GOOD})
    await wait_for_phase(rt, "policy", 1)
    with pytest.raises(ActionError, match="only the coordinator"):
        await rt.submit_policy("p_a", {"round": 1, **GOOD})
    with pytest.raises(ActionError, match="not a member"):
        await rt.submit_policy("p_zzz", {"round": 1, **GOOD})
    bad = [
        {"tax_rate": 0.07}, {"tax_rate": 0.9}, {"quota": 31}, {"quota": 2.5}, {"fine": -1}, {"audit_prob": 0.6},
        {"match_rate": 1.5}, {"redistribution": "lottery"}, {"info_policy": "everything"}, {"insurance": "yes"},
        {"announcement": "x" * (cfg.announcement_max_chars + 1)}, {"tax_rate": True}, {"round": 2},
    ]
    for b in bad:
        with pytest.raises(ActionError):
            await rt.submit_policy(COORD, {"round": 1, **b})
    assert len(store.of_kind("action_rejected")) == len(bad) + 2   # wrong phase + not coordinator
    await rt.submit_policy(COORD, {"round": 1, "announcement": "  hi\x07  "})
    assert store.of_kind("policy_submitted")[0]["payload"]["policy"]["announcement"] == "hi"
    with pytest.raises(ActionError):   # already submitted (the phase may also have ended already)
        await rt.submit_policy(COORD, {"round": 1, "tax_rate": 0.1})
    await wait_for_phase(rt, "decision", 1)
    with pytest.raises(ActionError, match="only islanders"):
        await rt.submit_decision(COORD, {"round": 1, "harvest": 4, "contribute": 3, "save": 3})
    rt.task.cancel()


async def test_ready_phases_wait_for_the_coordinator(make_cfg):
    cfg = make_cfg({**FAST, "phases.event.seconds": 2})
    rt = make_human(cfg)
    rt.start()
    await wait_for_phase(rt, "event", 1)
    for pid in SEATS:
        await rt.mark_ready(pid, "event")
    await asyncio.sleep(0.05)
    assert rt.phase == "event" and rt.snapshot_for(0)["n_done"] == 4
    await rt.mark_ready(COORD, "event")
    await wait_for_phase(rt, "policy", 1)
    rt.task.cancel()


async def test_coordinator_and_players_see_only_what_they_may(make_cfg):
    transport = FakeTransport()
    rt = make_human(make_cfg(FAST), transport)
    await asyncio.wait_for(rt.start(), 5)
    c = rt.coordinator_snapshot()
    text = json.dumps(c)
    assert c["role"] == "coordinator" and c["seat"] is None
    assert "n_rounds" not in text and "seed" not in text
    assert not any(pid in text for pid in SEATS)            # pseudonymous ids are never shown
    assert len(c["observation"]["history"]) == len(rt.ledgers)
    for seat in range(4):
        snap = rt.snapshot_for(seat)
        assert snap["role"] == "player" and COORD not in json.dumps(snap)
        assert "favors" not in snap["policy"]
    # Every message the coordinator received is a coordinator snapshot.
    assert all(p["role"] == "coordinator" for pid, _e, p in transport.sent if pid == COORD)


async def test_favors_stay_private(make_cfg):
    from app.engine.types import Favors

    cfg = make_cfg({**FAST, "phases.policy.seconds": 2})
    rt = make_human(cfg)
    rt.start()
    await wait_for_phase(rt, "policy", 1)
    rt.policy.favors[2] = Favors(quota_exempt=True)          # set from the inbox from Milestone 5 on
    await rt.submit_policy(COORD, {"round": 1, "tax_rate": 0.1})
    await wait_for_phase(rt, "communication", 1)
    assert rt.policy.favors_for(2).quota_exempt               # kept by a policy submission
    assert rt.snapshot_for(2)["observation"]["own_favors"]["quota_exempt"]
    for seat in (0, 1, 3):
        assert '"quota_exempt": true' not in json.dumps(rt.snapshot_for(seat))
    rt.task.cancel()


async def test_scripted_coordinator_full_game(make_cfg):
    """A 20-round game with a scripted coordinator stub runs end to end (players time out)."""
    cfg = make_cfg({**FAST, "group.rounds_min": 20, "group.rounds_max": 20,
                    **{f"phases.{p}.seconds": 0.005 for p in ("event", "policy", "communication", "decision",
                                                               "resolution")},
                    "phases.grace_seconds": 0.0})
    store = MemoryEventStore()
    stub = ScriptedCoordinator({**cfg.default_policy, "tax_rate": 0.2}, script={5: {"quota": 5}})
    rt = make_human(cfg, store=store, coordinator_backend=stub)
    await asyncio.wait_for(rt.start(), 20)
    assert rt.status == "finished" and len(rt.ledgers) == 20
    pol = store.of_kind("policy")
    assert len(pol) == 20 and not any(p["payload"]["timeout"] for p in pol)
    assert pol[0]["payload"]["backend"] == "ScriptedCoordinator"
    assert rt.policy.quota == 5 and all(l.group.pot_collected > 0 for l in rt.ledgers if l.group.total_harvest > 0)
