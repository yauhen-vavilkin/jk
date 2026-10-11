"""The one error shape the API answers with.

The message is the sentence the interface shows, word for word. A raw Jenkins
response body never reaches it: a response may echo content JK did not send.
"""

from __future__ import annotations

from fastapi import HTTPException

PRESET_DRIFTED = "This saved job changed in Jenkins. Repair it in Library first."
PASSWORD_EMPTY = "A password parameter has no value."
NAME_EMPTY = "A flow needs a name."
FLOW_RUNNING = "This flow is running; only planned steps can be changed."
JENKINS_UNREACHABLE = "Jenkins could not be reached."
JENKINS_AUTH = "Jenkins rejected the API token."
JOB_REFUSED = "Jenkins refused this user access to this job."


class ApiError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(status_code=status_code, detail={"code": code, "message": message})
        self.code = code
        self.message = message


def not_found(what: str) -> ApiError:
    return ApiError(404, "not_found", f"JK has no {what}.")


def param_not_defined(name: str) -> ApiError:
    return ApiError(400, "param_not_defined", f"Jenkins does not define a parameter named {name}.")


def password_empty() -> ApiError:
    return ApiError(400, "password_empty", PASSWORD_EMPTY)


def name_empty() -> ApiError:
    return ApiError(400, "name_empty", NAME_EMPTY)


def placeholder_value(name: str) -> ApiError:
    return ApiError(
        400,
        "placeholder_value",
        f"{name} still holds Jenkins' error placeholder. Choose its value.",
    )


def preset_drifted() -> ApiError:
    return ApiError(409, "preset_drifted", PRESET_DRIFTED)


FLOW_SENDING = "A step of this flow is being sent to Jenkins right now. Try again in a moment."


def flow_sending() -> ApiError:
    return ApiError(409, "flow_sending", FLOW_SENDING)


def review_refused(message: str) -> ApiError:
    return ApiError(409, "review_required", message)


def flow_running() -> ApiError:
    return ApiError(409, "flow_running", FLOW_RUNNING)


def conflict(code: str, message: str) -> ApiError:
    return ApiError(409, code, message)
