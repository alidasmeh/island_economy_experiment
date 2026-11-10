import copy

import pytest

from app.engine import ConfigError, default_policy, draw_group_setup, initial_state, load_config
from app.engine.config import config_from_dict


def test_default_config_loads_with_hash(cfg):
    assert cfg.n_players == 4
    assert cfg.effort_points == 10
    assert cfg.stock_initial == pytest.approx(70.0)
    assert cfg.stock_min == pytest.approx(10.0)
    assert len(cfg.sha256) == 64
    assert load_config(cfg.source_path).sha256 == cfg.sha256


def test_shipped_default_config_is_valid():
    default = load_config()
    assert default.source_path.endswith("config/default.yaml") and len(default.sha256) == 64


def test_event_probabilities_must_sum_to_one(cfg):
    raw = copy.deepcopy(cfg.raw)
    raw["events"][0]["probability"] = 0.9
    with pytest.raises(ConfigError, match="sum to 1"):
        config_from_dict(raw)


def test_missing_value_is_reported(cfg):
    raw = copy.deepcopy(cfg.raw)
    del raw["resource"]["regrowth_rate"]
    with pytest.raises(ConfigError, match="resource.regrowth_rate"):
        config_from_dict(raw)


def test_setup_is_deterministic_and_in_range(cfg):
    for seed in range(200):
        a, b = draw_group_setup(seed, cfg), draw_group_setup(seed, cfg)
        assert a == b
        assert cfg.rounds_min <= a.n_rounds <= cfg.rounds_max
        assert len(a.events) == a.n_rounds
        assert all(cfg.wealth_min <= w <= cfg.wealth_max and isinstance(w, int) for w in a.wealth0)
        assert all(cfg.skill_min <= s <= cfg.skill_max for s in a.skills)
    assert draw_group_setup(1, cfg) != draw_group_setup(2, cfg)


def test_event_frequencies_follow_config(cfg):
    counts = {e.name: 0 for e in cfg.events}
    total = 0
    for seed in range(2000):
        for e in draw_group_setup(seed, cfg).events:
            counts[e] += 1
            total += 1
    for e in cfg.events:
        assert counts[e.name] / total == pytest.approx(e.probability, abs=0.02)


def test_initial_state_and_default_policy(cfg):
    s = draw_group_setup(7, cfg)
    st = initial_state(s, cfg)
    assert st.round == 1 and st.stock == cfg.stock_initial and st.infra == cfg.infra_initial
    assert st.wealth == [float(w) for w in s.wealth0] and st.capital == [0.0] * 4
    p = default_policy(cfg)
    assert (p.quota, p.tax_rate, p.match_rate, p.fine, p.audit_prob, p.insurance) == (0, 0, 0, 0, 0, False)
