"""End to end: real uvicorn server, SQLite, REST join, 4 Socket.IO clients play a `none` game."""

import asyncio
import base64
import socket
from collections import Counter

import httpx
import pytest
import socketio
import uvicorn
from sqlalchemy import func, select


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def server(tmp_path, monkeypatch):
    monkeypatch.setenv("DASHBOARD_USERNAME", "admin")
    monkeypatch.setenv("DASHBOARD_PASSWORD", "secret")
    monkeypatch.setenv("ISLAND_TIME_SCALE", "0.05")   # 15 s phases -> 0.75 s
    from app.models import database

    database.configure_database(f"sqlite+aiosqlite:///{tmp_path}/e2e.db")
    from app.main import app

    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    task = asyncio.create_task(srv.serve())
    for _ in range(500):
        if srv.started or task.done():
            break
        await asyncio.sleep(0.01)
    if not srv.started:
        task.cancel()
        raise RuntimeError("test server failed to start")
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    await asyncio.wait_for(task, 10)


AUTH = {"Authorization": "Basic " + base64.b64encode(b"admin:secret").decode()}


async def test_admin_requires_credentials(server):
    async with httpx.AsyncClient(base_url=server) as http:
        assert (await http.post("/api/admin/sessions", json={"seeds": [1]})).status_code == 401
        bad = {"Authorization": "Basic " + base64.b64encode(b"admin:wrong").decode()}
        assert (await http.post("/api/admin/sessions", json={"seeds": [1]}, headers=bad)).status_code == 401
        r = await http.post("/api/admin/sessions", json={"conditions": ["ai"], "seeds": [1]}, headers=AUTH)
        assert r.status_code == 400   # only none | human exist in Study 1
        assert (await http.post("/api/join", json={"session_code": "NOPE"})).status_code == 404
        rules = (await http.get("/api/rules")).json()
        assert rules["effort_points"] == 10 and rules["n_players"] == 4
        assert not any("round" in k for k in rules)   # the number of rounds is never revealed
        assert rules["levers"]["tax_rate"]["max"] == 0.5 and "welfare_bonus_rate" in rules


async def test_socket_rejects_bad_token(server):
    c = socketio.AsyncClient()
    with pytest.raises(socketio.exceptions.ConnectionError):
        await c.connect(server, socketio_path="/ws", transports=["websocket"], auth={"token": "forged"})


async def test_full_game_over_sockets(server):
    async with httpx.AsyncClient(base_url=server) as http:
        r = await http.post("/api/admin/sessions", json={"label": "e2e", "conditions": ["none"], "seeds": [42]},
                            headers=AUTH)
        assert r.status_code == 200, r.text
        code = r.json()["session_code"]
        joins = [(await http.post("/api/join", json={"session_code": code, "prolific_pid": f"PROLIFIC{i}"})).json()
                 for i in range(5)]
        # Re-joining with the same Prolific ID returns the same pseudonymous participant.
        again = (await http.post("/api/join", json={"session_code": code, "prolific_pid": "PROLIFIC0"})).json()
        assert again["participant_id"] == joins[0]["participant_id"]
        # Simultaneous joins with the same Prolific ID resolve to one participant (no 500).
        racing = await asyncio.gather(*(http.post("/api/join", json={"session_code": code, "prolific_pid": "RACE"})
                                        for _ in range(3)))
        assert [r.status_code for r in racing] == [200, 200, 200]
        assert len({r.json()["participant_id"] for r in racing}) == 1

    finished = {}
    clients = []
    views = {}

    def make_client(i, token):
        c = socketio.AsyncClient()

        @c.on("state")
        async def on_state(s):
            views[i] = s["view"]
            if s["view"] != "game":
                return
            if s["phase"] == "finished":
                finished[i] = s["final"]
                return
            if s["done"]:
                return
            if s["phase"] == "decision":
                await c.emit("submit_decision", {"round": s["round"], "harvest": 2 + i, "contribute": 3,
                                                 "save": 5 - i, "slider_changes": i})
            elif s["phase"] == "resolution":
                if s["my_rating"] is None:
                    await c.emit("submit_rating", {"round": s["round"], "rating": 1 + i})
                await c.emit("ready", {"phase": "resolution"})
            else:
                await c.emit("ready", {"phase": s["phase"]})

        return c

    for i, j in enumerate(joins):
        c = make_client(i, j["token"])
        await c.connect(server, socketio_path="/ws", transports=["websocket"], auth={"token": j["token"]})
        clients.append(c)
        ack = await c.call("enter_waiting_room", {})
        if i < 4:
            assert ack["ok"], ack
        else:   # only one group is planned, so the fifth participant is turned away
            assert ack == {"ok": False, "error": "this session is full"}

    async def wait():
        while len(finished) < 4:
            await asyncio.sleep(0.05)
    await asyncio.wait_for(wait(), 60)
    assert views[4] == "full"   # connected after the only planned group had started
    assert all(f["payoff_coins"] > 0 for f in finished.values())
    for c in clients:
        await c.disconnect()

    from app.models.database import get_db
    from app.models.game_models import EventLog, ExternalIdentity, Group, Participant

    async with get_db() as db:
        counts = dict((await db.execute(select(EventLog.kind, func.count()).group_by(EventLog.kind))).all())
        g = (await db.execute(select(Group))).scalar_one()
        assert g.status == "finished" and g.condition == "none" and g.seed == 42
        assert counts["decision"] == 4 * g.n_rounds
        assert counts["round_resolved"] == g.n_rounds and counts["game_finished"] == 1
        assert counts["fairness_rating"] == 4 * g.n_rounds
        # Prolific IDs live only in the mapping table, never in game data.
        assert (await db.execute(select(func.count()).select_from(ExternalIdentity))).scalar() == 6
        payloads = [str(p) for p in (await db.execute(select(EventLog.payload))).scalars()]
        assert not any("PROLIFIC" in p for p in payloads)
        statuses = [p.status for p in (await db.execute(select(Participant))).scalars()]
        assert statuses.count("finished") == 4


