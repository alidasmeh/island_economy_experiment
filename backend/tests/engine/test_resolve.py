"""Unit tests for every step of section 5, plus edge cases."""

import pytest

from app.engine import BribeOffer, Decision, Favors, Policy, resolve_round
from app.engine.types import Allocation

D = Decision
CALM = None  # filled per-test from cfg


def run(cfg, state, decisions, policy=None, event="calm", rng=None, bribes=()):
    from tests.conftest import FixedRng

    return resolve_round(state, decisions, policy or Policy(), cfg.event(event), rng or FixedRng(),
                         cfg=cfg, bribes=bribes)


def assert_conserved(led):
    assert led.group.conservation_error < 1e-9


# ---------- 1. harvest ----------

def test_harvest_formula(cfg, make_state):
    st = make_state(skill=[1.0, 0.8, 1.2, 1.0], infra=1.5)
    new, led = run(cfg, st, [D(10, 0, 0), D(5, 5, 0), D(0, 0, 10), D(2, 4, 4)])
    q, S, A = cfg.catchability, st.stock, 1.5
    expected = [q * 10 * S * 1.0 * A, q * 5 * S * 0.8 * A, 0.0, q * 2 * S * 1.0 * A]
    assert [p.harvest for p in led.players] == pytest.approx(expected)
    assert led.group.harvest_scale == 1.0
    assert_conserved(led)


def test_storm_reduces_harvest(cfg, make_state):
    _, calm = run(cfg, make_state(), [D(10, 0, 0)] * 4, event="calm")
    _, storm = run(cfg, make_state(), [D(10, 0, 0)] * 4, event="storm")
    assert storm.players[0].harvest == pytest.approx(calm.players[0].harvest * cfg.event("storm").harvest_mult)


def test_harvest_scaled_down_when_exceeding_stock(make_cfg, make_state):
    c = make_cfg({"resource.catchability": 0.05})  # 4 * 0.05*10*S = 2S > S
    st = make_state(skill=[1.0, 1.0, 1.0, 0.5])
    new, led = run(c, st, [D(10, 0, 0)] * 4)
    assert led.group.total_harvest_raw > st.stock
    assert led.group.total_harvest == pytest.approx(st.stock)
    raw = [p.harvest_raw for p in led.players]
    got = [p.harvest for p in led.players]
    assert [g / r for g, r in zip(got, raw)] == pytest.approx([led.group.harvest_scale] * 4)
    assert new.stock == pytest.approx(led.group.regrowth)  # S + regrowth - S
    assert_conserved(led)


# ---------- 2. quota and audit ----------

def test_quota_audit_and_fine(cfg, make_state, rng):
    pol = Policy(quota=3, fine=10, audit_prob=0.5)
    # draws: seat0 0.1 (audited), seat1 0.9 (not), seat2 0.1 but under quota, seat3 0.1 (audited)
    new, led = run(cfg, make_state(), [D(10, 0, 0), D(10, 0, 0), D(2, 4, 4), D(10, 0, 0)],
                   policy=pol, rng=rng([0.1, 0.9, 0.1, 0.1]))
    h = led.players[0].harvest  # 7.0
    p0, p1, p2, p3 = led.players
    assert p0.caught and p0.over_quota == pytest.approx(h - 3)
    assert p0.quota_fine_assessed == pytest.approx(10 * (h - 3))
    assert not p1.audited and p1.over_quota > 0 and p1.quota_fine_assessed == 0
    assert not p2.audited and p2.over_quota == 0
    assert p3.caught
    assert p0.fines_paid == pytest.approx(p0.fines_assessed)
    assert new.wealth[0] == pytest.approx(100 + h - 10 * (h - 3))
    assert_conserved(led)


def test_quota_zero_means_no_quota(cfg, make_state, rng):
    _, led = run(cfg, make_state(), [D(10, 0, 0)] * 4, policy=Policy(quota=0, fine=50, audit_prob=0.5),
                 rng=rng([0.0] * 4))
    assert all(p.over_quota == 0 and not p.audited for p in led.players)


