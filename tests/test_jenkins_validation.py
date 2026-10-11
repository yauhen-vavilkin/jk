from __future__ import annotations

from jk.jenkins.models import ParameterDefinition


def definition(name: str, type_name: str) -> ParameterDefinition:
    return ParameterDefinition(name, type_name, None)


def test_security_properties_require_exact_parameter_types() -> None:
    assert definition("PASSWORD", "PasswordParameterDefinition").is_secret
    assert not definition("NOT_PASSWORD", "NotPasswordParameterDefinition").is_secret
    assert definition("CASCADE", "CascadeChoiceParameter").is_cascade
    assert not definition("DYNAMIC", "DynamicReferenceParameter").is_cascade
