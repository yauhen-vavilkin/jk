"""Stdlib-only pytest-process TCP boundary."""

from __future__ import annotations

import socket

OFFLINE_SUBPROCESS_PREAMBLE = """
import socket as _socket


def _reject_subprocess_connection(*args, **kwargs):
    raise RuntimeError("network access is disabled in an explicit offline subprocess")


_socket.socket.connect = _reject_subprocess_connection
_socket.socket.connect_ex = _reject_subprocess_connection
"""


def install_pytest_process_tcp_guard() -> None:
    """Block Python socket TCP connection calls for the rest of this process."""

    def reject_connection(*args: object, **kwargs: object) -> None:
        raise RuntimeError("network access is disabled in the default pytest process")

    socket.socket.connect = reject_connection
    socket.socket.connect_ex = reject_connection