def test_quota_exempt_and_audit_immune_favors(cfg, make_state, rng):
    pol = Policy(quota=3, fine=10, audit_prob=0.5,
                 favors={0: Favors(quota_exempt=True), 1: Favors(audit_immune=True)})
    _, led = run(cfg, make_state(), [D(10, 0, 0)] * 4, policy=pol, rng=rng([0.0] * 4))
    p0, p1, p2, _ = led.players
    assert p0.over_quota == 0 and not p0.audited
    assert p1.over_quota > 0 and not p1.audited and p1.fines_assessed == 0
    assert p2.caught


def test_fine_capped_at_balance(cfg, make_state, rng):
    pol = Policy(quota=1, fine=50, audit_prob=0.5)
    new, led = run(cfg, make_state(wealth=(5, 100, 100, 100)), [D(10, 0, 0)] * 4, policy=pol,
                   rng=rng([0.0] * 4))
    p0 = led.players[0]
    assert p0.fines_assessed > 5 + p0.harvest_income
    assert p0.fines_paid == pytest.approx(5 + p0.harvest_income)
    assert new.wealth[0] == pytest.approx(0.0)
    assert led.group.fines_unpaid > 0
    assert_conserved(led)


# ---------- 3–4. income and tax ----------

def test_price_drop_and_tax(cfg, make_state):
    pol = Policy(tax_rate=0.2)
    _, led = run(cfg, make_state(), [D(10, 0, 0)] * 4, policy=pol, event="price_drop")
    p = led.players[0]
    assert p.harvest_income == pytest.approx(p.harvest * cfg.price * cfg.event("price_drop").price_mult)
    assert p.tax == pytest.approx(0.2 * p.harvest_income)
    assert led.group.pot_collected == pytest.approx(sum(x.tax for x in led.players))


# ---------- 5. infrastructure and match ----------

def test_infrastructure_without_match(cfg, make_state):
    new, led = run(cfg, make_state(), [D(0, 10, 0), D(0, 5, 5), D(10, 0, 0), D(4, 3, 3)])
    C = 18
    assert new.infra == pytest.approx((1 - cfg.infra_depreciation) * 1.0 + cfg.infra_gain_per_point * C)


def test_match_paid_from_pot(cfg, make_state):
    pol = Policy(tax_rate=0.5, match_rate=0.5)
    decisions = [D(10, 0, 0)] * 2 + [D(0, 10, 0)] * 2  # pot = 0.5*7*2 = 7; match cost 0.5*20 = 10 > 7
    new, led = run(cfg, make_state(), decisions, policy=pol)
    g = led.group
    assert g.pot_collected == pytest.approx(7.0)
    assert g.match_scale == pytest.approx(0.7)
    assert g.match_cost == pytest.approx(7.0)
    assert g.pot_after_match == pytest.approx(0.0)
    assert new.infra == pytest.approx(0.98 + cfg.infra_gain_per_point * (20 + 10 * 0.7))
    assert all(p.redistribution == 0 for p in led.players)
    assert_conserved(led)


def test_match_fully_funded(cfg, make_state):
    pol = Policy(tax_rate=0.5, match_rate=0.1)
    decisions = [D(10, 0, 0)] * 3 + [D(0, 10, 0)]  # pot 10.5, match cost 1
    new, led = run(cfg, make_state(), decisions, policy=pol)
    assert led.group.match_scale == 1.0
    assert led.group.pot_after_match == pytest.approx(10.5 - 1.0)
    assert new.infra == pytest.approx(0.98 + 0.02 * 11)
    assert_conserved(led)


# ---------- 6. redistribution ----------

def _pot_decisions():
    return [D(10, 0, 0), D(6, 4, 0), D(2, 8, 0), D(0, 0, 10)]


