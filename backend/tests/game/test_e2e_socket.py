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


_tasks: set = set()
_errors: list = []
AUTH = {"Authorization": "Basic " + base64.b64encode(b"admin:secret").decode()}


async def onboarding_step(c, s, log: dict) -> bool:
    """Walk a client through consent, quiz, practice rounds, waiting room and questionnaire.

    Returns True when the state was an onboarding/exit state (handled here)."""
    from app.game import onboarding
    from app.game.service import get_service

    view = s["view"]
    if view == "lobby":
        step = s["step"]
        log.setdefault("steps", []).append(step)
        if step == "consent":
            assert (await c.call("give_consent", {"consent": True}))["ok"]
        elif step == "instructions":
            qs = onboarding.quiz_questions(get_service().cfg, s["condition"], s["role"])
            if not s["quiz"]["attempts_used"]:     # first attempt deliberately wrong, second right
                bad = {q.id: (q.answer + 1) % len(q.options) for q in qs}
                ack = await c.call("submit_quiz", {"answers": bad})
                assert ack["ok"] and not ack["passed"] and ack["attempts_left"] == 1
            else:
                ack = await c.call("submit_quiz", {"answers": {q.id: q.answer for q in qs}, "seconds": 12})
                assert ack["ok"] and ack["passed"], ack
        elif step == "practice":
            assert (await c.call("start_practice", {}))["ok"]
        elif step == "ready":
            log["enter"] = await c.call("enter_waiting_room", {"instructions_seconds": 30})
        return True
    if view == "game" and s.get("practice"):
        log["practice"] = True
        if s["phase"] == "finished":
            assert s["computer_seats"] and all(lab.startswith("Computer")
                                               for i, lab in enumerate(s["labels"]) if i in s["computer_seats"])
            assert (await c.call("finish_practice", {}))["ok"]
            return True
        return False      # practice rounds are played like the real game
    if view == "game" and s["phase"] == "finished" and "questionnaire" not in log:
        log["questionnaire"] = True
        q = await c.call("get_questionnaire", {})
        assert q["ok"], q
        answers = {it["id"]: (4 if it["kind"] == "likert7" else
                              "Prefer not to say" if it["kind"] == "choice" else None) for it in q["items"]}
        assert (await c.call("submit_questionnaire", {"answers": answers}))["ok"]
        return False      # the caller still records the final screen
    if view == "exit":
        log["exit"] = s
        return True
    return False


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
    logs: dict[int, dict] = {}

    def make_client(i, token):
        c = socketio.AsyncClient()

        lock = asyncio.Lock()

        @c.on("state")
        async def on_state(s):
            # Handle each state in its own task, so awaiting an acknowledgement inside a handler
            # never blocks the client from receiving it; the lock keeps states in order.
            async def run():
                async with lock:
                    while "/" not in c.namespaces:     # the first state arrives during the handshake
                        await asyncio.sleep(0.01)
                    try:
                        await handle(s)
                    except Exception as exc:   # surfaced by the test's final checks
                        _errors.append(repr(exc))
                        raise
            t = asyncio.create_task(run())
            _tasks.add(t)
            t.add_done_callback(_tasks.discard)

        async def handle(s):
            views[i] = s["view"]
            if await onboarding_step(c, s, logs.setdefault(i, {})):
                return
            if s["view"] != "game":
                return
            if s["phase"] == "finished":
                if not s.get("practice"):
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
        # Nobody may skip ahead to the waiting room.
        early = await c.call("enter_waiting_room", {})
        assert not early["ok"] and "first" in early["error"]

    async def wait():
        while sum(1 for lg in logs.values() if "exit" in lg) < 4 or len(views) < 5 \
                or not any(v == "full" or (lg.get("enter") or {}).get("ok") is False
                           for v, lg in ((views.get(k), logs.get(k, {})) for k in range(5))):
            await asyncio.sleep(0.05)
    await asyncio.wait_for(wait(), 90)
    assert not _errors, _errors
    # Only one group is planned: four play, the fifth is turned away.
    assert len(finished) == 4
    exits = [lg["exit"] for lg in logs.values() if "exit" in lg]
    assert all(e["outcome"] == "completed" and e["bonus"] > 0 and e["show_up_fee"] > 0 for e in exits)
    assert all(lg["steps"][:4] == ["consent", "instructions", "instructions", "practice"] and lg["practice"]
               for lg in logs.values() if "exit" in lg)
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
        assert statuses.count("completed") == 4
        assert counts["questionnaire"] == 4 and counts["quiz_attempt"] >= 8 and counts["consent"] >= 4
        # Practice rounds are logged apart from the real game.
        assert counts["practice_decision"] >= 4 * 2 * 2 and counts["practice_game_finished"] >= 4


