"""policy_preview: the coordinator's estimate follows the engine's own rules."""

import pytest

from app.engine import Decision, Policy, policy_preview, resolve_round
from app.engine.types import Allocation, Favors

from ..conftest import FixedRng


def calm(cfg):
    return next(e for e in cfg.events if e.name == "calm")


def test_round_one_uses_default_split_and_matches_resolve(cfg, make_state):
    state = make_state()
    policy = Policy(tax_rate=0.2, redistribution="equal")
    pv = policy_preview(state, policy, calm(cfg), cfg)
    a = cfg.timeout_default_allocation
    decisions = [Decision(a["harvest"], a["contribute"], a["save"])] * 4
    _new, led = resolve_round(state, decisions, policy, calm(cfg), FixedRng(default=0.999), cfg=cfg)
    assert pv["estimate"] and pv["based_on"] == "default_split"
    assert pv["pot_collected"] == pytest.approx(led.group.pot_collected)
    assert pv["stock_after"] == pytest.approx(led.group.stock_after)
    for p, q in zip(pv["players"], led.players):
        assert p["redistribution"] == pytest.approx(q.redistribution)
        assert p["coins_change"] == pytest.approx(q.harvest_income - q.tax + q.redistribution)


def test_uses_last_round_split_and_does_not_change_state(cfg, make_state):
    state = make_state()
    state.last_allocation = [Allocation(10, 0, 0), Allocation(0, 10, 0), Allocation(5, 5, 0), Allocation(0, 0, 10)]
    before = state.to_dict()
    pv = policy_preview(state, Policy(), calm(cfg), cfg)
    assert pv["based_on"] == "last_round" and state.to_dict() == before
    assert [p["harvest_effort"] for p in pv["players"]] == [10, 0, 5, 0]
    assert pv["players"][1]["harvest"] == 0


def test_expected_fines_and_favors(cfg, make_state):
    state = make_state()
    state.last_allocation = [Allocation(10, 0, 0)] * 4
    policy = Policy(quota=1, fine=10, audit_prob=0.5,
                    favors={1: Favors(quota_exempt=True), 2: Favors(audit_immune=True)})
    pv = policy_preview(state, policy, calm(cfg), cfg)
    p0, p1, p2, _p3 = pv["players"]
    assert p0["over_quota"] > 0 and p0["expected_fine"] == pytest.approx(0.5 * 10 * p0["over_quota"])
    assert p1["expected_fine"] == 0 and p2["expected_fine"] == 0
    assert pv["expected_fines"] == pytest.approx(p0["expected_fine"] + pv["players"][3]["expected_fine"])


def test_double_share_favor_shows_in_redistribution(cfg, make_state):
    state = make_state()
    state.last_allocation = [Allocation(4, 3, 3)] * 4
    policy = Policy(tax_rate=0.5, redistribution="equal", favors={0: Favors(double_redistribution_weight=True)})
    pv = policy_preview(state, policy, calm(cfg), cfg)
    r = [p["redistribution"] for p in pv["players"]]
    assert r[0] == pytest.approx(2 * r[1])
