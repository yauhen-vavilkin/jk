"""Sentences the engine's state means, in the words the panel uses.

They live beside the engine, not beside a screen, so that every part of the
panel says the same thing about the same state.
"""

from __future__ import annotations

from collections.abc import Sequence

UNKNOWN_SUBMISSION_REASON = "JK will not send it again."

KEPT_LAST_KNOWN_STATE = "JK kept the last known state and will not send anything again."

#: How a step's note starts when the connection failed while JK sent it; the error follows.
CONNECTION_FAILED_WHILE_SENDING = "the connection failed while the request was being sent"

#: A step's note when JK itself stopped while it was sending the step.
JK_STOPPED_WHILE_SENDING = "JK stopped while the request was being sent."


def ended_without_link(build_numbers: Sequence[int]) -> str:
    """The note on a step the user ended without linking a build: what it matched, if anything."""
    if not build_numbers:
        return "Ended without linking a build. No build matched."
    listed = ", ".join(f"#{number}" for number in build_numbers)
    return f"Ended without linking a build. Matching builds: {listed}."
