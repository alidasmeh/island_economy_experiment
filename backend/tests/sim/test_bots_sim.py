import csv
import json
import random

import pytest

from app.bots import make_bot, parse_strategy_mix, round_to_effort
from app.coordinator import ScriptedCoordinator
from app.engine import Decision, Favors, Policy, draw_group_setup, initial_state, resolve_round, round_rng
from app.engine.observation import coordinator_observation, player_observation
from app.sim.cli import main, parse_seeds
from app.sim.dilemma import run_dilemma_check
from app.sim.runner import simulate_group

# ---------- bots ----------


def _obs(cfg, seat=0, last=None, policy=None):
    st = initial_state(draw_group_setup(1, cfg), cfg)
    return player_observation(seat, st, policy or Policy(), cfg, event=cfg.events[0], last_ledger=last)


def test_fixed_bots_use_config(cfg):
    assert make_bot("selfish", cfg).decide(_obs(cfg), random.Random(0)) == Decision(**cfg.bot_allocations["selfish"])
    assert make_bot("cooperative", cfg).decide(_obs(cfg), random.Random(0)) == Decision(**cfg.bot_allocations["cooperative"])


def test_conditional_bot_mirrors_group_average(cfg):
    st = initial_state(draw_group_setup(1, cfg), cfg)
    ds = [Decision(10, 0, 0), Decision(10, 0, 0), Decision(0, 10, 0), Decision(0, 0, 10)]
    _, led = resolve_round(st, ds, Policy(), cfg.events[0], round_rng(1, 1), cfg=cfg)
    bot = make_bot("conditional", cfg)
    assert bot.decide(_obs(cfg), random.Random(0)) == Decision(**cfg.bot_allocations["conditional_first_round"])
    assert bot.decide(_obs(cfg, last=led), random.Random(0)) == Decision(5, 3, 2)  # 5/2.5/2.5 rounded


def test_random_bot_valid_and_covers_extremes(cfg):
    bot, r = make_bot("random", cfg), random.Random(3)
    seen = set()
    for _ in range(3000):
        d = bot.decide(_obs(cfg), r)
        assert min(d.harvest, d.contribute, d.save) >= 0 and d.harvest + d.contribute + d.save == cfg.effort_points
        seen.add((d.harvest, d.contribute, d.save))
    assert len(seen) == (cfg.effort_points + 2) * (cfg.effort_points + 1) // 2  # every composition appears


@pytest.mark.parametrize("shares,total,expected", [
    ((5, 2.5, 2.5), 10, (5, 3, 2)), ((1, 1, 1), 10, (4, 3, 3)), ((0, 0, 0), 10, (4, 3, 3)), ((3, 0, 0), 10, (10, 0, 0)),
])
def test_round_to_effort(shares, total, expected):
    assert round_to_effort(shares, total) == expected


def test_parse_strategy_mix():
    assert parse_strategy_mix("selfish", 4) == ["selfish"] * 4
    assert parse_strategy_mix("selfish:2,cooperative:2", 4) == ["selfish", "selfish", "cooperative", "cooperative"]
    assert parse_strategy_mix("random,conditional,selfish,cooperative", 4)[1] == "conditional"
    for bad in ("greedy", "selfish:3", "selfish,random"):
        with pytest.raises(ValueError):
            parse_strategy_mix(bad, 4)


def test_parse_seeds():
    assert parse_seeds("1..3,7") == [1, 2, 3, 7]
    assert len(parse_seeds("1..1000")) == 1000


# ---------- observations (information access) ----------


def _played_ledger(cfg):
    st = initial_state(draw_group_setup(2, cfg), cfg)
    ds = [Decision(10, 0, 0, transfer_to=1, transfer_amount=5), Decision(0, 10, 0), Decision(4, 3, 3), Decision(0, 0, 10)]
    return resolve_round(st, ds, Policy(), cfg.events[0], round_rng(2, 1), cfg=cfg)


def test_player_observation_hides_private_information(cfg):
    st, led = _played_ledger(cfg)
    pol = Policy(info_policy="totals_only", favors={2: Favors(quota_exempt=True), 0: Favors(audit_immune=True)})
    obs = player_observation(1, st, pol, cfg, last_ledger=led).to_dict()
    assert obs["last_round_individual"] is None
    assert "favors" not in obs["policy"]
    assert obs["own_favors"] == {"quota_exempt": False, "audit_immune": False, "double_redistribution_weight": False}
    flat = json.dumps(obs)
    # Other players' wealth/capital never appear; own values do.
    for j in (0, 2, 3):
        assert repr(st.wealth[j]) not in flat
    assert obs["wealth"] == st.wealth[1]


def test_player_observation_show_individual(cfg):
    st, led = _played_ledger(cfg)
    obs = player_observation(3, st, Policy(info_policy="show_individual"), cfg, last_ledger=led)
    rows = obs.last_round_individual
    assert [r["harvest_effort"] for r in rows] == [10, 0, 4, 0]
    assert set(rows[0]) == {"seat", "harvest_effort", "contribute_effort", "save_effort", "harvest"}
    assert player_observation(2, st, Policy(favors={2: Favors(quota_exempt=True)}), cfg).own_favors["quota_exempt"]