async def test_human_coordinator_game_over_sockets(server):
    async with httpx.AsyncClient(base_url=server) as http:
        r = await http.post("/api/admin/sessions", json={"conditions": ["human"], "seeds": [42]}, headers=AUTH)
        assert r.status_code == 200, r.text
        code = r.json()["session_code"]
        joins = [(await http.post("/api/join", json={"session_code": code})).json() for _ in range(5)]

    finished, roles, clients = {}, {}, []

    def make_client(i):
        c = socketio.AsyncClient()

        @c.on("state")
        async def on_state(s):
            if s["view"] == "lobby":
                roles[i] = (s["condition"], s["role"])
            if s["view"] != "game":
                return
            if s["phase"] == "finished":
                finished[i] = (s["role"], s["final"])
                return
            if s["done"]:
                return
            if s["role"] == "coordinator":
                if s["phase"] == "policy":
                    obs = s["observation"]
                    assert "n_rounds" not in obs
                    await c.emit("submit_policy", {"round": s["round"], "tax_rate": 0.2, "redistribution": "equal",
                                                   "announcement": f"Round {s['round']} rules"})
                elif s["phase"] in ("event", "communication", "resolution"):
                    await c.emit("ready", {"phase": s["phase"]})
                return
            if s["phase"] == "decision":
                await c.emit("submit_decision", {"round": s["round"], "harvest": 4, "contribute": 3, "save": 3})
            elif s["phase"] in ("event", "communication", "resolution"):
                await c.emit("ready", {"phase": s["phase"]})

        return c

    for i, j in enumerate(joins):
        c = make_client(i)
        await c.connect(server, socketio_path="/ws", transports=["websocket"], auth={"token": j["token"]})
        clients.append(c)
    for _ in range(100):
        if len(roles) == 5:
            break
        await asyncio.sleep(0.02)
    assert Counter(r for _c, r in roles.values()) == {"player": 4, "coordinator": 1}
    for c in clients:
        assert (await c.call("enter_waiting_room", {"instructions_seconds": 30}))["ok"]

    async def wait():
        while len(finished) < 5:
            await asyncio.sleep(0.05)
    await asyncio.wait_for(wait(), 90)
    coord_final = next(f for role, f in finished.values() if role == "coordinator")
    assert coord_final["welfare_bonus"] > 0
    for c in clients:
        await c.disconnect()

    from app.models.database import get_db
    from app.models.game_models import EventLog, Group

    async with get_db() as db:
        g = (await db.execute(select(Group))).scalar_one()
        assert g.status == "finished" and g.condition == "human"
        pol = (await db.execute(select(EventLog).where(EventLog.kind == "policy"))).scalars().all()
        assert len(pol) == g.n_rounds and not any(p.payload["timeout"] for p in pol)
        assert pol[-1].payload["policy"]["tax_rate"] == 0.2
