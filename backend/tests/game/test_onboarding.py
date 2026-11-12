"""Milestone 7: consent, quiz, practice rounds, waiting-room exit, questionnaire, completion codes."""

import asyncio
import dataclasses
import random

import pytest

from app.game import onboarding, repo
from app.game.lobby import Lobby, plan_assignments
from app.game.runtime import ActionError
from app.game.store import MemoryEventStore

from .test_runtime import FakeTransport


@pytest.fixture
async def db(tmp_path):
    from app.models import database

    database.configure_database(f"sqlite+aiosqlite:///{tmp_path}/onboarding.db")
    await database.init_db()
    yield


@pytest.fixture
def fast_cfg(cfg):
    """Timers short enough that practice rounds run out by themselves in a test."""
    return dataclasses.replace(cfg, phase_seconds={k: 0.02 for k in cfg.phase_seconds}, phase_grace_seconds=0.0)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def lobby(fast_cfg, clock):
    store = MemoryEventStore()
    lob = Lobby(fast_cfg, store, FakeTransport(), rng=random.Random(1), clock=clock)
    yield lob
    for rt in [*lob.groups.values(), *lob.practices.values()]:
        if rt.task:
            rt.task.cancel()


async def session(conditions=("none",), codes=None):
    s = await repo.create_session(label="t", assignments=plan_assignments(list(conditions), [1]), params_path="",
                                  params_sha256="x", params={}, code_version="",
                                  settings={"completion_codes": codes or {}})
    return s.id


async def join(lobby, code):
    p, _t, _n = await repo.join_participant(code, external_id=None)
    lobby.connected(p.id)
    return p.id


async def P(pid):
    return await repo.participant_by_id(pid)


async def consent(lobby, pid):
    await lobby.give_consent(await P(pid), {"consent": True})
    return await lobby.snapshot(await P(pid))


def right(cfg, snap):
    return {q.id: q.answer for q in onboarding.quiz_questions(cfg, snap["condition"], snap["role"])}


# ---------------------------------------------------------------------- content


@pytest.mark.parametrize("condition,role", [("none", "player"), ("human", "player"), ("human", "coordinator")])
def test_quiz_versions_are_well_formed(cfg, condition, role):
    qs = onboarding.quiz_questions(cfg, condition, role)
    assert len(qs) >= 4 and len({q.id for q in qs}) == len(qs)
    assert all(0 <= q.answer < len(q.options) and len(set(q.options)) == len(q.options) for q in qs)
    assert all("answer" not in q for q in onboarding.public_quiz(qs))       # answers never leave the server
    passed, wrong, _ = onboarding.grade_quiz(qs, {q.id: q.answer for q in qs})
    assert passed and not wrong
    passed, wrong, cleaned = onboarding.grade_quiz(qs, {qs[0].id: "x", qs[1].id: 99, qs[2].id: True})
    assert not passed and set(wrong) == {q.id for q in qs} and cleaned[qs[0].id] is None


def test_quiz_numbers_come_from_config(cfg):
    text = " ".join(q.text + " ".join(q.options) for q in onboarding.quiz_questions(cfg, "none", "player"))
    assert str(cfg.effort_points) in text and f"{cfg.stock_min:g}" in text


@pytest.mark.parametrize("condition,role,trust", [("none", "player", False), ("human", "player", True),
                                                  ("human", "coordinator", False)])
def test_questionnaire_items(condition, role, trust):
    items = onboarding.questionnaire_items(condition, role)
    ids = [it.id for it in items]
    assert ("trust_coord" in ids) == trust
    assert {"age", "gender"} <= set(ids) and len(set(ids)) == len(ids)
    good = {it.id: 5 if it.kind == "likert7" else "Woman" if it.kind == "choice" else None for it in items}
    out = onboarding.clean_questionnaire(items, {**good, "age": "34", "comments": "  <b>hi</b>\x00 "})
    assert out["age"] == 34 and out["comments"] == "<b>hi</b>"          # plain text, never interpreted
    with pytest.raises(ValueError):
        onboarding.clean_questionnaire(items, {**good, items[0].id: None})   # required item missing
    with pytest.raises(ValueError):
        onboarding.clean_questionnaire(items, {**good, items[0].id: 8})
    with pytest.raises(ValueError):
        onboarding.clean_questionnaire(items, {**good, "gender": "<script>"})
    with pytest.raises(ValueError):
        onboarding.clean_questionnaire(items, {**good, "age": 12})


