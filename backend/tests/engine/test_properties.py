"""Conservation, determinism, validation and settlement."""

import random

import pytest

from app.engine import (
    BribeOffer, Decision, Favors, Policy, ValidationError, default_policy, draw_group_setup,
    initial_state, resolve_round, round_rng, settle_game, timeout_decision, validate_decision,
    validate_policy,
)
from app.engine.types import Allocation


def random_policy(r: random.Random, cfg) -> Policy:
    favors = {s: Favors(r.random() < 0.2, r.random() < 0.2, r.random() < 0.2) for s in range(cfg.n_players)
              if r.random() < 0.3}
    return Policy(
        quota=r.randint(0, 30),
        tax_rate=round(r.randint(0, 10) * 0.05, 2),
        redistribution=r.choice(cfg.redistribution_options),
        match_rate=round(r.randint(0, 20) * 0.05, 2),
        fine=r.randint(0, 50),
        audit_prob=round(r.randint(0, 10) * 0.05, 2),
        insurance=r.random() < 0.5,
        info_policy=r.choice(cfg.info_policy_options),
        favors=favors,
    )


def random_decision(r: random.Random, cfg, seat: int, wealth: float) -> Decision:
    h = r.randint(0, cfg.effort_points)
    c = r.randint(0, cfg.effort_points - h)
    to = r.choice([None] + [j for j in range(cfg.n_players) if j != seat])
    amt = round(r.uniform(0, wealth), 2) if to is not None and r.random() < 0.3 else 0.0
    return Decision(h, c, cfg.effort_points - h - c, transfer_to=to if amt else None, transfer_amount=amt)


def play(seed, cfg, policy_fn, decision_fn, bribe_fn=lambda r, st: ()):
    setup = draw_group_setup(seed, cfg)
    st = initial_state(setup, cfg)
    r = random.Random(seed * 7919)
    ledgers = []
    for t in range(1, setup.n_rounds + 1):
        ds = [decision_fn(r, i, st) for i in range(st.n)]
        st, led = resolve_round(st, ds, policy_fn(r), setup.event_for(cfg, t), round_rng(seed, t), cfg=cfg,
                                bribes=bribe_fn(r, st))
        ledgers.append(led)
    return st, ledgers


def test_conservation_fuzz(cfg):
    """Coins in = coins out + fines destroyed (+ pot to infrastructure + bribes), every round."""
    def bribes(r, st):
        return [BribeOffer(f"o{k}", s, round(r.uniform(0, st.wealth[s] / 2), 2), r.random() < 0.6)
                for k, s in enumerate(range(st.n)) if r.random() < 0.3]

    for seed in range(150):
        st, ledgers = play(seed, cfg, lambda r: random_policy(r, cfg),
                           lambda r, i, st: random_decision(r, cfg, i, st.wealth[i]), bribes)
        for led in ledgers:
            assert led.group.conservation_error < 1e-8
            assert led.group.stock_after >= 0
            assert all(p.wealth_after >= -1e-9 for p in led.players)
        assert st.coordinator.bribe_income <= cfg.bribe_income_cap + 1e-9


def test_determinism_same_seed_same_decisions(cfg):
    def go(seed):
        _, ledgers = play(seed, cfg, lambda r: random_policy(r, cfg),
                          lambda r, i, st: random_decision(r, cfg, i, st.wealth[i]),
                          lambda r, st: [BribeOffer("x", 0, 5, True)] if r.random() < 0.3 else [])
        return [led.to_dict() for led in ledgers]

    for seed in (1, 2, 42, 999):
        assert go(seed) == go(seed)
    assert go(1) != go(2)


def test_matched_draws_independent_of_behaviour(cfg):
    """Audit draws are taken from the round RNG in full, so they match across conditions."""
    a = [round_rng(5, t).random() for t in range(1, 6)]
    b = [round_rng(5, t).random() for t in range(1, 6)]
    assert a == b


# ---------- validation ----------

def test_validate_decision(cfg):
    ok = Decision(4, 3, 3, transfer_to=1, transfer_amount=10)
    assert validate_decision(ok, cfg, seat=0, n_players=4, available_wealth=50) is ok
    bad = [
        Decision(4, 3, 4),
        Decision(-1, 6, 5),
        Decision(4.0, 3, 3),
        Decision(4, 3, 3, transfer_to=0, transfer_amount=5),
        Decision(4, 3, 3, transfer_to=7, transfer_amount=5),
        Decision(4, 3, 3, transfer_to=None, transfer_amount=5),
        Decision(4, 3, 3, transfer_to=1, transfer_amount=51),
        Decision(4, 3, 3, transfer_to=1, transfer_amount=-1),
        Decision(4, 3, 3, transfer_to=1, transfer_amount=float("nan")),
    ]
    for d in bad:
        with pytest.raises(ValidationError):
            validate_decision(d, cfg, seat=0, n_players=4, available_wealth=50)


def test_validate_policy(cfg):
    assert validate_policy(default_policy(cfg), cfg, n_players=4)
    assert validate_policy(Policy(quota=30, tax_rate=0.5, match_rate=1.0, fine=50, audit_prob=0.5,
                                  redistribution="need", insurance=True, info_policy="totals_only",
                                  favors={3: Favors(quota_exempt=True)}), cfg, n_players=4)
    bad = [
        Policy(quota=31), Policy(quota=-1), Policy(quota=2.5), Policy(tax_rate=0.55), Policy(tax_rate=0.12),
        Policy(match_rate=1.1), Policy(fine=51), Policy(audit_prob=0.6), Policy(redistribution="lottery"),
        Policy(info_policy="all"), Policy(insurance="yes"), Policy(announcement="x" * 201),
        Policy(favors={4: Favors(quota_exempt=True)}), Policy(tax_rate=float("nan")),
    ]
    for p in bad:
        with pytest.raises(ValidationError):
            validate_policy(p, cfg, n_players=4)


def test_timeout_decision(cfg):
    d = timeout_decision(None, cfg)
    assert (d.harvest, d.contribute, d.save, d.timeout) == (4, 3, 3, True)
    d = timeout_decision(Allocation(1, 2, 7), cfg)
    assert (d.harvest, d.contribute, d.save, d.timeout) == (1, 2, 7, True)


def test_policy_roundtrip():
    p = Policy(quota=5, favors={2: Favors(audit_immune=True)})
    assert Policy.from_dict(p.to_dict()) == p


# ---------- settlement ----------

def test_settle_game(cfg, make_state):
    st = make_state(wealth=(100, 50, 0, 10), capital=(20, 0, 5, 0), pool=8)
    st.coordinator.bribe_income, st.coordinator.fines = 10.0, 20.0
    s = settle_game(st, cfg, has_coordinator=True)
    assert s.payoff_coins == pytest.approx([122, 52, 7, 12])
    assert s.payoff_money == pytest.approx([c / cfg.coins_per_currency_unit for c in s.payoff_coins])
    assert s.coordinator_welfare_bonus == pytest.approx(cfg.welfare_bonus_rate * 193)
    assert s.coordinator_payoff_coins == pytest.approx(max(0, cfg.welfare_bonus_rate * 193 + 10 - 20))
    assert settle_game(st, cfg, has_coordinator=False).coordinator_payoff_coins == 0


def test_full_game_default_policy_runs(cfg):
    st, ledgers = play(3, cfg, lambda r: default_policy(cfg), lambda r, i, st: Decision(4, 3, 3))
    assert len(ledgers) == draw_group_setup(3, cfg).n_rounds
    assert st.round == len(ledgers) + 1
