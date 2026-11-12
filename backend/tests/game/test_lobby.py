"""Lobby: condition/role allocation before the instructions, and group formation."""

import random
from collections import Counter

import pytest

from app.game import repo
from app.game.lobby import Lobby, plan_assignments
from app.game.runtime import ActionError
from app.game.store import MemoryEventStore

from .test_runtime import FakeTransport


@pytest.fixture
async def db(tmp_path):
    from app.models import database

    database.configure_database(f"sqlite+aiosqlite:///{tmp_path}/lobby.db")
    await database.init_db()
    yield


async def new_session(conditions, seeds):
    s = await repo.create_session(label="t", assignments=plan_assignments(conditions, seeds), params_path="",
                                  params_sha256="x", params={}, code_version="")
    return s.id


async def arrive(lobby, code):
    """A participant joins, connects and consents (allocation happens right after consent)."""
    p, _token, _new = await repo.join_participant(code, external_id=None)
    lobby.connected(p.id)
    first = await lobby.snapshot(await repo.participant_by_id(p.id))
    assert first["step"] == "consent" and "role" not in first      # nothing is allocated before consent
    await lobby.give_consent(await repo.participant_by_id(p.id), {"consent": True})
    snap = await lobby.snapshot(await repo.participant_by_id(p.id))
    return p.id, snap


async def ready(pid):
    """Skip the quiz and practice rounds (tested in test_onboarding)."""
    await repo.update_participant(pid, status="practice_done")
    return await repo.participant_by_id(pid)


@pytest.fixture
def lobby(cfg):
    lob = Lobby(cfg, MemoryEventStore(), FakeTransport(), rng=random.Random(3))
    yield lob


async def test_human_group_gets_one_coordinator(db, lobby):
    code = await new_session(["human"], [1])
    snaps = [await arrive(lobby, code) for _ in range(5)]
    roles = Counter((s["condition"], s["role"]) for _pid, s in snaps)
    assert roles == {("human", "player"): 4, ("human", "coordinator"): 1}
    for pid, _s in snaps:
        await lobby.enter_waiting_room(await ready(pid))
    rt = next(iter(lobby.groups.values()))
    coord = next(pid for pid, s in snaps if s["role"] == "coordinator")
    assert rt.coordinator == coord and coord not in rt.seats and len(rt.seats) == 4
    p = await repo.participant_by_id(coord)
    assert p.role == "coordinator" and p.seat is None and p.status == "playing"
    for t in lobby.groups.values():
        t.task.cancel()


async def test_coordinator_role_is_random(db, cfg):
    """Over many sessions, each arrival position is about equally likely to become coordinator."""
    firsts = Counter()
    lob = Lobby(cfg, MemoryEventStore(), FakeTransport(), rng=random.Random(11))
    for _ in range(60):
        code = await new_session(["human"], [1])
        for pos in range(5):
            _pid, s = await arrive(lob, code)
            if s["role"] == "coordinator":
                firsts[pos] += 1
    assert sum(firsts.values()) == 60 and len(firsts) >= 4 and max(firsts.values()) < 30


async def test_mixed_session_fills_planned_groups_in_order(db, lobby):
    code = await new_session(["none", "human"], [5])         # plan: none(seed 5), human(seed 5)
    snaps = [await arrive(lobby, code) for _ in range(9)]
    conds = [s["condition"] for _pid, s in snaps]
    assert conds[:4] == ["none"] * 4 and conds[4:] == ["human"] * 5
    assert sum(s["role"] == "coordinator" for _pid, s in snaps) == 1
    # Nobody left: a tenth arrival overbooks the earliest planned group.
    _pid, s = await arrive(lobby, code)
    assert s["view"] == "lobby" and s["condition"] == "none"


async def test_seat_is_freed_when_someone_leaves_during_instructions(db, lobby):
    code = await new_session(["none", "human"], [5])
    first = [await arrive(lobby, code) for _ in range(4)]
    lobby.disconnected(first[0][0])                           # left during the instructions
    _pid, s = await arrive(lobby, code)
    assert s["condition"] == "none"                           # takes the freed seat
    p = await repo.participant_by_id(first[0][0])
    assert p.condition == "none"                              # allocation is kept if they come back


async def test_groups_start_when_their_condition_is_complete(db, lobby):
    code = await new_session(["human", "none"], [5])          # human planned first
    snaps = [await arrive(lobby, code) for _ in range(9)]
    none_pids = [pid for pid, s in snaps if s["condition"] == "none"]
    for pid in none_pids:
        await lobby.enter_waiting_room(await ready(pid))
    assert [rt.condition for rt in lobby.groups.values()] == ["none"]   # does not wait for the human group
    assert next(iter(lobby.groups)).endswith("g002")
    for rt in lobby.groups.values():
        rt.task.cancel()


async def test_full_session(db, lobby):
    code = await new_session(["none"], [5])
    snaps = [await arrive(lobby, code) for _ in range(5)]
    for pid, _s in snaps[:4]:
        await lobby.enter_waiting_room(await ready(pid))
    with pytest.raises(ActionError, match="full"):
        await lobby.enter_waiting_room(await ready(snaps[4][0]))
    _pid, s = await arrive(lobby, code)
    assert s == {"view": "full"}
    for rt in lobby.groups.values():
        rt.task.cancel()
