"""Island Economy game engine: pure, deterministic, no I/O.

Public API:
    load_config, Config                         -- parameters (config/default.yaml)
    draw_group_setup, initial_state, round_rng  -- seeded group setup (matched design)
    resolve_round                               -- one round of section 5
    settle_game                                 -- final payoffs
    policy_preview                              -- coordinator's estimate of a policy's effects
    validate_decision, validate_policy, timeout_decision
"""

from .config import Config, ConfigError, EventSpec, load_config
from .metrics import gini, welfare
from .preview import policy_preview
from .resolve import FinalSettlement, conservation_error, resolve_round, settle_game
from .setup import GroupSetup, default_policy, draw_group_setup, initial_state, round_rng
from .types import (
    Allocation,
    BribeOffer,
    Decision,
    Favors,
    GroupState,
    Policy,
    RoundLedger,
)
from .validation import ValidationError, timeout_decision, validate_decision, validate_policy

__all__ = [
    "Allocation", "BribeOffer", "Config", "ConfigError", "Decision", "EventSpec", "Favors",
    "FinalSettlement", "GroupSetup", "GroupState", "Policy", "RoundLedger", "ValidationError",
    "conservation_error", "default_policy", "draw_group_setup", "gini", "initial_state",
    "load_config", "policy_preview", "resolve_round", "round_rng", "settle_game", "timeout_decision",
    "validate_decision", "validate_policy", "welfare",
]