def test_coordinator_observation_sees_everyone_but_not_T(cfg):
    st, led = _played_ledger(cfg)
    pol = Policy(info_policy="totals_only", favors={1: Favors(audit_immune=True)})
    obs = coordinator_observation(st, pol, cfg, ledgers=[led]).to_dict()
    assert len(obs["last_round_players"]) == 4 and obs["last_round_players"][0]["harvest_effort"] == 10
    assert obs["current_policy"]["favors"]["1"]["audit_immune"]
    assert "n_rounds" not in json.dumps(obs) and len(obs["history"]) == 1


# ---------- coordinator stub ----------


def test_scripted_coordinator_script_and_bribes(cfg):
    coord = ScriptedCoordinator({**cfg.default_policy, "tax_rate": 0.1}, script={3: {"tax_rate": 0.3, "quota": 4}})
    st = initial_state(draw_group_setup(1, cfg), cfg)
    obs = coordinator_observation(st, Policy(), cfg, ledgers=[], inbox=[{"type": "bribe", "offer_id": "o1"}])
    a1 = coord.act(obs)
    assert a1.policy.tax_rate == 0.1 and a1.bribe_responses["o1"].accept is False
    st.round = 3
    a3 = coord.act(coordinator_observation(st, Policy(), cfg, ledgers=[]))
    st.round = 4
    a4 = coord.act(coordinator_observation(st, Policy(), cfg, ledgers=[]))
    assert (a3.policy.tax_rate, a3.policy.quota) == (0.3, 4) and a4.policy == a3.policy


def test_scripted_coordinator_from_yaml(cfg, tmp_path):
    p = tmp_path / "policy.yaml"
    p.write_text("base: {tax_rate: 0.2, redistribution: need}\nrounds: {2: {insurance: true}}\n")
    coord = ScriptedCoordinator.from_yaml(p, cfg)
    assert coord.base["tax_rate"] == 0.2 and coord.base["quota"] == cfg.default_policy["quota"]
    assert coord.script == {2: {"insurance": True}}


# ---------- runner ----------


def test_full_20_round_game_with_bots_and_stub(cfg):
    """Acceptance: 4 bots + scripted coordinator stub, full 20 rounds, no errors, coins conserved."""
    coord = ScriptedCoordinator(cfg.bot_stub_policy, script={5: {"redistribution": "infrastructure"},
                                                             10: {"redistribution": "need", "insurance": False}})
    res = simulate_group(11, cfg, ["cooperative", "selfish", "conditional", "random"], coordinator=coord,
                         condition="coordinator_stub", n_rounds=20)
    assert len(res.rounds) == 20 and len(res.players) == 80
    assert res.group["max_conservation_error"] < 1e-8
    assert res.rounds[0]["pot_collected"] > 0
    assert res.group["coordinator_payoff_coins"] > 0


def test_simulation_is_deterministic(cfg):
    a = simulate_group(5, cfg, ["random", "conditional", "random", "selfish"])
    b = simulate_group(5, cfg, ["random", "conditional", "random", "selfish"])
    assert a.rounds == b.rounds and a.players == b.players and a.group == b.group


def test_matched_design_same_draws_across_conditions(cfg):
    none = simulate_group(8, cfg, ["cooperative"] * 4)
    stub = simulate_group(8, cfg, ["cooperative"] * 4, coordinator=ScriptedCoordinator.from_config(cfg),
                          condition="coordinator_stub")
    assert [r["event"] for r in none.rounds] == [r["event"] for r in stub.rounds]
    assert none.group["n_rounds"] == stub.group["n_rounds"]
    assert none.group["initial_welfare"] == stub.group["initial_welfare"]


# ---------- CLI and dilemma ----------


def test_cli_simulate_writes_csvs(tmp_path, capsys):
    out = tmp_path / "out"
    rc = main(["simulate", "--condition", "coordinator_stub", "--strategy-mix", "selfish:2,cooperative:2",
               "--strategy-mix", "random", "--seeds", "1..3", "--out", str(out)])
    assert rc == 0
    with (out / "groups.csv").open() as f:
        groups = list(csv.DictReader(f))
    with (out / "rounds.csv").open() as f:
        rounds = list(csv.DictReader(f))
    assert len(groups) == 6 and {g["condition"] for g in groups} == {"coordinator_stub"}
    assert len(rounds) == sum(int(g["n_rounds"]) for g in groups)
    meta = json.loads((out / "meta.json").read_text())
    assert len(meta["params_sha256"]) == 64 and meta["n_groups"] == 6


def test_cli_plot(tmp_path):
    out = tmp_path / "out"
    main(["simulate", "--strategy-mix", "cooperative", "--strategy-mix", "selfish", "--seeds", "1..3", "--out", str(out),
          "--plot"])
    assert (out / "welfare_by_round.png").stat().st_size > 0 and (out / "stock_by_round.png").stat().st_size > 0


def test_dilemma_report_runs(cfg):
    r = run_dilemma_check(cfg, list(range(1, 6)), counterfactual_seeds=2)
    assert r.n_seeds == 5 and r.rounds_compared > 0
    assert "(a)" in r.text(cfg) and "(c)" in r.text(cfg)


def test_default_calibration_passes_a_and_c():
    """The shipped (calibrated) defaults pass checks (a) and (c); (b) holds in >= 99.5% of live rounds."""
    from app.engine import load_config

    cfg = load_config()
    r = run_dilemma_check(cfg, list(range(1, 201)), counterfactual_seeds=20)
    assert r.check_a and r.check_c
    assert r.selfish_beats_coop_share_live >= 0.995
