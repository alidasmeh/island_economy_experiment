"""Development tool: fill seats in a session with scripted clients over the real API.

Lets one person test the multiplayer flow in a browser:

    poetry run python -m app.devtools.fake_players --session CODE --n 3

Each fake player joins via POST /api/join, connects over Socket.IO like a browser,
consents, passes the quiz, plays the practice rounds, enters the waiting room, plays a
fixed bot strategy and answers the questionnaire. For testing only: in a real
session these would be indistinguishable from participants, so never run it there.
"""

from __future__ import annotations

import argparse
import asyncio
import random

import httpx
import socketio

from app.bots import STRATEGIES
from app.engine import load_config
from app.game import onboarding


async def fake_player(i: int, url: str, code: str, strategy: str, delay: tuple[float, float],
                      chatty: bool = False) -> None:
    cfg = load_config()
    alloc = cfg.bot_allocations.get(strategy) or cfg.bot_allocations["conditional_first_round"]
    async with httpx.AsyncClient(base_url=url) as http:
        r = await http.post("/api/join", json={"session_code": code, "prolific_pid": f"FAKE_{code}_{i}"})
        r.raise_for_status()
        token = r.json()["token"]
    sio = socketio.AsyncClient()
    done = asyncio.Event()
    acted: set[tuple[bool, int, str]] = set()
    answered: set[str] = set()

    lock = asyncio.Lock()
    tasks: set[asyncio.Task] = set()

    @sio.on("state")
    async def on_state(s):
        # Each state is handled in its own task (awaiting an ack inside a handler would block
        # the client from receiving it); the lock keeps them in order.
        async def run():
            async with lock:
                while "/" not in sio.namespaces:
                    await asyncio.sleep(0.01)
                await handle(s)
        t = asyncio.create_task(run())
        tasks.add(t)
        t.add_done_callback(tasks.discard)

    async def onboard(s) -> bool:
        view = s.get("view")
        if view == "lobby":
            if s["step"] == "consent":
                await sio.call("give_consent", {"consent": True})
            elif s["step"] == "instructions":
                qs = onboarding.quiz_questions(cfg, s["condition"], s["role"])
                await sio.call("submit_quiz", {"answers": {q.id: q.answer for q in qs}})
            elif s["step"] == "practice":
                await sio.call("start_practice", {})
            elif s["step"] == "ready":
                ack = await sio.call("enter_waiting_room", {})
                print(f"fake player {i} ({strategy}): {ack}", flush=True)
                if not ack.get("ok"):
                    done.set()
            return True
        if view == "game" and s.get("practice") and s["phase"] == "finished":
            await sio.call("finish_practice", {})
            return True
        if view in ("questionnaire",) or (view == "game" and s["phase"] == "finished"):
            q = await sio.call("get_questionnaire", {})
            if q.get("ok"):
                answers = {it["id"]: random.randint(1, 7) if it["kind"] == "likert7" else
                           "Prefer not to say" if it["kind"] == "choice" else None for it in q["items"]}
                await sio.call("submit_questionnaire", {"answers": answers})
            return True
        if view in ("exit", "full", "unavailable") or s.get("status") == "aborted":
            done.set()
            return True
        return False

    async def handle(s):
        if await onboard(s) or s.get("view") != "game":
            return
        if s.get("role") == "coordinator" and s["phase"] == "communication":
            # Answer every new offer (offers can arrive after this fake coordinator is already done).
            for m in s["observation"]["inbox"]:
                if m["type"] == "bribe" and m["status"] == "pending" and m["round"] == s["round"] \
                        and m["offer_id"] not in answered:
                    answered.add(m["offer_id"])
                    yes = random.random() < 0.5
                    await sio.call("respond_bribe", {"offer_id": m["offer_id"], "accept": yes,
                                                     "reply": "OK" if yes else "No, thanks",
                                                     "favor": "quota_exempt" if yes else None})
        key = (s.get("practice", False), s["round"], s["phase"])
        if s["done"] or key in acted:
            return
        if s.get("role") == "coordinator" and s["phase"] == "decision":
            return
        acted.add(key)
        await asyncio.sleep(random.uniform(*delay))
        if chatty and s["phase"] == "communication" and s.get("role") == "player":
            await sio.call("send_message", {"channel": "public", "text": f"Round {s['round']}: hello from {s['label']}"})
            if s.get("has_coordinator"):
                await sio.call("send_message", {"channel": "direct", "to": "coordinator",
                                                "text": f"{s['label']} here, privately."})
                if s["round"] <= 2:
                    await sio.call("offer_bribe", {"amount": 5 + i, "note": f"From {s['label']}: go easy on me"})
        if s["phase"] == "policy" and s.get("role") != "coordinator":
            return
        if s["phase"] == "policy":
            policy = {k: v for k, v in cfg.bot_stub_policy.items() if k != "favors"}
            ack = await sio.call("submit_policy", {"round": s["round"], **policy})
        elif s["phase"] == "decision":
            if strategy == "random":
                e = cfg.effort_points
                a, b = sorted(random.sample(range(e + 2), 2))
                split = {"harvest": a, "contribute": b - a - 1, "save": e + 1 - b}
            else:
                split = dict(alloc)
            ack = await sio.call("submit_decision", {"round": s["round"], **split})
        elif s["phase"] == "resolution" and s.get("role") == "player":
            await sio.call("submit_rating", {"round": s["round"], "rating": random.randint(1, 7)})
            ack = await sio.call("ready", {"phase": "resolution"})
        else:
            ack = await sio.call("ready", {"phase": s["phase"]})
        if not ack.get("ok"):
            print(f"fake player {i}: {ack}")

    await sio.connect(url, socketio_path="/ws", transports=["websocket"], auth={"token": token})
    await done.wait()
    await sio.disconnect()


async def main_async(args: argparse.Namespace) -> None:
    strategies = (args.strategy * args.n)[: args.n]
    await asyncio.gather(*(fake_player(i, args.url, args.session.upper(), s, (args.min_delay, args.max_delay),
                                       args.chatty)
                           for i, s in enumerate(strategies)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--session", required=True, help="session code")
    ap.add_argument("--n", type=int, default=3, help="number of fake players")
    ap.add_argument("--strategy", nargs="+", default=["conditional"], choices=STRATEGIES,
                    help="strategies, cycled over the fake players (conditional plays its first-round split)")
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--chatty", action="store_true",
                    help="islanders post a chat message and a DM each round, and offers in rounds 1-2")
    ap.add_argument("--min-delay", type=float, default=1.0)
    ap.add_argument("--max-delay", type=float, default=3.0)
    asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    main()
