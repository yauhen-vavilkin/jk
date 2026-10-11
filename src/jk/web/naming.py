"""One name, one thing.

Two flows on the board, or two saved flows, never share a name: the user would
have no way to tell them apart. Where the user types the name, a taken one is
refused and they choose another. Where the panel picks the name itself -- a
duplicate, or a saved flow dropped on the board a second time -- it takes the
next free one instead of asking.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from itertools import chain, count

#: `copy`, `copy 2`, `copy 3`: what the panel adds to a name that is taken.
COPY = "copy"
_TAIL = re.compile(rf"\s+{COPY}(\s+\d+)?$", re.IGNORECASE)


def tidy(name: str) -> str:
    """The name as it is stored: what the user typed, without the edges."""
    return name.strip()


def is_taken(wanted: str, taken: Iterable[str]) -> bool:
    """Case does not make two names different, and neither does a stray space."""
    folded = tidy(wanted).casefold()
    return any(tidy(other).casefold() == folded for other in taken)


def copy_name(original: str, taken: Iterable[str]) -> str:
    """What a copy of `original` is called: `X copy`, then `X copy 2`, `X copy 3`.

    The copy tail is stripped first, so a copy of `X copy` is `X copy 2` and
    never `X copy copy`.
    """
    return free_name(f"{_base(original)} {COPY}", taken)


def _base(name: str) -> str:
    """`X copy 3` -> `X`; anything without a copy tail is itself."""
    return tidy(_TAIL.sub("", tidy(name))) or tidy(name)


def free_name(wanted: str, taken: Iterable[str]) -> str:
    """`wanted` when it is free; otherwise `X copy`, then `X copy 2`, `X copy 3`."""
    names = list(taken)
    wanted = tidy(wanted)
    if not is_taken(wanted, names):
        return wanted
    base = _base(wanted)
    # chain, not a tuple: unpacking an endless count into one would never finish.
    attempts = chain([f"{base} {COPY}"], (f"{base} {COPY} {n}" for n in count(2)))
    return next(attempt for attempt in attempts if not is_taken(attempt, names))