def test_completion_codes_session_overrides_config(cfg):
    cfg = dataclasses.replace(cfg, completion_codes={"completed": "DEF", "quiz_failed": "QF"})
    info = onboarding.completion_info(cfg, {"completion_codes": {"completed": "SESS1"}}, "completed")
    assert info["code"] == "SESS1" and info["url"].endswith("cc=SESS1")
    assert onboarding.completion_info(cfg, {}, "quiz_failed")["code"] == "QF"
    assert onboarding.completion_info(cfg, {}, "no_group") == {"outcome": "no_group", "code": None, "url": None}


# ---------------------------------------------------------------------- flow


async def test_consent_comes_before_allocation(db, lobby):
    code = await session()
    pid = await join(lobby, code)
    snap = await lobby.snapshot(await P(pid))
    assert snap == {"view": "lobby", "step": "consent", "consent_version": lobby.cfg.consent_version}
    assert (await P(pid)).condition is None
    with pytest.raises(ActionError):
        await lobby.give_consent(await P(pid), {"consent": "yes"})
    with pytest.raises(ActionError):
        await lobby.enter_waiting_room(await P(pid))
    snap = await consent(lobby, pid)
    assert snap["step"] == "instructions" and snap["condition"] == "none"
    with pytest.raises(ActionError, match="already"):
        await lobby.give_consent(await P(pid), {"consent": False})
    logged = [r for r in lobby.store.records if r["kind"] == "consent"]
    assert logged[0]["payload"] == {"given": True, "version": lobby.cfg.consent_version}


async def test_declining_consent_ends_the_study(db, lobby):
    code = await session()
    pid = await join(lobby, code)
    await lobby.give_consent(await P(pid), {"consent": False})
    snap = await lobby.snapshot(await P(pid))
    assert snap["view"] == "exit" and snap["outcome"] == "no_consent" and snap["show_up_fee"] is None
    assert (await P(pid)).condition is None                     # never allocated, holds no seat


async def test_quiz_two_attempts_then_exit_with_show_up_fee(db, lobby):
    code = await session(codes={"quiz_failed": "QUIZ123"})
    pid = await join(lobby, code)
    snap = await consent(lobby, pid)
    assert snap["quiz"]["max_attempts"] == 2 and snap["quiz"]["attempts_used"] == 0
    wrong = {q["id"]: 0 for q in snap["quiz"]["questions"]}
    r = await lobby.submit_quiz(await P(pid), {"answers": wrong})
    assert r["ok"] and not r["passed"] and r["wrong"] and r["attempts_left"] == 1
    snap = await lobby.snapshot(await P(pid))
    assert snap["step"] == "instructions" and snap["quiz"]["attempts_used"] == 1
    r = await lobby.submit_quiz(await P(pid), {"answers": wrong})
    assert not r["passed"] and r["attempts_left"] == 0
    snap = await lobby.snapshot(await P(pid))
    assert snap["view"] == "exit" and snap["outcome"] == "quiz_failed" and snap["code"] == "QUIZ123"
    assert snap["show_up_fee"] == lobby.cfg.show_up_fee and snap["bonus"] is None
    assert pid not in lobby.sessions[code].alloc                 # the seat is free for someone else
    with pytest.raises(ActionError):
        await lobby.submit_quiz(await P(pid), {"answers": wrong})
    attempts = [r["payload"] for r in lobby.store.records if r["kind"] == "quiz_attempt"]
    assert [a["attempt"] for a in attempts] == [1, 2] and all(not a["passed"] for a in attempts)


async def test_quiz_pass_then_practice_then_waiting_room(db, lobby):
    code = await session()
    pid = await join(lobby, code)
    snap = await consent(lobby, pid)
    r = await lobby.submit_quiz(await P(pid), {"answers": right(lobby.cfg, snap)})
    assert r["passed"]
    snap = await lobby.snapshot(await P(pid))
    assert snap["step"] == "practice" and snap["practice_rounds"] == lobby.cfg.practice_rounds
    with pytest.raises(ActionError, match="practice"):
        await lobby.enter_waiting_room(await P(pid))            # practice rounds come first
    with pytest.raises(ActionError):
        await lobby.finish_practice(await P(pid))

    assert (await lobby.start_practice(await P(pid)))["ok"]
    rt = lobby.practices[pid]
    assert lobby.runtime_of(pid) is rt and rt.practice and rt.members() == [pid]
    assert sorted(rt.bots) == [1, 2, 3] and rt.n_rounds == lobby.cfg.practice_rounds
    snap = await lobby.snapshot(await P(pid))
    assert snap["view"] == "game" and snap["practice"] and snap["labels"][1].startswith("Computer")
    assert "communication" not in snap["phases"]
    if rt.status == "running":
        with pytest.raises(ActionError, match="not over"):
            await lobby.finish_practice(await P(pid))
    await asyncio.wait_for(rt.task, 10)                          # times out through every step
    assert rt.status == "finished" and len(rt.ledgers) == lobby.cfg.practice_rounds
    assert (await lobby.finish_practice(await P(pid)))["ok"]
    snap = await lobby.snapshot(await P(pid))
    assert snap["step"] == "ready" and pid not in lobby.practices
    assert (await lobby.enter_waiting_room(await P(pid)))["ok"]

    kinds = [r["kind"] for r in lobby.store.records]
    assert "practice_game_finished" in kinds and "game_finished" not in kinds   # practice is logged apart
    bot_decisions = [r for r in lobby.store.records if r["kind"] == "practice_decision" and r["payload"].get("bot")]
    assert len(bot_decisions) == 3 * lobby.cfg.practice_rounds