async def test_human_coordinator_game_over_sockets(server):
    async with httpx.AsyncClient(base_url=server) as http:
        r = await http.post("/api/admin/sessions", json={"conditions": ["human"], "seeds": [42]}, headers=AUTH)
        assert r.status_code == 200, r.text
        code = r.json()["session_code"]
        joins = [(await http.post("/api/join", json={"session_code": code})).json() for _ in range(5)]

    finished, roles, clients, sent = {}, {}, [], []
    logs: dict[int, dict] = {}

    def make_client(i):
        c = socketio.AsyncClient()

        lock = asyncio.Lock()

        @c.on("state")
        async def on_state(s):
            # Handle each state in its own task, so awaiting an acknowledgement inside a handler
            # never blocks the client from receiving it; the lock keeps states in order.
            async def run():
                async with lock:
                    while "/" not in c.namespaces:     # the first state arrives during the handshake
                        await asyncio.sleep(0.01)
                    try:
                        await handle(s)
                    except Exception as exc:   # surfaced by the test's final checks
                        _errors.append(repr(exc))
                        raise
            t = asyncio.create_task(run())
            _tasks.add(t)
            t.add_done_callback(_tasks.discard)

        async def handle(s):
            if s["view"] == "lobby" and "role" in s:
                roles[i] = (s["condition"], s["role"])
            if await onboarding_step(c, s, logs.setdefault(i, {})):
                return
            if s["view"] != "game":
                return
            if s["phase"] == "finished":
                if not s.get("practice"):
                    finished[i] = (s["role"], s["final"])
                return
            if s.get("practice") and s["phase"] == "communication":
                raise AssertionError("practice rounds have no communication step")
            if s["done"]:
                return
            if s["role"] == "coordinator":
                if s["phase"] == "communication":
                    pending = [m for m in s["observation"]["inbox"]
                               if m["type"] == "bribe" and m["status"] == "pending"]
                    for m in pending:
                        await c.emit("respond_bribe", {"offer_id": m["offer_id"], "accept": True,
                                                       "favor": "audit_immune", "reply": "ok"})
                    if s["round"] > 1 or any(m["type"] == "bribe" for m in s["observation"]["inbox"]):
                        await c.emit("ready", {"phase": "communication"})
                    return
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
            elif s["phase"] == "communication" and s["round"] == 1 and s["seat"] == 0 and not sent \
                    and not s.get("practice"):
                sent.append(True)
                assert (await c.call("send_message", {"channel": "public", "text": "hi group"}))["ok"]
                assert (await c.call("offer_bribe", {"amount": 5, "note": "be kind"}))["ok"]
                await c.emit("ready", {"phase": "communication"})
            elif s["phase"] in ("event", "communication", "resolution"):
                await c.emit("ready", {"phase": s["phase"]})

        return c

    for i, j in enumerate(joins):
        c = make_client(i)
        await c.connect(server, socketio_path="/ws", transports=["websocket"], auth={"token": j["token"]})
        clients.append(c)

    async def wait():
        while sum(1 for lg in logs.values() if "exit" in lg) < 5:
            await asyncio.sleep(0.05)
    await asyncio.wait_for(wait(), 120)
    assert Counter(r for _c, r in roles.values()) == {"player": 4, "coordinator": 1}
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
        kinds = dict((await db.execute(select(EventLog.kind, func.count()).group_by(EventLog.kind))).all())
        assert kinds["message"] == 1 and kinds["bribe_offered"] == 1 and kinds["bribe_response"] == 1
        assert kinds["favor_granted"] == 1 and kinds["bribe_settled"] == 1
