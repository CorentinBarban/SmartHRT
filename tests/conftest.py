"""Fixtures et configuration pour les tests SmartHRT.

Ce module fournit les fixtures communes pour tous les tests,
notamment le mock du coordinateur et les helpers pour simuler
les différents états de la machine à états.
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, time as dt_time, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

import pytest

from custom_components.SmartHRT.const import (
    DEFAULT_RCTH,
    DEFAULT_RPTH,
    DEFAULT_RELAXATION_FACTOR,
    DEFAULT_TSP,
    DOMAIN,
)
from custom_components.SmartHRT.coordinator import (
    SmartHRTCoordinator,
    SmartHRTState,
)
from custom_components.SmartHRT.data_model import SmartHRTData  # ADR-047


@dataclass
class MockConfigEntry:
    """Mock de ConfigEntry Home Assistant."""

    entry_id: str = "test_entry_123"
    data: dict = field(
        default_factory=lambda: {
            "name": "Test SmartHRT",
            "tsp": DEFAULT_TSP,
            "target_hour": "06:00:00",
            "recoverycalc_hour": "23:00:00",
            "sensor_interior_temperature": "sensor.interior_temp",
            "weather_entity": "weather.home",
        }
    )


class MockStore:
    """Mock du Store Home Assistant pour la persistance."""

    def __init__(self):
        self._data: dict | None = None

    async def async_load(self) -> dict | None:
        return self._data

    async def async_save(self, data: dict) -> None:
        self._data = data


class MockUnits:
    """Mock pour hass.config.units."""

    def __init__(self, temperature_unit: str = "°C"):
        from homeassistant.const import UnitOfTemperature

        self.temperature_unit = temperature_unit


class MockConfig:
    """Mock pour hass.config."""

    def __init__(self):
        from homeassistant.const import UnitOfTemperature

        self.units = MockUnits(UnitOfTemperature.CELSIUS)


class MockHass:
    """Mock simplifié de Home Assistant."""

    def __init__(self):
        self.states = MockStates()
        self.services = MockServices()
        self.config = MockConfig()  # ADR-054: Ajout pour détecter l'unité système
        self._listeners = []
        self._scheduled_callbacks = []
        self._time_trackers = []
        # Ajouter un loop pour les trackers Home Assistant
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
        # ADR-027: Attribut requis par DataUpdateCoordinator pour la validation thread-safe
        import threading

        self.loop_thread_id = threading.get_ident()

    async def async_add_executor_job(self, func, *args, **kwargs):
        """Exécute une fonction de manière synchrone pour les tests."""
        return func(*args, **kwargs)

    def async_create_task(self, coro):
        """Crée une tâche asynchrone."""
        if asyncio.iscoroutine(coro):
            # Pour les tests, on peut ignorer ou forcer l'exécution
            pass
        return MagicMock()


class MockStates:
    """Mock pour hass.states."""

    def __init__(self):
        self._states: dict[str, MockState] = {}

    def get(self, entity_id: str):
        return self._states.get(entity_id)

    def set(self, entity_id: str, state: str, attributes: dict | None = None):
        self._states[entity_id] = MockState(state, attributes or {})


@dataclass
class MockState:
    """Mock d'un état Home Assistant."""

    state: str
    attributes: dict = field(default_factory=dict)

    @property
    def entity_id(self) -> str:
        return self.attributes.get("entity_id", "unknown")


class MockServices:
    """Mock pour hass.services."""

    def has_service(self, domain: str, service: str) -> bool:
        return True

    async def async_call(self, domain, service, **kwargs) -> dict:
        return {}


@pytest.fixture
def mock_hass() -> MockHass:
    """Fixture pour le mock de Home Assistant."""
    hass = MockHass()
    # Configurer les états par défaut
    hass.states.set("sensor.interior_temp", "18.5")
    hass.states.set(
        "weather.home",
        "sunny",
        {
            "temperature": 5.0,
            "wind_speed": 15.0,
        },
    )
    return hass


@pytest.fixture
def mock_entry() -> MockConfigEntry:
    """Fixture pour le mock de ConfigEntry."""
    return MockConfigEntry()


@pytest.fixture
def mock_store() -> MockStore:
    """Fixture pour le mock du Store."""
    return MockStore()