async def test_coordinator_practices_with_computer_islanders(db, lobby, fast_cfg):
    code = await session(conditions=("human",))
    pids = [await join(lobby, code) for _ in range(5)]
    snaps = {pid: await consent(lobby, pid) for pid in pids}
    coord = next(pid for pid, s in snaps.items() if s["role"] == "coordinator")
    await lobby.submit_quiz(await P(coord), {"answers": right(fast_cfg, snaps[coord])})
    await lobby.start_practice(await P(coord))
    rt = lobby.practices[coord]
    assert rt.coordinator == coord and rt.condition == "human" and sorted(rt.bots) == [0, 1, 2, 3]
    assert rt.members() == [coord]
    await asyncio.wait_for(rt.task, 10)
    assert rt.status == "finished" and not rt.coordinator_dropped     # no dropout in practice
    snap = rt.snapshot_for_participant(coord)
    assert snap["practice"] and snap["final"] is not None


async def test_leaving_the_waiting_room_after_the_maximum_wait(db, lobby, clock):
    code = await session(codes={"no_group": "NOGRP"})
    pid = await join(lobby, code)
    await consent(lobby, pid)
    await repo.update_participant(pid, status="practice_done")
    await lobby.enter_waiting_room(await P(pid))
    snap = await lobby.snapshot(await P(pid))
    assert snap["view"] == "waiting" and snap["can_leave_at_ms"] > snap["server_now_ms"]
    with pytest.raises(ActionError, match="wait"):
        await lobby.leave_after_waiting(await P(pid))
    clock.t += lobby.cfg.waiting_room_max_seconds + 1
    assert (await lobby.leave_after_waiting(await P(pid)))["ok"]
    snap = await lobby.snapshot(await P(pid))
    assert snap["view"] == "exit" and snap["outcome"] == "no_group" and snap["code"] == "NOGRP"
    assert pid not in lobby.sessions[code].waiting and pid not in lobby.sessions[code].alloc


async def test_questionnaire_then_payment_page(db, lobby):
    code = await session(codes={"completed": "DONE42"})
    pids = [await join(lobby, code) for _ in range(4)]
    for pid in pids:
        await consent(lobby, pid)
        await repo.update_participant(pid, status="practice_done")
        await lobby.enter_waiting_room(await P(pid))
    rt = next(iter(lobby.groups.values()))
    await asyncio.wait_for(rt.task, 30)
    pid = pids[0]
    p = await P(pid)
    assert p.status == "finished" and p.bonus == round(rt.settlement.payoff_money[0], 2)
    with pytest.raises(ActionError):
        await lobby.submit_questionnaire(p, {"answers": {}})                  # required items missing
    items = lobby.questionnaire_public(p)
    answers = {it["id"]: 4 if it["kind"] == "likert7" else "Prefer not to say" if it["kind"] == "choice" else None
               for it in items}
    assert (await lobby.submit_questionnaire(p, {"answers": answers, "seconds": 40}))["ok"]
    snap = await lobby.snapshot(await P(pid))
    assert snap["view"] == "exit" and snap["outcome"] == "completed" and snap["code"] == "DONE42"
    assert snap["bonus"] == p.bonus and snap["show_up_fee"] == lobby.cfg.show_up_fee
    with pytest.raises(ActionError):
        await lobby.submit_questionnaire(await P(pid), {"answers": answers})   # only once
    # A participant whose game ended while the server restarted still gets the questionnaire.
    lobby.by_participant.pop(pids[1], None)
    snap = await lobby.snapshot(await P(pids[1]))
    assert snap["view"] == "questionnaire" and snap["items"]
