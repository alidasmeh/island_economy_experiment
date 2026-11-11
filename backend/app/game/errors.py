"""Errors shared by the live-game modules."""


class ActionError(Exception):
    """A participant action that is not allowed right now (returned to the client, logged)."""
