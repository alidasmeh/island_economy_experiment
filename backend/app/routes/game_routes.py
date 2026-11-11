"""REST endpoints for the Island Economy game.

    POST /api/join                    participant joins a session -> pseudonymous id + token
    POST /api/admin/sessions          create a session (HTTP Basic: DASHBOARD_USERNAME / DASHBOARD_PASSWORD)
    GET  /api/admin/sessions          list sessions
    GET  /api/admin/sessions/{code}   session detail with live group status
"""

import os
import secrets
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field

from app.game import repo
from app.game.lobby import SUPPORTED_CONDITIONS, plan_assignments
from app.game.service import get_service

game_router = APIRouter(prefix="/api", tags=["game"])
basic = HTTPBasic()


def require_admin(creds: HTTPBasicCredentials = Depends(basic)) -> str:
    user, pw = os.getenv("DASHBOARD_USERNAME") or "", os.getenv("DASHBOARD_PASSWORD") or ""
    ok = bool(user and pw) and secrets.compare_digest(creds.username.encode(), user.encode()) \
        and secrets.compare_digest(creds.password.encode(), pw.encode())
    if not ok:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials", {"WWW-Authenticate": "Basic"})
    return creds.username


class JoinRequest(BaseModel):
    session_code: str = Field(min_length=1, max_length=32)
    prolific_pid: str | None = Field(default=None, max_length=100)
    study_id: str | None = Field(default=None, max_length=100)
    prolific_session_id: str | None = Field(default=None, max_length=100)


@game_router.post("/join")
async def join(req: JoinRequest) -> dict[str, Any]:
    code = req.session_code.strip().upper()
    s = await repo.get_session(code)
    if s is None or s.status != "open":
        raise HTTPException(404, "unknown or closed session")
    p, token, is_new = await repo.join_participant(code, external_id=(req.prolific_pid or "").strip() or None,
                                                   study_id=req.study_id or "",
                                                   external_session_id=req.prolific_session_id or "")
    await get_service().store.append("joined", session_id=code, participant_id=p.id,
                                     payload={"new": is_new, "has_external_id": bool(req.prolific_pid)})
    return {"participant_id": p.id, "token": token, "session_code": code, "status": p.status}


class CreateSessionRequest(BaseModel):
    label: str = Field(default="", max_length=200)
    conditions: list[str] = Field(default_factory=lambda: ["none"], min_length=1)
    seeds: list[int] | None = None          # explicit seeds, or
    n_seeds: int | None = Field(default=None, ge=1, le=10000)   # random seeds drawn server-side


@game_router.post("/admin/sessions")
async def create_session(req: CreateSessionRequest, _admin: str = Depends(require_admin)) -> dict[str, Any]:
    bad = [c for c in req.conditions if c not in SUPPORTED_CONDITIONS]
    if bad:
        raise HTTPException(400, f"unsupported condition(s) {bad}; available: {list(SUPPORTED_CONDITIONS)}")
    if req.seeds:
        seeds = list(req.seeds)
    elif req.n_seeds:
        seeds = [secrets.randbelow(2**31 - 1) + 1 for _ in range(req.n_seeds)]
    else:
        raise HTTPException(400, "give seeds or n_seeds")
    svc = get_service()
    s = await repo.create_session(label=req.label, assignments=plan_assignments(req.conditions, seeds),
                                  params_path=svc.cfg.source_path, params_sha256=svc.cfg.sha256,
                                  params=svc.cfg.raw, code_version=svc.code_version)
    await svc.store.append("session_created", session_id=s.id,
                           payload={"label": s.label, "assignments": s.assignments, "params_sha256": s.params_sha256,
                                    "code_version": s.code_version})
    return {"session_code": s.id, "assignments": s.assignments, "params_sha256": s.params_sha256}


@game_router.get("/admin/sessions")
async def list_sessions(_admin: str = Depends(require_admin)) -> list[dict[str, Any]]:
    return [{"session_code": s.id, "label": s.label, "status": s.status, "created_at": s.created_at.isoformat(),
             "n_groups_planned": len(s.assignments)} for s in await repo.list_sessions()]


@game_router.get("/admin/sessions/{code}")
async def session_detail(code: str, _admin: str = Depends(require_admin)) -> dict[str, Any]:
    s = await repo.get_session(code.upper())
    if s is None:
        raise HTTPException(404, "unknown session")
    lobby = get_service().lobby
    live = lobby.sessions.get(s.id)
    groups = []
    for g in await repo.groups_in_session(s.id):
        rt = lobby.groups.get(g.id)
        groups.append({"group_id": g.id, "condition": g.condition, "seed": g.seed, "n_rounds": g.n_rounds,
                       "status": rt.status if rt else g.status, "phase": rt.phase if rt else None,
                       "round": rt.round if rt else None, "flagged": g.flagged})
    return {"session_code": s.id, "label": s.label, "status": s.status, "assignments": s.assignments,
            "params_sha256": s.params_sha256, "code_version": s.code_version,
            "n_waiting": len(live.waiting) if live else 0, "groups": groups}


@game_router.get("/rules")
async def rules() -> dict[str, Any]:
    """Public game parameters for the instruction pages (never the number of rounds)."""
    cfg = get_service().cfg
    return {
        "n_players": cfg.n_players,
        "effort_points": cfg.effort_points,
        "wealth_min": cfg.wealth_min, "wealth_max": cfg.wealth_max,
        "skill_min": cfg.skill_min, "skill_max": cfg.skill_max,
        "carrying_capacity": cfg.carrying_capacity,
        "stock_initial": cfg.stock_initial,
        "stock_min": cfg.stock_min,
        "regrowth_rate": cfg.regrowth_rate,
        "catchability": cfg.catchability,
        "price": cfg.price,
        "infra_initial": cfg.infra_initial,
        "infra_gain_per_point": cfg.infra_gain_per_point,
        "infra_depreciation": cfg.infra_depreciation,
        "saving_return_per_point": cfg.saving_return_per_point,
        "interest_rate": cfg.interest_rate,
        "events": [{"name": e.name, "probability": e.probability, "harvest_mult": e.harvest_mult,
                    "regrowth_mult": e.regrowth_mult, "price_mult": e.price_mult,
                    "insurance_payout": e.insurance_payout} for e in cfg.events],
        "phase_seconds": {k: round(v) for k, v in cfg.phase_seconds.items()},
        "timeout_default_allocation": cfg.timeout_default_allocation,
        "coins_per_currency_unit": cfg.coins_per_currency_unit,
        "currency": cfg.currency,
        "show_up_fee": cfg.show_up_fee,
        # Coordinator condition
        "levers": {name: {"min": r.min, "max": r.max, "step": r.step}
                   for name, r in (("quota", cfg.lever_quota), ("tax_rate", cfg.lever_tax_rate),
                                   ("match_rate", cfg.lever_match_rate), ("fine", cfg.lever_fine),
                                   ("audit_prob", cfg.lever_audit_prob))},
        "redistribution_options": list(cfg.redistribution_options),
        "info_policy_options": list(cfg.info_policy_options),
        "announcement_max_chars": cfg.announcement_max_chars,
        "insurance_premium": cfg.insurance_premium,
        "infra_gain_per_pot_coin": cfg.infra_gain_per_pot_coin,
        "welfare_bonus_rate": cfg.welfare_bonus_rate,
    }