def test_redistribution_equal(cfg, make_state):
    _, led = run(cfg, make_state(), _pot_decisions(), policy=Policy(tax_rate=0.5))
    pot = led.group.pot_collected
    assert [p.redistribution for p in led.players] == pytest.approx([pot / 4] * 4)
    assert_conserved(led)


def test_redistribution_need(cfg, make_state):
    st = make_state(wealth=(200, 150, 100, 50), capital=(0, 0, 0, 50))  # totals 200,150,100,100
    _, led = run(cfg, st, _pot_decisions(), policy=Policy(tax_rate=0.5, redistribution="need"))
    pot = led.group.pot_collected
    w = [0, 50, 100, 100]
    assert [p.redistribution for p in led.players] == pytest.approx([pot * x / 250 for x in w])
    assert_conserved(led)


def test_redistribution_contribution(cfg, make_state):
    _, led = run(cfg, make_state(), _pot_decisions(), policy=Policy(tax_rate=0.5, redistribution="contribution"))
    pot = led.group.pot_collected
    assert [p.redistribution for p in led.players] == pytest.approx([0, pot * 4 / 12, pot * 8 / 12, 0])


def test_redistribution_contribution_falls_back_to_equal(cfg, make_state):
    _, led = run(cfg, make_state(), [D(10, 0, 0)] * 4, policy=Policy(tax_rate=0.5, redistribution="contribution"))
    assert led.group.redistribution_fallback_equal
    pot = led.group.pot_collected
    assert [p.redistribution for p in led.players] == pytest.approx([pot / 4] * 4)


def test_redistribution_need_all_equal_falls_back(cfg, make_state):
    _, led = run(cfg, make_state(), _pot_decisions(), policy=Policy(tax_rate=0.5, redistribution="need"))
    assert led.group.redistribution_fallback_equal


def test_redistribution_infrastructure(cfg, make_state):
    new, led = run(cfg, make_state(), _pot_decisions(), policy=Policy(tax_rate=0.5, redistribution="infrastructure"))
    pot = led.group.pot_collected
    assert all(p.redistribution == 0 for p in led.players)
    assert led.group.pot_to_infrastructure == pytest.approx(pot)
    assert new.infra == pytest.approx(0.98 + 0.02 * 12 + cfg.infra_gain_per_pot_coin * pot)
    assert_conserved(led)


def test_double_redistribution_weight_favor(cfg, make_state):
    pol = Policy(tax_rate=0.5, favors={3: Favors(double_redistribution_weight=True)})
    _, led = run(cfg, make_state(), _pot_decisions(), policy=pol)
    pot = led.group.pot_collected
    assert [p.redistribution for p in led.players] == pytest.approx([pot / 5] * 3 + [2 * pot / 5])


def test_empty_pot(cfg, make_state):
    _, led = run(cfg, make_state(), [D(0, 5, 5)] * 4, policy=Policy(tax_rate=0.5, match_rate=1.0, redistribution="need"))
    g = led.group
    assert g.pot_collected == 0 and g.match_cost == 0 and g.match_scale == 0
    assert all(p.redistribution == 0 for p in led.players)
    assert_conserved(led)


# ---------- 7. insurance ----------

def test_insurance_premium_accumulates(cfg, make_state):
    new, led = run(cfg, make_state(), [D(4, 3, 3)] * 4, policy=Policy(insurance=True), event="calm")
    assert all(p.premium == cfg.insurance_premium for p in led.players)
    assert new.insurance_pool == pytest.approx(4 * cfg.insurance_premium)
    assert_conserved(led)


def test_insurance_pays_out_on_storm(cfg, make_state):
    st = make_state(pool=12.0)
    new, led = run(cfg, st, [D(4, 3, 3)] * 4, policy=Policy(insurance=True), event="storm")
    pool = 12.0 + 4 * cfg.insurance_premium
    assert all(p.insurance_payout == pytest.approx(pool / 4) for p in led.players)
    assert new.insurance_pool == 0
    assert_conserved(led)


