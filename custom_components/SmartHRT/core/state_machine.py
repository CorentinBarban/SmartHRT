"""Pure Python state machine for SmartHRT.

Implements:
- ADR-033: Decoupled state transition logic
- ADR-034: Centralized side effects via Actions
- ADR-035: Atomic transitions with validation
- ADR-046: Declarative transition-to-actions mapping
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Callable, Protocol

from .types import Action, StateTransitionResult


class LoggerProtocol(Protocol):
    """Protocol for logger compatibility (stdlib or custom)."""

    def debug(self, msg: str, *args: object, **kwargs: object) -> None: ...
    def info(self, msg: str, *args: object, **kwargs: object) -> None: ...
    def warning(self, msg: str, *args: object, **kwargs: object) -> None: ...


class SmartHRTState(StrEnum):
    """SmartHRT state machine states.

    ADR-049: Added INITIALIZING as entry point after (re)start.

    Lifecycle:
    INITIALIZING -> any state (restoration)
    HEATING_ON -> DETECTING_LAG -> MONITORING -> RECOVERY -> HEATING_PROCESS -> HEATING_ON
    """

    INITIALIZING = "initializing"  # ADR-049: État initial après (re)démarrage
    HEATING_ON = "heating_on"
    DETECTING_LAG = "detecting_lag"
    MONITORING = "monitoring"
    RECOVERY = "recovery"
    HEATING_PROCESS = "heating_process"


# State flags: maps state -> (recovery_calc_mode, rp_calc_mode, temp_lag_detection_active)
STATE_FLAGS: dict[SmartHRTState, tuple[bool, bool, bool]] = {
    SmartHRTState.INITIALIZING: (False, False, False),  # ADR-049
    SmartHRTState.HEATING_ON: (False, False, False),
    SmartHRTState.DETECTING_LAG: (False, False, True),
    SmartHRTState.MONITORING: (True, False, False),
    SmartHRTState.RECOVERY: (False, True, False),
    SmartHRTState.HEATING_PROCESS: (False, True, False),
}

# ADR-049: INITIALIZING peut transitionner vers n'importe quel état (restauration)
VALID_TRANSITIONS: dict[SmartHRTState, set[SmartHRTState]] = {
    SmartHRTState.INITIALIZING: {
        SmartHRTState.HEATING_ON,
        SmartHRTState.DETECTING_LAG,
        SmartHRTState.MONITORING,
        SmartHRTState.RECOVERY,
        SmartHRTState.HEATING_PROCESS,
    },
    SmartHRTState.HEATING_ON: {SmartHRTState.DETECTING_LAG},
    SmartHRTState.DETECTING_LAG: {SmartHRTState.MONITORING},
    SmartHRTState.MONITORING: {
        SmartHRTState.RECOVERY,
        SmartHRTState.HEATING_PROCESS,
        SmartHRTState.HEATING_ON,  # ADR-055: Cas "pas de relance nécessaire"
    },
    SmartHRTState.RECOVERY: {SmartHRTState.HEATING_PROCESS},
    SmartHRTState.HEATING_PROCESS: {SmartHRTState.HEATING_ON},
}

# ADR-046: Mapping déclaratif transition → actions
# ADR-049: Transitions depuis INITIALIZING pour restauration avec effets de bord
# Ordre recommandé: Snapshots, Annulation timers, Calculs, Planification, Sauvegarde
TRANSITION_ACTIONS: dict[tuple[SmartHRTState, SmartHRTState], list[Action]] = {
    # ADR-049: Transitions depuis INITIALIZING (restauration après redémarrage)
    # Ces transitions reprogramment les timers nécessaires
    (SmartHRTState.INITIALIZING, SmartHRTState.HEATING_ON): [],
    (SmartHRTState.INITIALIZING, SmartHRTState.DETECTING_LAG): [],
    (SmartHRTState.INITIALIZING, SmartHRTState.MONITORING): [
        Action.SCHEDULE_RECOVERY_UPDATE,
    ],
    (SmartHRTState.INITIALIZING, SmartHRTState.RECOVERY): [
        Action.SCHEDULE_RECOVERY_UPDATE,
    ],
    (SmartHRTState.INITIALIZING, SmartHRTState.HEATING_PROCESS): [],
    # HEATING_ON → DETECTING_LAG: Démarrage du cycle, pas d'action spécifique
    (SmartHRTState.HEATING_ON, SmartHRTState.DETECTING_LAG): [],
    # DETECTING_LAG → MONITORING: Planifier la mise à jour recovery
    (SmartHRTState.DETECTING_LAG, SmartHRTState.MONITORING): [
        Action.SCHEDULE_RECOVERY_UPDATE,
        Action.SAVE_DATA,
    ],
    # MONITORING → RECOVERY: Démarrage de la relance
    (SmartHRTState.MONITORING, SmartHRTState.RECOVERY): [
        Action.CANCEL_RECOVERY_TIMER,
        Action.SNAPSHOT_RECOVERY_START,
        Action.CALCULATE_RCTH,
        Action.SAVE_DATA,
    ],
    # MONITORING → HEATING_PROCESS: Cas où target atteinte sans recovery
    (SmartHRTState.MONITORING, SmartHRTState.HEATING_PROCESS): [],
    # MONITORING → HEATING_ON: Cas "pas de relance nécessaire" (ADR-055)
    # La température n'est jamais descendue sous la cible durant la nuit
    (SmartHRTState.MONITORING, SmartHRTState.HEATING_ON): [
        Action.CANCEL_RECOVERY_TIMER,
        Action.SAVE_DATA,
    ],
    # RECOVERY → HEATING_PROCESS: Transition naturelle
    (SmartHRTState.RECOVERY, SmartHRTState.HEATING_PROCESS): [],
    # HEATING_PROCESS → HEATING_ON: Fin du cycle, calcul RPth
    (SmartHRTState.HEATING_PROCESS, SmartHRTState.HEATING_ON): [
        Action.SNAPSHOT_RECOVERY_END,
        Action.CALCULATE_RPTH,
        Action.SAVE_DATA,
    ],
}

StateTransitionCallback = Callable[[SmartHRTState, SmartHRTState], None]

_LOGGER = logging.getLogger(__name__)


def get_state_flags(state: SmartHRTState) -> dict[str, bool]:
    """Return mode flags for a given state (ADR-035: coherent state)."""
    flags = STATE_FLAGS.get(state, (False, False, False))
    return {
        "recovery_calc_mode": flags[0],
        "rp_calc_mode": flags[1],
        "temp_lag_detection_active": flags[2],
    }


class SmartHRTStateMachine:
    """Pure Python state machine without Home Assistant dependencies.

    ADR-033: Decoupled from HA, testable in isolation.
    ADR-034: Returns actions for side effects.
    ADR-035: Validates transitions atomically.
    """

    def __init__(
        self,
        initial_state: SmartHRTState = SmartHRTState.HEATING_ON,
        valid_transitions: dict[SmartHRTState, set[SmartHRTState]] | None = None,
        transition_actions: (
            dict[tuple[SmartHRTState, SmartHRTState], list[Action]] | None
        ) = None,
        logger: LoggerProtocol | None = None,
        log_prefix: str = "",
    ) -> None:
        self._state = initial_state
        self._valid_transitions = valid_transitions or VALID_TRANSITIONS
        self._transition_actions = transition_actions or {}
        self._on_enter_callbacks: dict[SmartHRTState, list[StateTransitionCallback]] = (
            {}
        )
        self._on_exit_callbacks: dict[SmartHRTState, list[StateTransitionCallback]] = {}
        self._logger = logger or _LOGGER
        self._log_prefix = log_prefix

    @property
    def state(self) -> SmartHRTState:
        return self._state

    def _log(self, level: str, msg: str, *args: object) -> None:
        """Log with prefix."""
        prefixed = f"{self._log_prefix} {msg}" if self._log_prefix else msg
        getattr(self._logger, level)(prefixed, *args)

    def can_transition(
        self, current_state: SmartHRTState, new_state: SmartHRTState
    ) -> bool:
        """Check if transition is valid without performing it."""
        return new_state in self._valid_transitions.get(current_state, set())

    def valid_targets(
        self, from_state: SmartHRTState | None = None
    ) -> set[SmartHRTState]:
        """Return valid target states from current or specified state."""
        source = from_state if from_state is not None else self._state
        return self._valid_transitions.get(source, set())

    def actions_for_transition(
        self, old_state: SmartHRTState, new_state: SmartHRTState
    ) -> list[Action]:
        """Return actions configured for a transition."""
        return list(self._transition_actions.get((old_state, new_state), []))

    def on_enter(self, state: SmartHRTState, callback: StateTransitionCallback) -> None:
        """Register callback for entering a state."""
        self._on_enter_callbacks.setdefault(state, []).append(callback)

    def on_exit(self, state: SmartHRTState, callback: StateTransitionCallback) -> None:
        """Register callback for exiting a state."""
        self._on_exit_callbacks.setdefault(state, []).append(callback)

    def transition_to(self, new_state: SmartHRTState) -> bool:
        """Perform a validated transition to a new state.

        Returns True if transition succeeded, False otherwise.
        """
        if new_state == self._state:
            self._log("debug", "No-op transition: already in %s", new_state.value)
            return False

        if not self.can_transition(self._state, new_state):
            valid = self.valid_targets()
            self._log(
                "warning",
                "Invalid transition %s → %s (valid: %s)",
                self._state.value,
                new_state.value,
                ", ".join(s.value for s in valid) if valid else "none",
            )
            return False

        old_state = self._state

        # Execute exit callbacks
        for callback in self._on_exit_callbacks.get(old_state, []):
            try:
                callback(old_state, new_state)
            except Exception as e:
                self._log("warning", "Exit callback error: %s", e)

        self._state = new_state

        # Execute enter callbacks
        for callback in self._on_enter_callbacks.get(new_state, []):
            try:
                callback(old_state, new_state)
            except Exception as e:
                self._log("warning", "Enter callback error: %s", e)

        self._log("info", "Transition %s → %s", old_state.value, new_state.value)
        return True

    def transition_with_actions(
        self, new_state: SmartHRTState
    ) -> StateTransitionResult:
        """Perform a transition and return emitted actions (ADR-034)."""
        old_state = self._state
        success = self.transition_to(new_state)
        actions: list[Action] = []

        if success:
            actions = self.actions_for_transition(old_state, new_state)
            if actions:
                self._log("debug", "Actions emitted: %s", [a.value for a in actions])

        return StateTransitionResult(
            success=success,
            old_state=old_state,
            new_state=self._state,
            actions=actions,
        )

    def _force_state_unsafe(
        self, new_state: SmartHRTState, run_callbacks: bool = False
    ) -> None:
        """Force a state change without validating transitions.

        ADR-049: Renamed from force_state to discourage direct use.

        ⛔ USAGE INTERDIT sauf pour les tests unitaires.
        Pour la restauration d'état, utiliser transition_to depuis
        INITIALIZING qui garantit l'exécution des callbacks appropriés.
        """
        if new_state == self._state:
            return

        old_state = self._state
        self._state = new_state

        if run_callbacks:
            for callback in self._on_exit_callbacks.get(old_state, []):
                try:
                    callback(old_state, new_state)
                except Exception as e:
                    self._log("warning", "Exit callback error during force: %s", e)
            for callback in self._on_enter_callbacks.get(new_state, []):
                try:
                    callback(old_state, new_state)
                except Exception as e:
                    self._log("warning", "Enter callback error during force: %s", e)

        self._log("info", "State forced %s → %s", old_state.value, new_state.value)

    # ADR-049: Alias pour compatibilité descendante (tests)
    force_state = _force_state_unsafe
