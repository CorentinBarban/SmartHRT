"""Tests de non-régression pour le bug #3.6.

Le garde-fou contre les sauts de température implausibles (glitch
capteur/réseau) borne le TAUX de variation (°C/h) plutôt qu'un seuil
fixe en °C, avec un plancher (MIN_TEMP_JUMP_FLOOR_C) pour ne pas rejeter
à tort deux lectures très rapprochées.
"""

from datetime import timedelta

import pytest
from homeassistant.util import dt as dt_util

from custom_components.SmartHRT.const import (
    MAX_PLAUSIBLE_TEMP_RATE_C_PER_HOUR,
    MIN_TEMP_JUMP_FLOOR_C,
)


class FakeState:
    """Faux State Home Assistant minimal (entity_id, state, last_updated)."""

    def __init__(self, entity_id: str, state: str, last_updated):
        self.entity_id = entity_id
        self.state = state
        self.last_updated = last_updated


class FakeEvent:
    """Faux Event minimal exposant .data comme un dict."""

    def __init__(self, new_state):
        self.data = {"new_state": new_state}


ENTITY_ID = "sensor.interior_temp"


def _feed_temperature(coordinator, temp: float, when) -> None:
    coordinator._on_sensor_state_change(
        FakeEvent(FakeState(ENTITY_ID, str(temp), when))
    )


class TestTemperatureJumpGuard:
    """Régression #3.6: rejet des sauts implausibles basé sur le taux °C/h."""

    @pytest.mark.asyncio
    async def test_jump_within_floor_accepted_despite_tiny_elapsed_time(
        self, create_coordinator
    ):
        """Sur un intervalle très court, le plancher (pas le taux) gouverne
        et un delta <= MIN_TEMP_JUMP_FLOOR_C est accepté.

        L'intervalle est assez court pour que
        MAX_PLAUSIBLE_TEMP_RATE_C_PER_HOUR * elapsed_hours < MIN_TEMP_JUMP_FLOOR_C,
        donc max_allowed = MIN_TEMP_JUMP_FLOOR_C via le max() des deux bornes.
        """
        coordinator = await create_coordinator()
        t0 = dt_util.now()

        _feed_temperature(coordinator, 18.5, t0)
        _feed_temperature(
            coordinator,
            18.5 + MIN_TEMP_JUMP_FLOOR_C,
            t0 + timedelta(seconds=1),
        )

        assert coordinator.data.interior_temp == pytest.approx(
            18.5 + MIN_TEMP_JUMP_FLOOR_C
        )

    @pytest.mark.asyncio
    async def test_jump_beyond_floor_rejected_despite_tiny_elapsed_time(
        self, create_coordinator
    ):
        """Sur un intervalle très court, un delta > MIN_TEMP_JUMP_FLOOR_C est rejeté."""
        coordinator = await create_coordinator()
        t0 = dt_util.now()

        _feed_temperature(coordinator, 18.5, t0)
        _feed_temperature(
            coordinator,
            18.5 + MIN_TEMP_JUMP_FLOOR_C + 5.0,
            t0 + timedelta(seconds=1),
        )

        assert coordinator.data.interior_temp == pytest.approx(18.5)

    @pytest.mark.asyncio
    async def test_jump_within_plausible_rate_over_time_accepted(
        self, create_coordinator
    ):
        """Un delta cohérent avec le taux max sur l'écart de temps est accepté."""
        coordinator = await create_coordinator()
        t0 = dt_util.now()
        elapsed_hours = 2.0
        delta = MAX_PLAUSIBLE_TEMP_RATE_C_PER_HOUR * elapsed_hours - 0.1

        _feed_temperature(coordinator, 18.5, t0)
        _feed_temperature(
            coordinator, 18.5 + delta, t0 + timedelta(hours=elapsed_hours)
        )

        assert coordinator.data.interior_temp == pytest.approx(18.5 + delta)

    @pytest.mark.asyncio
    async def test_jump_exceeding_plausible_rate_over_time_rejected(
        self, create_coordinator
    ):
        """Un delta excédant le taux max sur l'écart de temps est rejeté."""
        coordinator = await create_coordinator()
        t0 = dt_util.now()
        elapsed_hours = 2.0
        delta = MAX_PLAUSIBLE_TEMP_RATE_C_PER_HOUR * elapsed_hours + 1.0

        _feed_temperature(coordinator, 18.5, t0)
        _feed_temperature(
            coordinator, 18.5 + delta, t0 + timedelta(hours=elapsed_hours)
        )

        assert coordinator.data.interior_temp == pytest.approx(18.5)