def test_insurance_off_takes_no_premium(cfg, make_state):
    new, led = run(cfg, make_state(), [D(4, 3, 3)] * 4, policy=Policy(insurance=False))
    assert all(p.premium == 0 for p in led.players) and new.insurance_pool == 0


# ---------- 8. saving ----------

def test_saving_and_interest(cfg, make_state):
    new, led = run(cfg, make_state(capital=(100, 0, 50, 0)), [D(0, 0, 10), D(0, 0, 10), D(10, 0, 0), D(4, 3, 3)])
    i, rho = cfg.interest_rate, cfg.saving_return_per_point
    assert new.capital == pytest.approx([100 * (1 + i) + 10 * rho, 10 * rho, 50 * (1 + i), 3 * rho])
    assert led.players[0].interest == pytest.approx(100 * i)
    assert_conserved(led)


# ---------- 9. transfers ----------

def test_transfers(cfg, make_state):
    ds = [D(0, 0, 10, transfer_to=1, transfer_amount=30), D(0, 0, 10, transfer_to=0, transfer_amount=10),
          D(0, 0, 10), D(0, 0, 10)]
    new, led = run(cfg, make_state(), ds)
    assert new.wealth == pytest.approx([80, 120, 100, 100])
    assert led.players[0].transfer_out == 30 and led.players[0].transfer_in == 10
    assert_conserved(led)


def test_transfer_clamped_to_balance(cfg, make_state):
    ds = [D(0, 0, 10, transfer_to=1, transfer_amount=500)] + [D(0, 0, 10)] * 3
    new, led = run(cfg, make_state(), ds)
    assert led.players[0].transfer_out == pytest.approx(100)
    assert new.wealth[0] == pytest.approx(0) and new.wealth[1] == pytest.approx(200)


def test_self_transfer_ignored(cfg, make_state):
    ds = [D(0, 0, 10, transfer_to=0, transfer_amount=50)] + [D(0, 0, 10)] * 3
    new, _ = run(cfg, make_state(), ds)
    assert new.wealth[0] == 100


# ---------- 10. bribes ----------

def test_bribe_accepted_refused_detected(cfg, make_state, rng):
    bribes = [BribeOffer("a", 0, 10, True), BribeOffer("b", 1, 10, False), BribeOffer("c", 2, 8, True)]
    # draws: 4 audits, then detection draws per bribe: a detected (0.0), b n/a, c not (0.99)
    new, led = run(cfg, make_state(), [D(0, 0, 10)] * 4, bribes=bribes, rng=rng([0.5] * 4 + [0.0, 0.0, 0.99]))
    a, b, c = led.bribes
    assert a.executed and a.detected and a.paid == 10
    assert not b.executed and b.rejected_reason == "refused"
    assert c.executed and not c.detected
    rate = cfg.bribe_income_rate
    assert new.coordinator.bribe_gross == pytest.approx(18)
    assert new.coordinator.bribe_income == pytest.approx(rate * 18)
    assert new.coordinator.fines == pytest.approx(cfg.bribe_fine)
    assert new.wealth[0] == pytest.approx(100 - 10 - cfg.bribe_fine)
    assert new.wealth[1] == pytest.approx(100)
    assert new.wealth[2] == pytest.approx(92)
    assert_conserved(led)


def test_bribe_cap_reached(make_cfg, make_state):
    c = make_cfg({"coordinator_pay.bribe_income_cap": 10, "coordinator_pay.bribe_income_rate": 0.5})
    st = make_state()
    st.coordinator.bribe_income = 6.0  # 4 coins of income left under the cap
    bribes = [BribeOffer("x", 0, 8, True), BribeOffer("y", 1, 2, True)]  # x would add 4 (ok), y adds 1 (exceeds)
    new, led = run(c, st, [D(0, 0, 10)] * 4, bribes=bribes)
    x, y = led.bribes
    assert x.executed and new.coordinator.bribe_income == pytest.approx(10)
    assert not y.executed and y.rejected_reason == "cap_reached"
    assert new.wealth[1] == 100
    assert_conserved(led)


