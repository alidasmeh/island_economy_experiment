"""Development tool: fill seats in a session with scripted clients over the real API.

Lets one person test the multiplayer flow in a browser:

    poetry run python -m app.devtools.fake_players --session CODE --n 3

Each fake player joins via POST /api/join, connects over Socket.IO like a browser,
enters the waiting room and plays a fixed bot strategy. For testing only: in a real
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
    acted: set[tuple[int, str]] = set()
    answered: set[str] = set()

    @sio.on("state")
    async def on_state(s):
        if s.get("view") != "game":
            return
        if s["phase"] == "finished" or s.get("status") == "aborted":
            done.set()
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
        key = (s["round"], s["phase"])
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
    ack = await sio.call("enter_waiting_room", {})
    print(f"fake player {i} ({strategy}): {ack}", flush=True)
    if ack.get("ok"):
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
