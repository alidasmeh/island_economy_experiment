"""Round resolution: the pure payoff and state-update function (section 5).

``resolve_round`` performs no I/O. Given the same state, decisions, policy,
event and RNG state it always returns the same new state and ledger.

Money flows are tracked on a per-player running balance in the order of
section 5, so no deduction can push a player below zero:
  * premiums, transfers and bribes are capped at the balance at that step;
  * fines (quota fines from step 2, bribery fines from step 10) are assessed
    when they occur and collected at step 12, capped at the remaining balance.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

from .config import Config, EventSpec
from .metrics import gini, welfare
from .types import (
    BribeLedger,
    BribeOffer,
    Decision,
    GroupLedger,
    GroupState,
    PlayerLedger,
    Policy,
    RoundLedger,
)

EPS = 1e-9


def resolve_round(
    state: GroupState,
    decisions: Sequence[Decision],
    policy: Policy,
    event: EventSpec,
    rng: random.Random,
    *,
    cfg: Config,
    bribes: Sequence[BribeOffer] = (),
) -> tuple[GroupState, RoundLedger]:
    n = state.n
    if len(decisions) != n:
        raise ValueError(f"expected {n} decisions, got {len(decisions)}")
    for i, d in enumerate(decisions):
        if d.harvest + d.contribute + d.save != cfg.effort_points or min(d.harvest, d.contribute, d.save) < 0:
            raise ValueError(f"invalid effort split for seat {i}")

    # Uniform draws are taken in a fixed order and always in full, so the same
    # seed produces the same audit/detection draws whatever players decide.
    u_audit = [rng.random() for _ in range(n)]
    u_detect = [rng.random() for _ in bribes]

    S, A = state.stock, state.infra
    new = state.copy()
    pl = [
        PlayerLedger(
            seat=i,
            harvest_effort=d.harvest,
            contribute_effort=d.contribute,
            save_effort=d.save,
            timeout=d.timeout,
            wealth_before=state.wealth[i],
            capital_before=state.capital[i],
            transfer_to=d.transfer_to,
            transfer_requested=float(d.transfer_amount or 0.0),
        )
        for i, d in enumerate(decisions)
    ]
    gl = GroupLedger(round=state.round, event=event.name, stock_before=S, infra_before=A,
                     pool_before=state.insurance_pool, redistribution_rule=policy.redistribution)
    bal = list(state.wealth)

    # 1. Raw harvest, scaled down if it exceeds the stock.
    for i, d in enumerate(decisions):
        pl[i].harvest_raw = cfg.catchability * d.harvest * S * state.skill[i] * A * event.harvest_mult
    gl.total_harvest_raw = sum(p.harvest_raw for p in pl)
    if gl.total_harvest_raw > S and gl.total_harvest_raw > 0:
        gl.harvest_scale = S / gl.total_harvest_raw
    for p in pl:
        p.harvest = p.harvest_raw * gl.harvest_scale
    gl.total_harvest = sum(p.harvest for p in pl)

    # 2. Quota and audit.
    if policy.quota > 0:
        for i, p in enumerate(pl):
            fav = policy.favors_for(i)
            if fav.quota_exempt or p.harvest <= policy.quota + EPS:
                continue
            p.over_quota = p.harvest - policy.quota
            if not fav.audit_immune and u_audit[i] < policy.audit_prob:
                p.audited = p.caught = True
                p.quota_fine_assessed = policy.fine * p.over_quota

    # 3. Harvest income.
    gl.price = cfg.price * event.price_mult
    for i, p in enumerate(pl):
        p.harvest_income = p.harvest * gl.price
        bal[i] += p.harvest_income

    # 4. Tax into the common pot.
    for i, p in enumerate(pl):
        p.tax = policy.tax_rate * p.harvest_income
        bal[i] -= p.tax
    pot = gl.pot_collected = sum(p.tax for p in pl)

    # 5. Infrastructure, with the match paid out of the pot (scaled if short).
    C = gl.total_contribution = float(sum(d.contribute for d in decisions))
    gl.match_points_requested = policy.match_rate * C
    match_cost_full = gl.match_points_requested * cfg.match_cost_per_point
    if match_cost_full > pot + EPS and match_cost_full > 0:
        gl.match_scale = pot / match_cost_full
    gl.match_cost = match_cost_full * gl.match_scale
    pot -= gl.match_cost
    pot = max(0.0, pot)
    gl.pot_after_match = pot
    A_next = (1 - cfg.infra_depreciation) * A + cfg.infra_gain_per_point * (
        C + gl.match_points_requested * gl.match_scale
    )

    # 6. Redistribution of the remaining pot.
    if policy.redistribution == "infrastructure":
        gl.pot_to_infrastructure = pot
        gl.infra_from_pot = cfg.infra_gain_per_pot_coin * pot
        A_next += gl.infra_from_pot
    else:
        weights = _redistribution_weights(policy, state, decisions)
        if sum(weights) <= EPS:
            gl.redistribution_fallback_equal = True
            weights = _redistribution_weights(policy, state, decisions, rule="equal")
        wsum = sum(weights)
        for i, p in enumerate(pl):
            p.redistribution_weight = weights[i]
            p.redistribution = pot * weights[i] / wsum if pot > 0 else 0.0
            bal[i] += p.redistribution
        gl.pot_redistributed = sum(p.redistribution for p in pl)
    gl.infra_after = A_next

    # 7. Insurance: premium from everyone while on; the pool pays out equally on
    #    payout events (storm) whenever it holds money.
    pool = state.insurance_pool
    if policy.insurance:
        for i, p in enumerate(pl):
            p.premium = min(cfg.insurance_premium, max(0.0, bal[i]))
            bal[i] -= p.premium
        gl.premiums = sum(p.premium for p in pl)
        pool += gl.premiums
    if event.insurance_payout and pool > 0:
        share = pool / n
        for i, p in enumerate(pl):
            p.insurance_payout = share
            bal[i] += share
        gl.pool_payout = pool
        pool = 0.0
    gl.pool_after = new.insurance_pool = pool

    # 8. Saving into private capital.
    for i, (p, d) in enumerate(zip(pl, decisions)):
        p.interest = cfg.interest_rate * state.capital[i]
        p.saving_added = cfg.saving_return_per_point * d.save
        p.capital_after = new.capital[i] = state.capital[i] + p.interest + p.saving_added

    # 9. Player-to-player transfers (outgoing capped at the pre-transfer balance).
    outgoing = []
    for i, (p, d) in enumerate(zip(pl, decisions)):
        to = d.transfer_to
        amt = float(d.transfer_amount or 0.0)
        if amt > 0 and to is not None and 0 <= to < n and to != i:
            p.transfer_out = min(amt, max(0.0, bal[i]))
            outgoing.append((i, to, p.transfer_out))
    for i, to, amt in outgoing:
        bal[i] -= amt
        bal[to] += amt
        pl[to].transfer_in += amt

    # 10. Bribes: accepted offers are paid (if within the coordinator's cap), and
    #     each executed bribe is detected with probability p_detect.
    bl: list[BribeLedger] = []
    coord = new.coordinator
    for b, u in zip(bribes, u_detect):
        rec = BribeLedger(offer_id=b.offer_id, sender=b.sender, amount=b.amount, accepted=b.accepted)
        bl.append(rec)
        if not b.accepted:
            rec.rejected_reason = "refused"
            continue
        income = cfg.bribe_income_rate * b.amount
        if coord.bribe_income + income > cfg.bribe_income_cap + EPS:
            rec.rejected_reason = "cap_reached"
            continue
        rec.paid = min(b.amount, max(0.0, bal[b.sender]))
        rec.coordinator_income = cfg.bribe_income_rate * rec.paid
        rec.executed = True
        bal[b.sender] -= rec.paid
        pl[b.sender].bribes_paid += rec.paid
        coord.bribe_gross += rec.paid
        coord.bribe_income += rec.coordinator_income
        if u < cfg.bribe_detection_prob:
            rec.detected = True
            pl[b.sender].bribe_fine_assessed += cfg.bribe_fine
            coord.fines += cfg.bribe_fine
            gl.coordinator_fines += cfg.bribe_fine
    gl.bribes_paid = sum(r.paid for r in bl)
    gl.coordinator_bribe_income = sum(r.coordinator_income for r in bl)

    # 11. Stock update (no regrowth if the stock started below S_min).
    gl.collapsed = S < cfg.stock_min
    gl.regrowth = 0.0 if gl.collapsed else (
        cfg.regrowth_rate * S * (1 - S / cfg.carrying_capacity) * event.regrowth_mult
    )
    gl.stock_after = new.stock = max(0.0, S + gl.regrowth - gl.total_harvest)
    new.infra = A_next

    # 12. Wealth: collect fines (capped at the remaining balance) and finalize.
    for i, p in enumerate(pl):
        p.fines_assessed = p.quota_fine_assessed + p.bribe_fine_assessed
        p.fines_paid = min(p.fines_assessed, max(0.0, bal[i]))
        bal[i] -= p.fines_paid
        p.wealth_after = new.wealth[i] = bal[i]
    gl.fines_paid = sum(p.fines_paid for p in pl)
    gl.fines_unpaid = sum(p.fines_assessed - p.fines_paid for p in pl)

    new.last_allocation = [d.allocation for d in decisions]
    new.round = state.round + 1
    gl.welfare = welfare(new.wealth, new.capital)
    gl.gini = gini([new.total(i) for i in range(n)])
    ledger = RoundLedger(group=gl, players=pl, bribes=bl)
    gl.conservation_error = conservation_error(state, new, ledger)
    return new, ledger


def _redistribution_weights(policy: Policy, state: GroupState, decisions: Sequence[Decision],
                            rule: str | None = None) -> list[float]:
    rule = rule or policy.redistribution
    n = state.n
    if rule == "equal":
        base = [1.0] * n
    elif rule == "need":
        totals = [state.total(i) for i in range(n)]
        top = max(totals)
        base = [top - t for t in totals]
    elif rule == "contribution":
        base = [float(d.contribute) for d in decisions]
    else:
        raise ValueError(f"no weights for rule {rule!r}")
    return [w * (2.0 if policy.favors_for(i).double_redistribution_weight else 1.0) for i, w in enumerate(base)]


def conservation_error(before: GroupState, after: GroupState, ledger: RoundLedger) -> float:
    """Coins in − coins out for one round; should be ~0.

    Players' coins (wealth + capital) plus the insurance pool change only by:
      + harvest income + new savings + interest            (created)
      − pot spent on infrastructure (match + infra rule)    (converted to A)
      − fines paid                                          (destroyed)
      − bribes paid                                         (leave to the coordinator)
    and the pot must be fully used (tax = match + redistribution + infra).
    """
    g, ps = ledger.group, ledger.players
    held_before = sum(before.wealth) + sum(before.capital) + before.insurance_pool
    held_after = sum(after.wealth) + sum(after.capital) + after.insurance_pool
    created = sum(p.harvest_income + p.saving_added + p.interest for p in ps)
    removed = g.match_cost + g.pot_to_infrastructure + g.fines_paid + g.bribes_paid
    flow_err = (held_after - held_before) - (created - removed)
    pot_err = g.pot_collected - (g.match_cost + g.pot_redistributed + g.pot_to_infrastructure)
    return abs(flow_err) + abs(pot_err)


@dataclass
class FinalSettlement:
    pool_refund: list[float]
    payoff_coins: list[float]          # final wealth + capital (+ pool refund)
    payoff_money: list[float]
    coordinator_welfare_bonus: float
    coordinator_bribe_income: float
    coordinator_fines: float
    coordinator_payoff_coins: float
    coordinator_payoff_money: float


def settle_game(state: GroupState, cfg: Config, *, has_coordinator: bool) -> FinalSettlement:
    """Final payoffs: wealth + capital (+ equal refund of a leftover insurance pool)."""
    n = state.n
    refund = [state.insurance_pool / n if cfg.insurance_refund_pool_at_end else 0.0] * n
    coins = [state.wealth[i] + state.capital[i] + refund[i] for i in range(n)]
    money = [c / cfg.coins_per_currency_unit for c in coins]
    bonus = cfg.welfare_bonus_rate * sum(coins) if has_coordinator else 0.0
    c = state.coordinator
    coord_coins = max(0.0, bonus + c.bribe_income - c.fines) if has_coordinator else 0.0
    return FinalSettlement(
        pool_refund=refund,
        payoff_coins=coins,
        payoff_money=money,
        coordinator_welfare_bonus=bonus,
        coordinator_bribe_income=c.bribe_income,
        coordinator_fines=c.fines,
        coordinator_payoff_coins=coord_coins,
        coordinator_payoff_money=coord_coins / cfg.coins_per_currency_unit,
    )
