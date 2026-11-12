"""Tables for the Island Economy experiment.

`event_log` is the source of truth: an append-only, timestamped record of
everything that happens, keyed by session, group, round and participant.
The other tables hold identities and configuration. Analysis tables
(decisions, policies, messages, ...) are derived from the log at export time.
"""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, String, Text

from .database import Base, JSONType


def utcnow():
    return datetime.now(timezone.utc)


class ExperimentSession(Base):
    __tablename__ = "ie_sessions"

    id = Column(String(32), primary_key=True)                 # session code shared in the study link
    label = Column(String(200), default="")
    created_at = Column(DateTime(timezone=True), default=utcnow)
    status = Column(String(20), default="open")               # open | closed
    assignments = Column(JSONType, nullable=False)            # planned groups: [{condition, seed}, ...]
    params_path = Column(Text, default="")
    params_sha256 = Column(String(64), nullable=False)
    params_snapshot = Column(JSONType, nullable=False)        # full parameter snapshot
    code_version = Column(String(80), default="")
    settings = Column(JSONType, nullable=True)                # e.g. {"completion_codes": {outcome: code}}


class Participant(Base):
    """Pseudonymous participant. Never stores the Prolific ID (see ExternalIdentity)."""

    __tablename__ = "ie_participants"

    id = Column(String(32), primary_key=True)                 # e.g. "p_3f9a..." (random)
    session_id = Column(String(32), ForeignKey("ie_sessions.id"), index=True, nullable=False)
    role = Column(String(20), nullable=True)                  # player | coordinator (set when allocated)
    condition = Column(String(20), nullable=True)             # none | human (set when allocated)
    # joined -> consented -> quiz_passed -> practice -> practice_done -> waiting -> playing -> finished
    # -> completed; exits: no_consent | quiz_failed | no_group | aborted
    status = Column(String(30), default="joined")
    group_id = Column(String(40), nullable=True, index=True)
    seat = Column(Integer, nullable=True)
    quiz_attempts = Column(Integer, default=0)
    bonus = Column(Float, nullable=True)                      # game bonus in currency units (set when the game ends)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class ParticipantToken(Base):
    """Access tokens (stored hashed). Re-joining adds a token; earlier ones stay valid."""

    __tablename__ = "ie_participant_tokens"

    token_hash = Column(String(64), primary_key=True)
    participant_id = Column(String(32), ForeignKey("ie_participants.id"), index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)


class ExternalIdentity(Base):
    """Mapping to recruitment-platform IDs, kept apart from all game data."""

    __tablename__ = "ie_external_ids"

    id = Column(Integer, primary_key=True, autoincrement=True)
    participant_id = Column(String(32), ForeignKey("ie_participants.id"), index=True, nullable=False)
    session_id = Column(String(32), index=True, nullable=False)
    provider = Column(String(20), default="prolific")
    external_id = Column(String(100), nullable=False)
    study_id = Column(String(100), default="")
    external_session_id = Column(String(100), default="")
    created_at = Column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("ix_ext_session_external", "session_id", "provider", "external_id", unique=True),)


class Group(Base):
    __tablename__ = "ie_groups"

    id = Column(String(40), primary_key=True)
    session_id = Column(String(32), ForeignKey("ie_sessions.id"), index=True, nullable=False)
    index_in_session = Column(Integer, nullable=False)
    condition = Column(String(20), nullable=False)            # none | human
    seed = Column(BigInteger, nullable=False)
    n_rounds = Column(Integer, nullable=False)                # never shown to participants
    status = Column(String(20), default="running")            # running | finished | aborted
    flagged = Column(Boolean, default=False)
    flags = Column(JSONType, default=list)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    finished_at = Column(DateTime(timezone=True), nullable=True)


class EventLog(Base):
    """Append-only event log. Rows are only ever inserted."""

    __tablename__ = "ie_event_log"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    ts = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    session_id = Column(String(32), nullable=False)
    group_id = Column(String(40), nullable=True)
    round = Column(Integer, nullable=True)
    participant_id = Column(String(32), nullable=True)
    kind = Column(String(40), nullable=False)
    payload = Column(JSONType, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_event_log_group", "session_id", "group_id", "round"),
        Index("ix_event_log_kind", "kind"),
    )
