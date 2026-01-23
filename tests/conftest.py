"""Fixtures communes pour les tests SmartHRT."""

from datetime import time as dt_time, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from collections import deque
import asyncio

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from custom_components.SmartHRT.const import (
    DOMAIN,
    CONF_NAME,
    CONF_TARGET_HOUR,
    CONF_RECOVERYCALC_HOUR,
    CONF_SENSOR_INTERIOR_TEMP,
    CONF_PHONE_ALARM,
    CONF_TSP,
    DATA_COORDINATOR,
)
from custom_components.SmartHRT.coordinator import SmartHRTCoordinator, SmartHRTData


@pytest.fixture
def mock_hass():
    """Create a mock Home Assistant instance."""
    hass = MagicMock(spec=HomeAssistant)
    hass.data = {}
    hass.states = MagicMock()
    hass.states.get = MagicMock(return_value=None)
    hass.states.async_all = MagicMock(return_value=[])
    hass.services = MagicMock()
    hass.services.has_service = MagicMock(return_value=False)
    hass.services.async_register = MagicMock()
    hass.services.async_remove = MagicMock()
    hass.services.async_call = AsyncMock(return_value={})
    hass.config_entries = MagicMock()
    hass.config_entries.async_forward_entry_setups = AsyncMock()
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
    hass.config_entries.async_reload = AsyncMock()

    # async_create_task must properly handle coroutines to avoid warnings
    def mock_create_task(coro, *args, **kwargs):
        """Close coroutine to avoid 'never awaited' warning."""
        coro.close()
        return MagicMock()

    hass.async_create_task = MagicMock(side_effect=mock_create_task)
    # Add config attribute for Store
    hass.config = MagicMock()
    hass.config.path = MagicMock(return_value="/tmp/test_storage")
    # Add loop attribute for async_track_point_in_time
    try:
        hass.loop = asyncio.get_event_loop()
    except RuntimeError:
        hass.loop = asyncio.new_event_loop()
    return hass


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    entry = MagicMock(spec=ConfigEntry)
    entry.entry_id = "test_entry_id"
    entry.data = {
        CONF_NAME: "Test SmartHRT",
        CONF_TARGET_HOUR: "06:00:00",
        CONF_RECOVERYCALC_HOUR: "23:00:00",
        CONF_SENSOR_INTERIOR_TEMP: "sensor.interior_temp",
        CONF_PHONE_ALARM: "sensor.phone_alarm",
        CONF_TSP: 19.0,
    }
    entry.options = {}
    entry.add_update_listener = MagicMock(return_value=MagicMock())
    entry.async_on_unload = MagicMock()
    return entry


@pytest.fixture
def mock_coordinator(mock_hass, mock_config_entry):
    """Create a mock coordinator."""
    with (
        patch("custom_components.SmartHRT.coordinator.async_track_state_change_event"),
        patch("custom_components.SmartHRT.coordinator.async_track_time_interval"),
        patch("custom_components.SmartHRT.coordinator.async_track_point_in_time"),
        patch("custom_components.SmartHRT.coordinator.Store") as mock_store_class,
    ):
        # Mock the Store instance
        mock_store = MagicMock()
        mock_store.async_load = AsyncMock(return_value=None)
        mock_store.async_save = AsyncMock()
        mock_store_class.return_value = mock_store

        coordinator = SmartHRTCoordinator(mock_hass, mock_config_entry)
        return coordinator


@pytest.fixture
def mock_coordinator_with_data(mock_coordinator):
    """Create a coordinator with sample data."""
    mock_coordinator.data.interior_temp = 18.5
    mock_coordinator.data.exterior_temp = 5.0
    mock_coordinator.data.wind_speed = 2.5
    mock_coordinator.data.tsp = 19.0
    mock_coordinator.data.rcth = 50.0
    mock_coordinator.data.rpth = 50.0
    mock_coordinator.data.rcth_lw = 50.0
    mock_coordinator.data.rcth_hw = 50.0
    mock_coordinator.data.rpth_lw = 50.0
    mock_coordinator.data.rpth_hw = 50.0
    mock_coordinator.data.target_hour = dt_time(6, 0, 0)
    mock_coordinator.data.recoverycalc_hour = dt_time(23, 0, 0)
    return mock_coordinator


@pytest.fixture
def sample_smarthrt_data():
    """Create sample SmartHRT data for testing."""
    return SmartHRTData(
        name="Test SmartHRT",
        tsp=19.0,
        target_hour=dt_time(6, 0, 0),
        recoverycalc_hour=dt_time(23, 0, 0),
        interior_temp=18.5,
        exterior_temp=5.0,
        wind_speed=2.5,
        rcth=50.0,
        rpth=50.0,
        rcth_lw=50.0,
        rcth_hw=50.0,
        rpth_lw=50.0,
        rpth_hw=50.0,
    )


@pytest.fixture
def mock_weather_state():
    """Create a mock weather entity state."""
    state = MagicMock()
    state.entity_id = "weather.home"
    state.state = "sunny"
    state.attributes = {
        "temperature": 5.0,
        "wind_speed": 15.0,
    }
    return state
