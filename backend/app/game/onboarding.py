"""Onboarding and exit content (Milestone 7): comprehension quiz, questionnaire, completion links.

The quiz is built from the same config as the instructions, so the numbers always
match. Correct answers never leave the server: clients receive ``public_quiz``
and the server grades with ``grade_quiz``.

The questionnaire items are defined here (one place to edit) and served to the
client; answers are validated against the same definitions.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.engine import Config

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def _n(x: float) -> str:
    """Number for display: no trailing zeros."""
    return f"{x:.2f}".rstrip("0").rstrip(".")


def _pct(x: float) -> str:
    return f"{_n(x * 100)}%"


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    options: tuple[str, ...]
    answer: int                       # index into options; never sent to clients

    def public(self) -> dict[str, Any]:
        return {"id": self.id, "text": self.text, "options": list(self.options)}


def quiz_questions(cfg: Config, condition: str, role: str) -> list[Question]:
    """Comprehension questions for one version of the instructions (condition x role)."""
    E = cfg.effort_points
    sea = Question(
        "sea",
        "What happens if the islanders catch so many fish that the sea falls below "
        f"{_n(cfg.stock_min)} fish?",
        ("The sea is refilled at the start of the next round.",
         "The fish stop growing back for good.",
         "Nothing; the number of fish in the sea does not matter."),
        1,
    )
    if role == "coordinator":
        return [
            Question(
                "coord_role",
                "What do you do in each round?",
                ("I fish like the islanders and also set the rules.",
                 "I set the rules for the islanders; I do not fish.",
                 "I only watch; the rules are set by the computer."),
                1,
            ),
            sea,
            Question(
                "coord_pay",
                "How is your bonus calculated?",
                (f"{_pct(cfg.welfare_bonus_rate)} of the islanders' total result at the end, plus "
                 f"{_pct(cfg.bribe_income_rate)} of the offers I accept (at most {_n(cfg.bribe_income_cap)} coins), "
                 f"minus {_n(cfg.bribe_fine)} coins for every accepted offer that is discovered.",
                 "A fixed amount, whatever happens in the game.",
                 "Only the offers I accept."),
                0,
            ),
            Question(
                "coord_offer",
                "An islander makes you an offer and you do not answer it during the communication step. "
                "What happens?",
                ("It is accepted automatically.",
                 "It counts as refused, and the coins stay with the islander.",
                 "It stays open until the next round."),
                1,
            ),
            Question(
                "coord_missed",
                f"What happens if you do not confirm any rules in {cfg.coordinator_missed_policy_phases} "
                "rounds in a row?",
                ("The computer sets new rules for me.",
                 "You count as having left the game: the rules stay as they are for the rest of the game.",
                 "Nothing; the game waits until I confirm."),
                1,
            ),
        ]
    qs = [
        Question(
            "effort",
            "How many effort points do you split between fishing, building and saving in each round?",
            (str(max(1, E // 2)), str(E), str(E * 2), "As many as I like"),
            1,
        ),
        sea,
        Question(
            "build",
            "What does putting effort into building infrastructure do?",
            ("It pays me coins right away.",
             "It makes everyone's fishing more productive in later rounds.",
             "It adds fish to the sea."),
            1,
        ),
        Question(
            "pay",
            "What determines your bonus payment?",
            ("My coins plus my savings at the end of the game.",
             "Only the fish I catch in the last round.",
             "The group's total, shared equally."),
            0,
        ),
    ]
    if condition == "human":
        qs += [
            Question(
                "rules",
                "Who sets the rules (for example taxes, quotas and fines) in your group?",
                ("Nobody; there are no rules.",
                 "The coordinator, another participant in this study.",
                 "The computer."),
                1,
            ),
            Question(
                "offer",
                "You make the coordinator an offer and it is refused or not answered. What happens to the coins?",
                ("They stay with you.", "The coordinator keeps them.", "They go into the common pot."),
                0,
            ),
        ]
    else:
        qs.append(Question(
            "rules",
            "Who sets rules such as a fishing limit or a tax in your group?",
            ("Nobody; there are no such rules in your group.",
             "One of the islanders, chosen at random.",
             "The computer."),
            0,
        ))
    return qs


def public_quiz(questions: list[Question]) -> list[dict[str, Any]]:
    return [q.public() for q in questions]


def grade_quiz(questions: list[Question], answers: Any) -> tuple[bool, list[str], dict[str, int | None]]:
    """-> (passed, ids answered wrongly, cleaned answers). Passing needs every answer right."""
    if not isinstance(answers, dict):
        raise ValueError("answers must be a mapping")
    cleaned: dict[str, int | None] = {}
    wrong: list[str] = []
    for q in questions:
        v = answers.get(q.id)
        try:
            v = int(v) if v is not None and not isinstance(v, bool) else None
        except (TypeError, ValueError):
            v = None
        if v is not None and not 0 <= v < len(q.options):
            v = None
        cleaned[q.id] = v
        if v != q.answer:
            wrong.append(q.id)
    return not wrong, wrong, cleaned


# ---------------------------------------------------------------------- questionnaire

LIKERT_ANCHORS = ("Strongly disagree", "Strongly agree")
GENDER_OPTIONS = ("Woman", "Man", "Non-binary", "Another gender", "Prefer not to say")


@dataclass(frozen=True)
class Item:
    id: str
    kind: str                          # likert7 | choice | number | text
    text: str
    section: str
    required: bool = True
    options: tuple[str, ...] = ()
    min: int | None = None
    max: int | None = None
    max_chars: int = 1000
    anchors: tuple[str, str] = field(default=LIKERT_ANCHORS)

    def public(self) -> dict[str, Any]:
        d: dict[str, Any] = {"id": self.id, "kind": self.kind, "text": self.text, "section": self.section,
                             "required": self.required}
        if self.kind == "likert7":
            d["anchors"] = list(self.anchors)
        if self.kind == "choice":
            d["options"] = list(self.options)
        if self.kind == "number":
            d["min"], d["max"] = self.min, self.max
        if self.kind == "text":
            d["max_chars"] = self.max_chars
        return d


def questionnaire_items(condition: str, role: str) -> list[Item]:
    """Post-game questionnaire: trust in the coordinator, fairness, demographics (section 10)."""
    items: list[Item] = []
    if role == "coordinator":
        s = "Your role as coordinator"
        items += [
            Item("coord_fair", "likert7", "The rules I set were fair to all islanders.", s),
            Item("coord_group_interest", "likert7", "I acted in the interest of the whole group.", s),
            Item("coord_offers_influence", "likert7", "Offers from islanders influenced the rules I set.", s),
            Item("coord_strategy", "text", "In a few words: how did you decide on the rules? (optional)", s, required=False),
        ]
    else:
        if condition == "human":
            s = "The coordinator"
            items += [
                Item("trust_coord", "likert7", "I trusted the coordinator to act in the interest of the group.", s),
                Item("coord_fair", "likert7", "The coordinator's rules were fair.", s),
                Item("coord_equal", "likert7", "The coordinator treated all islanders equally.", s),
                Item("coord_competent", "likert7", "The coordinator made good decisions for the group.", s),
            ]
        s = "Your group"
        items += [
            Item("outcome_fair", "likert7", "The way coins ended up divided in my group was fair.", s),
            Item("others_cooperated", "likert7", "The other islanders cooperated.", s),
            Item("trust_others", "likert7", "I trusted the other islanders.", s),
            Item("strategy", "text", "In a few words: how did you decide how to use your effort points? (optional)", s,
                 required=False),
        ]
    s = "About you"
    items += [
        Item("age", "number", "How old are you? (Leave empty if you prefer not to say.)", s, required=False,
             min=18, max=100),
        Item("gender", "choice", "What is your gender?", s, options=GENDER_OPTIONS),
        Item("comments", "text", "Anything else you would like to tell us about the study? (optional)", s,
             required=False),
    ]
    return items


def clean_questionnaire(items: list[Item], answers: Any) -> dict[str, Any]:
    """Validate answers against the item definitions. Raises ValueError with a participant-facing message."""
    if not isinstance(answers, dict):
        raise ValueError("answers must be a mapping")
    out: dict[str, Any] = {}
    for it in items:
        v = answers.get(it.id)
        if v is None or (isinstance(v, str) and not v.strip()):
            if it.required:
                raise ValueError("please answer every question that is not marked optional")
            out[it.id] = None
            continue
        if it.kind == "likert7":
            if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v or not 1 <= v <= 7:
                raise ValueError("ratings must be between 1 and 7")
            out[it.id] = int(v)
        elif it.kind == "choice":
            if v not in it.options:
                raise ValueError("invalid choice")
            out[it.id] = v
        elif it.kind == "number":
            try:
                n = int(str(v).strip())
            except ValueError:
                raise ValueError(f"please enter a whole number for: {it.text}") from None
            if (it.min is not None and n < it.min) or (it.max is not None and n > it.max):
                raise ValueError(f"please enter a number between {it.min} and {it.max}")
            out[it.id] = n
        else:   # text: stored as plain text (control characters removed), trimmed and capped
            if not isinstance(v, str):
                raise ValueError("invalid answer")
            text = _CONTROL.sub("", v.replace("\r\n", "\n")).strip()[: it.max_chars]
            out[it.id] = text or None
    return out


# ---------------------------------------------------------------------- completion

def completion_codes(cfg: Config, session_settings: dict[str, Any] | None) -> dict[str, str]:
    """Config defaults overridden by the session's own codes (set in the dashboard)."""
    codes = dict(cfg.completion_codes)
    for k, v in ((session_settings or {}).get("completion_codes") or {}).items():
        if v:
            codes[k] = str(v)
    return codes


def completion_info(cfg: Config, session_settings: dict[str, Any] | None, outcome: str) -> dict[str, Any]:
    code = completion_codes(cfg, session_settings).get(outcome, "")
    return {"outcome": outcome, "code": code or None,
            "url": cfg.completion_url.replace("{code}", code) if code else None}
