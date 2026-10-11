"""The error types every JK layer raises.

The TYPE carries the meaning, so the interface can choose a clear message and a
useful next action. The message carries detail, but never a raw Jenkins response
body: a response may echo content JK did not choose to send.
"""

from __future__ import annotations


class JKError(Exception):
    """Base class for every error JK raises deliberately."""


class StateAccessError(JKError):
    """JK cannot keep its local state accessible only to its owner."""


class JenkinsAuthError(JKError):
    """Jenkins rejected the credentials or the user lacks permission."""


class JenkinsUnavailable(JKError):
    """A connection or protocol failure while talking to Jenkins.

    Safe to retry for monitoring (GET only). NEVER safe to retry for submission.
    """


class SubmissionRejected(JKError):
    """Jenkins clearly refused the submission. No build was created."""


class SubmissionPreflightFailed(JKError):
    """A read failed before JK claimed or sent the step; a review can resume it."""


class AmbiguousSubmission(JKError):
    """The submission result is unknown.

    JK does not know whether Jenkins accepted the request. The run becomes
    NEEDS_ATTENTION and is never re-sent.
    """


class TargetNotFound(JKError):
    """A queue item or build JK was following can no longer be found."""
