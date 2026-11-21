"""Module core SmartHRT : modèle thermique et machine à états, sans dépendance à Home Assistant."""

from .state_machine import (
    STATE_FLAGS,
    TRANSITION_ACTIONS,
    VALID_TRANSITIONS,
    SmartHRTState,
    SmartHRTStateMachine,
    get_state_flags,
)
from .thermal import ThermalSolver
from .types import (
    Action,
    StateTransitionResult,
    ThermalCoefficients,
    ThermalConfig,
    ThermalState,
)

__all__ = [
    "ThermalState",
    "ThermalCoefficients",
    "ThermalConfig",
    "ThermalSolver",
    "Action",
    "StateTransitionResult",
    "SmartHRTState",
    "SmartHRTStateMachine",
    "VALID_TRANSITIONS",
    "TRANSITION_ACTIONS",
    "STATE_FLAGS",
    "get_state_flags",
]
