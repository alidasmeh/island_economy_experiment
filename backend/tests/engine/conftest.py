import copy

import pytest

from app.engine import GroupState, load_config
from app.engine.config import config_from_dict
from app.engine.types import CoordinatorAccount


class FixedRng:
    """Stand-in for random.Random that returns a scripted sequence of uniforms."""

    def __init__(self, values=None, default=0.99):
        self.values = list(values or [])
        self.default = default

    def random(self):
        return self.values.pop(0) if self.values else self.default


@pytest.fixture(scope="session")
def cfg():
    return load_config()


@pytest.fixture
def make_cfg(cfg):
    """Build a config from the default with nested overrides, e.g. make_cfg({"resource.price": 2})."""

    def _make(overrides=None):
        raw = copy.deepcopy(cfg.raw)
        for path, value in (overrides or {}).items():
            cur = raw
            keys = path.split(".")
            for k in keys[:-1]:
                cur = cur[k]
            cur[keys[-1]] = value
        return config_from_dict(raw)

    return _make


@pytest.fixture
def make_state(cfg):
    def _make(wealth=(100.0, 100.0, 100.0, 100.0), capital=None, skill=None, stock=None, infra=None,
              pool=0.0, rnd=1):
        n = len(wealth)
        return GroupState(
            round=rnd,
            stock=cfg.stock_initial if stock is None else stock,
            infra=cfg.infra_initial if infra is None else infra,
            insurance_pool=pool,
            wealth=[float(w) for w in wealth],
            capital=[0.0] * n if capital is None else [float(c) for c in capital],
            skill=[1.0] * n if skill is None else list(skill),
            coordinator=CoordinatorAccount(),
            last_allocation=[None] * n,
        )

    return _make


@pytest.fixture
def rng():
    return FixedRng
