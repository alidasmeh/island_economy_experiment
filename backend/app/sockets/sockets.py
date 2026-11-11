"""Socket.IO transport for the live game.

Clients connect with ``auth={"token": ...}`` (issued by POST /api/join). The
token binds the connection to one pseudonymous participant; every event is
checked against that binding. The server pushes a ``state`` message (a
per-participant snapshot) whenever something the participant may see changes.

Client -> server events (all acknowledged with {"ok": bool, "error"?: str}):
    enter_waiting_room      {instructions_seconds?}
    submit_policy           {round, quota, tax_rate, redistribution, match_rate, fine, audit_prob, insurance,
                             info_policy, announcement}            (coordinator, policy phase)
    submit_decision         {round, harvest, contribute, save, transfer_to?, transfer_amount?,
                             client_response_ms?, slider_changes?}
    ready                   {phase}
    submit_rating           {round, rating}
"""

import logging
from typing import Any

import socketio

from app.game import repo
from app.game.runtime import ActionError
from app.game.service import get_service

log = logging.getLogger(__name__)

# Create Socket.IO server
sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
socket_app = socketio.ASGIApp(socketio_server=sio, socketio_path="/ws")


class SioTransport:
    """Sends to every connection of a participant (each participant has its own room)."""

    async def send(self, participant_id: str, event: str, payload: dict[str, Any]) -> None:
        await sio.emit(event, payload, room=participant_id)


transport = SioTransport()


@sio.on("connect")
async def connect(sid, environ, auth=None):
    token = (auth or {}).get("token") if isinstance(auth, dict) else None
    p = await repo.participant_by_token(token)
    if p is None:
        raise socketio.exceptions.ConnectionRefusedError("invalid or missing token")
    await sio.save_session(sid, {"pid": p.id, "session_id": p.session_id})
    await sio.enter_room(sid, p.id)
    svc = get_service()
    svc.lobby.connected(p.id)
    await svc.store.append("connected", session_id=p.session_id, group_id=p.group_id, participant_id=p.id,
                           payload={"sid": sid})
    await sio.emit("state", await svc.lobby.snapshot(p), to=sid)


@sio.on("disconnect")
async def disconnect(sid, *args):
    sess = await sio.get_session(sid)
    if not sess:
        return
    svc = get_service()
    await svc.store.append("disconnected", session_id=sess["session_id"], participant_id=sess["pid"],
                           payload={"sid": sid})
    # Leave the waiting room only if this was the participant's last open connection.
    if svc.lobby.disconnected(sess["pid"]) == 0:
        await svc.lobby.leave_waiting_room(sess["pid"], sess["session_id"], reason="disconnected")


async def _call(sid, fn) -> dict[str, Any]:
    sess = await sio.get_session(sid)
    if not sess:
        return {"ok": False, "error": "not authenticated"}
    try:
        return await fn(sess["pid"], sess["session_id"])
    except ActionError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception:  # pragma: no cover - logged, never leaks internals to the client
        log.exception("socket handler failed")
        return {"ok": False, "error": "server error"}


def _runtime(pid: str):
    rt = get_service().lobby.runtime_of(pid)
    if rt is None:
        raise ActionError("you are not in a running group")
    return rt


@sio.on("enter_waiting_room")
async def enter_waiting_room(sid, data=None):
    async def go(pid, session_id):
        p = await repo.participant_by_id(pid)
        if p is None:
            raise ActionError("unknown participant")
        info = {}
        if isinstance(data, dict) and isinstance(data.get("instructions_seconds"), (int, float)):
            info["instructions_seconds"] = max(0, min(int(data["instructions_seconds"]), 86400))
        return await get_service().lobby.enter_waiting_room(p, info)
    return await _call(sid, go)


@sio.on("submit_policy")
async def submit_policy(sid, data=None):
    return await _call(sid, lambda pid, _s: _runtime(pid).submit_policy(pid, data if isinstance(data, dict) else {}))


@sio.on("submit_decision")
async def submit_decision(sid, data=None):
    return await _call(sid, lambda pid, _s: _runtime(pid).submit_decision(pid, data if isinstance(data, dict) else {}))


@sio.on("ready")
async def ready(sid, data=None):
    phase = (data or {}).get("phase") if isinstance(data, dict) else None
    return await _call(sid, lambda pid, _s: _runtime(pid).mark_ready(pid, str(phase)))


@sio.on("submit_rating")
async def submit_rating(sid, data=None):
    return await _call(sid, lambda pid, _s: _runtime(pid).submit_rating(pid, data if isinstance(data, dict) else {}))
