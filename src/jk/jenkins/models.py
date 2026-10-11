"""Typed views over the Jenkins JSON shapes JK depends on."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def scalar_to_str(value: Any) -> str:
    """Render a Jenkins JSON scalar the way it must be sent back.

    Jenkins returns booleans as JSON booleans but only accepts the strings
    "true"/"false" in a form body, so the two directions must agree.
    """
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


# What an Active Choices script answers when it has nothing to compute from: the
# parameter is unanswered, not set to the word. See spec.md section 6.
ERROR_PLACEHOLDER = "error"

SUPPORTED_PARAMETER_TYPES = frozenset(
    {
        "StringParameterDefinition",
        "TextParameterDefinition",
        "BooleanParameterDefinition",
        "ChoiceParameterDefinition",
        "CascadeChoiceParameter",
        "PasswordParameterDefinition",
    }
)


@dataclass(frozen=True)
class ParameterDefinition:
    name: str
    type: str
    default: str | None
    choices: list[str] | None = None

    @property
    def is_cascade(self) -> bool:
        """Active Choices parameters: their default is computed without context."""
        return self.type == "CascadeChoiceParameter"

    @property
    def is_secret(self) -> bool:
        return self.type == "PasswordParameterDefinition"

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> ParameterDefinition | None:
        name = raw.get("name")
        if not name:
            return None  # unnamed DynamicReferenceParameter entries are not user inputs
        default_holder = raw.get("defaultParameterValue") or {}
        default = default_holder.get("value")
        return cls(
            name=name,
            type=raw.get("type", ""),
            default=None if default is None else scalar_to_str(default),
            choices=raw.get("choices"),
        )


@dataclass(frozen=True)
class BuildInfo:
    number: int
    queue_id: int | None
    building: bool
    result: str | None
    timestamp_ms: int
    duration_ms: int
    estimated_ms: int | None
    url: str

    @property
    def is_final(self) -> bool:
        """A build is final only when it has stopped AND reported a result.

        `building=false` with `result=null` is a transient state and must be
        polled again -- never treated as success.
        """
        return not self.building and self.result is not None

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> BuildInfo:
        return cls(
            number=int(raw["number"]),
            queue_id=raw.get("queueId"),
            building=bool(raw.get("building", False)),
            result=raw.get("result"),
            timestamp_ms=int(raw.get("timestamp", 0)),
            duration_ms=int(raw.get("duration", 0)),
            estimated_ms=raw.get("estimatedDuration"),
            url=raw.get("url", ""),
        )


@dataclass(frozen=True)
class QueueInfo:
    id: int
    cancelled: bool
    build_number: int | None
    build_url: str | None

    @classmethod
    def from_json(cls, raw: dict[str, Any]) -> QueueInfo:
        executable = raw.get("executable") or {}
        return cls(
            id=int(raw["id"]),
            cancelled=bool(raw.get("cancelled", False)),
            build_number=executable.get("number"),
            build_url=executable.get("url"),
        )
