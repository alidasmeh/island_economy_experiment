"""Database access for sessions, participants and groups (identities and configuration).

Game events go to the append-only event log via ``store.SqlEventStore``.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.database import get_db
from app.models.game_models import ExperimentSession, ExternalIdentity, Group, Participant, ParticipantToken


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token() -> str:
    return secrets.token_urlsafe(32)


def new_id(prefix: str, nbytes: int = 8) -> str:
    return f"{prefix}{secrets.token_hex(nbytes)}"


async def create_session(*, label: str, assignments: list[dict[str, Any]], params_path: str, params_sha256: str,
                         params: dict[str, Any], code_version: str) -> ExperimentSession:
    async with get_db() as db:
        for _ in range(5):
            code = secrets.token_hex(4).upper()
            if await db.get(ExperimentSession, code) is None:
                break
        s = ExperimentSession(id=code, label=label, assignments=assignments, params_path=params_path,
                              params_sha256=params_sha256, params_snapshot=params, code_version=code_version)
        db.add(s)
        await db.commit()
        return s


async def get_session(code: str) -> ExperimentSession | None:
    async with get_db() as db:
        return await db.get(ExperimentSession, code)


async def list_sessions() -> list[ExperimentSession]:
    async with get_db() as db:
        return list((await db.execute(select(ExperimentSession).order_by(ExperimentSession.created_at.desc()))).scalars())


async def join_participant(session_code: str, *, external_id: str | None, study_id: str = "",
                           external_session_id: str = "") -> tuple[Participant, str, bool]:
    """Create a participant, or add a token for a returning external ID. Returns (participant, token, is_new).

    Two simultaneous joins with the same external ID are resolved by the unique index on
    the mapping table: the losing insert is rolled back and retried as a returning join.
    """
    token = new_token()
    for attempt in range(2):
        async with get_db() as db:
            if external_id:
                q = select(ExternalIdentity).where(ExternalIdentity.session_id == session_code,
                                                   ExternalIdentity.provider == "prolific",
                                                   ExternalIdentity.external_id == external_id)
                ext = (await db.execute(q)).scalar_one_or_none()
                if ext is not None:
                    db.add(ParticipantToken(token_hash=hash_token(token), participant_id=ext.participant_id))
                    await db.commit()
                    return await db.get(Participant, ext.participant_id), token, False
            p = Participant(id=new_id("p_"), session_id=session_code)
            db.add(p)
            await db.flush()
            db.add(ParticipantToken(token_hash=hash_token(token), participant_id=p.id))
            if external_id:
                db.add(ExternalIdentity(participant_id=p.id, session_id=session_code, external_id=external_id,
                                        study_id=study_id, external_session_id=external_session_id))
            try:
                await db.commit()
                return p, token, True
            except IntegrityError:
                await db.rollback()
                if attempt == 1 or not external_id:
                    raise
    raise RuntimeError("unreachable")


async def participant_by_token(token: str) -> Participant | None:
    if not token:
        return None
    async with get_db() as db:
        t = await db.get(ParticipantToken, hash_token(token))
        return await db.get(Participant, t.participant_id) if t else None


async def update_participant(pid: str, **fields: Any) -> None:
    async with get_db() as db:
        p = await db.get(Participant, pid)
        for k, v in fields.items():
            setattr(p, k, v)
        await db.commit()


async def create_group(*, group_id: str, session_id: str, index: int, condition: str, seed: int, n_rounds: int,
                       seats: list[str]) -> None:
    async with get_db() as db:
        db.add(Group(id=group_id, session_id=session_id, index_in_session=index, condition=condition, seed=seed,
                     n_rounds=n_rounds))
        for seat, pid in enumerate(seats):
            p = await db.get(Participant, pid)
            p.group_id, p.seat, p.status, p.role = group_id, seat, "playing", "player"
        await db.commit()


async def finish_group(group_id: str, status: str) -> None:
    async with get_db() as db:
        g = await db.get(Group, group_id)
        g.status, g.finished_at = status, datetime.now(timezone.utc)
        for p in (await db.execute(select(Participant).where(Participant.group_id == group_id))).scalars():
            p.status = "finished" if status == "finished" else status
        await db.commit()


async def groups_in_session(session_id: str) -> list[Group]:
    async with get_db() as db:
        q = select(Group).where(Group.session_id == session_id).order_by(Group.index_in_session)
        return list((await db.execute(q)).scalars())


async def participant_by_id(pid: str) -> Participant | None:
    async with get_db() as db:
        return await db.get(Participant, pid)
