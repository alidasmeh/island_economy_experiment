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
