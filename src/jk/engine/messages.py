"""Sentences the engine's state means, in the words the panel uses.

They live beside the engine, not beside a screen, so that every part of the
panel says the same thing about the same state.
"""

from __future__ import annotations

from collections.abc import Sequence

UNKNOWN_SUBMISSION_REASON = "JK will not send it again."

KEPT_LAST_KNOWN_STATE = "JK kept the last known state and will not send anything again."

#: How a step's note starts when Jenkins took the request but made no build for it.
NEVER_STARTED = "Jenkins accepted the request but never started a build."

#: What the panel adds to that note: nothing ran, so running it again is safe.
NOTHING_RAN = (
    "Nothing ran in Jenkins. End the flow, then run it again from History if you still need it."
)


def never_started_note(next_build_number: int) -> str:
    """The note when the queue item is gone and the job's build counter did not move."""
    return (
        f"{NEVER_STARTED} The next build number is still {next_build_number}, "
        "so no build was created."
    )


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
