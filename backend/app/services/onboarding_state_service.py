from __future__ import annotations

REGISTERED = "REGISTERED"
PREFERENCES_SET = "PREFERENCES_SET"
DISCOVERY_STARTED = "DISCOVERY_STARTED"
COMPLETED = "COMPLETED"

VALID_ONBOARDING_STATES = {
    REGISTERED,
    PREFERENCES_SET,
    DISCOVERY_STARTED,
    COMPLETED,
}

_STATE_ORDER: dict[str, int] = {
    REGISTERED: 0,
    PREFERENCES_SET: 1,
    DISCOVERY_STARTED: 2,
    COMPLETED: 3,
}

_ALLOWED_TRANSITIONS: dict[str, str] = {
    REGISTERED: PREFERENCES_SET,
    PREFERENCES_SET: DISCOVERY_STARTED,
    DISCOVERY_STARTED: COMPLETED,
}


def assert_canonical_onboarding_step(step: str) -> None:
    assert step in VALID_ONBOARDING_STATES, f"Invalid canonical onboarding step: {step}"


def validate_onboarding_state(state: str | None) -> str:
    if state not in VALID_ONBOARDING_STATES:
        raise ValueError("Invalid onboarding state")
    return str(state)


def advance_onboarding_state(current_state: str | None, target_state: str) -> str:
    """
    Validate and return the next onboarding state.

    Allowed transitions:
    REGISTERED -> PREFERENCES_SET
    PREFERENCES_SET -> DISCOVERY_STARTED
    DISCOVERY_STARTED -> COMPLETED
    """
    current = validate_onboarding_state(current_state)
    target = validate_onboarding_state(target_state)
    assert_canonical_onboarding_step(current)
    assert_canonical_onboarding_step(target)
    allowed_next = _ALLOWED_TRANSITIONS.get(current)
    if allowed_next != target:
        raise ValueError("Invalid onboarding transition")
    return target


def is_state_at_least(current_state: str | None, target_state: str) -> bool:
    current = validate_onboarding_state(current_state)
    target = validate_onboarding_state(target_state)
    return _STATE_ORDER[current] >= _STATE_ORDER[target]