@pytest.fixture
def coordinator_data() -> SmartHRTData:
    """Fixture pour les données initiales du coordinator."""
    return SmartHRTData(
        name="Test SmartHRT",
        tsp=DEFAULT_TSP,
        target_hour=dt_time(6, 0, 0),
        recoverycalc_hour=dt_time(23, 0, 0),
        current_state=SmartHRTState.HEATING_ON,
        smartheating_mode=True,
        recovery_adaptive_mode=True,
        rcth=DEFAULT_RCTH,
        rpth=DEFAULT_RPTH,
        rcth_lw=DEFAULT_RCTH,
        rcth_hw=DEFAULT_RCTH,
        rpth_lw=DEFAULT_RPTH,
        rpth_hw=DEFAULT_RPTH,
        relaxation_factor=DEFAULT_RELAXATION_FACTOR,
        interior_temp=18.5,
        exterior_temp=5.0,
        wind_speed=4.0,  # m/s
    )


@pytest.fixture
def mock_now():
    """Fixture pour mocker dt_util.now()."""

    def _mock_now(year=2026, month=2, day=3, hour=10, minute=0, second=0):
        from homeassistant.util import dt as dt_util

        return datetime(year, month, day, hour, minute, second, tzinfo=dt_util.UTC)

    return _mock_now


@pytest.fixture
def create_coordinator(mock_hass, mock_entry, mock_store):
    """Factory fixture pour créer un coordinator configuré."""

    # ADR-040: Flags calculés depuis current_state - mapping pour tests legacy
    FLAG_TO_STATE = {
        "recovery_calc_mode": SmartHRTState.MONITORING,
        "rp_calc_mode": SmartHRTState.HEATING_PROCESS,
        "temp_lag_detection_active": SmartHRTState.DETECTING_LAG,
    }

    async def _create_coordinator(
        initial_state: str = SmartHRTState.HEATING_ON, **data_overrides
    ) -> SmartHRTCoordinator:
        # Configurer le frame helper pour DataUpdateCoordinator (ADR-027)
        from homeassistant.helpers import frame as frame_helper

        frame_helper._hass.hass = mock_hass

        with (
            patch(
                "custom_components.SmartHRT.coordinator.Store", return_value=mock_store
            ),
            patch(
                "custom_components.SmartHRT.coordinator.async_track_time_interval",
                return_value=lambda: None,
            ),
            patch(
                "custom_components.SmartHRT.coordinator.async_track_state_change_event",
                return_value=lambda: None,
            ),
            patch(
                "custom_components.SmartHRT.coordinator.async_track_point_in_time",
                return_value=lambda: None,
            ),
        ):
            coordinator = SmartHRTCoordinator(mock_hass, mock_entry)
            coordinator._store = mock_store

            # ADR-040: Si un flag est dans data_overrides avec True, ajuster initial_state
            for flag_name, target_state in FLAG_TO_STATE.items():
                if data_overrides.get(flag_name) is True:
                    initial_state = target_state
                    break

            # Configurer les données initiales
            coordinator.data.current_state = initial_state
            coordinator._state_machine.force_state(initial_state, run_callbacks=False)
            coordinator.data.interior_temp = 18.5
            coordinator.data.exterior_temp = 5.0
            coordinator.data.wind_speed = 4.0

            # Appliquer les overrides (sauf flags - ADR-040: calculés depuis state)
            computed_flags = {
                "recovery_calc_mode",
                "rp_calc_mode",
                "temp_lag_detection_active",
            }
            # Support pour data_overrides={...} comme paramètre nommé (legacy pattern)
            if "data_overrides" in data_overrides:
                nested_overrides = data_overrides.pop("data_overrides")
                data_overrides.update(nested_overrides)

            for key, value in data_overrides.items():
                if key not in computed_flags:
                    setattr(coordinator.data, key, value)

            return coordinator

    return _create_coordinator


def make_datetime(
    hour: int,
    minute: int = 0,
    second: int = 0,
    day: int = 3,
    month: int = 2,
    year: int = 2026,
) -> datetime:
    """Helper pour créer des datetime pour les tests."""
    from homeassistant.util import dt as dt_util

    return datetime(year, month, day, hour, minute, second, tzinfo=dt_util.UTC)