# ---------- 11. stock ----------

def test_stock_update_logistic(cfg, make_state):
    st = make_state(stock=50.0)
    new, led = run(cfg, st, [D(4, 3, 3)] * 4, event="good_season")
    regrowth = cfg.regrowth_rate * 50 * (1 - 50 / cfg.carrying_capacity) * cfg.event("good_season").regrowth_mult
    assert led.group.regrowth == pytest.approx(regrowth)
    assert new.stock == pytest.approx(50 + regrowth - led.group.total_harvest)


def test_no_regrowth_below_collapse_threshold(cfg, make_state):
    new, led = run(cfg, make_state(stock=cfg.stock_min - 0.5), [D(4, 3, 3)] * 4)
    assert led.group.collapsed and led.group.regrowth == 0
    assert new.stock == pytest.approx(cfg.stock_min - 0.5 - led.group.total_harvest)


def test_stock_at_zero(cfg, make_state):
    new, led = run(cfg, make_state(stock=0.0), [D(10, 0, 0)] * 4, policy=Policy(tax_rate=0.5, quota=1, audit_prob=0.5, fine=50))
    assert led.group.total_harvest == 0 and new.stock == 0 and led.group.regrowth == 0
    assert all(p.harvest_income == 0 and p.fines_assessed == 0 for p in led.players)
    assert_conserved(led)


# ---------- 12. wealth identity ----------

def test_wealth_identity_and_round_advance(cfg, make_state, rng):
    pol = Policy(quota=4, fine=5, audit_prob=0.5, tax_rate=0.3, match_rate=0.2, insurance=True,
                 redistribution="need")
    ds = [D(10, 0, 0, transfer_to=2, transfer_amount=5), D(3, 4, 3), D(0, 10, 0), D(5, 0, 5, transfer_to=0, transfer_amount=1)]
    bribes = [BribeOffer("b1", 3, 4, True)]
    st = make_state(wealth=(120, 60, 80, 150), capital=(10, 0, 0, 30), pool=8)
    new, led = run(cfg, st, ds, policy=pol, event="storm", rng=rng([0.0, 0.0, 0.0, 0.0, 0.0]), bribes=bribes)
    for i, p in enumerate(led.players):
        expected = (p.wealth_before + p.harvest_income - p.tax - p.fines_paid + p.redistribution
                    + p.insurance_payout + p.transfer_in - p.transfer_out - p.bribes_paid - p.premium)
        assert new.wealth[i] == pytest.approx(expected)
    assert new.round == 2
    assert new.last_allocation == [Allocation(10, 0, 0), Allocation(3, 4, 3), Allocation(0, 10, 0), Allocation(5, 0, 5)]
    assert_conserved(led)


def test_all_players_timing_out(cfg, make_state):
    from app.engine import timeout_decision

    st = make_state()
    ds = [timeout_decision(a, cfg) for a in st.last_allocation]
    new, led = run(cfg, st, ds)
    a = cfg.timeout_default_allocation
    assert all(p.timeout and (p.harvest_effort, p.contribute_effort, p.save_effort) ==
               (a["harvest"], a["contribute"], a["save"]) for p in led.players)
    ds2 = [timeout_decision(x, cfg) for x in [Allocation(7, 1, 2)] * 4]
    _, led2 = run(cfg, new, ds2)
    assert all(p.harvest_effort == 7 and p.timeout for p in led2.players)


def test_input_state_not_mutated(cfg, make_state):
    st = make_state()
    snapshot = st.to_dict()
    run(cfg, st, [D(10, 0, 0, transfer_to=1, transfer_amount=5)] * 4, policy=Policy(tax_rate=0.5, insurance=True))
    assert st.to_dict() == snapshot


def test_rejects_invalid_effort(cfg, make_state):
    with pytest.raises(ValueError):
        run(cfg, make_state(), [D(5, 5, 5)] * 4)
    with pytest.raises(ValueError):
        run(cfg, make_state(), [D(10, 0, 0)] * 3)
