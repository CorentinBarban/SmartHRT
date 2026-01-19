"""Tests pour les sensors SmartHRT."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from homeassistant.util import dt as dt_util

from homeassistant.const import UnitOfTemperature, UnitOfSpeed, UnitOfTime
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.helpers.device_registry import DeviceEntryType

from custom_components.SmartHRT.sensor import (
    SmartHRTBaseSensor,
    SmartHRTInteriorTempSensor,
    SmartHRTExteriorTempSensor,
    SmartHRTWindSpeedSensor,
    SmartHRTWindchillSensor,
    SmartHRTRecoveryStartSensor,
    SmartHRTRCthSensor,
    SmartHRTRPthSensor,
    async_setup_entry,
)
from custom_components.SmartHRT.const import DOMAIN, DEVICE_MANUFACTURER


class TestSmartHRTBaseSensor:
    """Tests pour la classe de base SmartHRTBaseSensor."""

    def test_device_info(self, mock_coordinator, mock_config_entry):
        """Test des informations du device."""
        sensor = SmartHRTInteriorTempSensor(mock_coordinator, mock_config_entry)

        device_info = sensor.device_info

        assert device_info.get("entry_type") == DeviceEntryType.SERVICE
        assert (DOMAIN, mock_config_entry.entry_id) in device_info.get(
            "identifiers", set()
        )
        assert device_info.get("manufacturer") == DEVICE_MANUFACTURER

    def test_should_poll(self, mock_coordinator, mock_config_entry):
        """Test que le polling est désactivé."""
        sensor = SmartHRTInteriorTempSensor(mock_coordinator, mock_config_entry)

        assert sensor.should_poll is False


class TestSmartHRTInteriorTempSensor:
    """Tests pour le sensor de température intérieure."""

    def test_properties(self, mock_coordinator, mock_config_entry):
        """Test des propriétés du sensor."""
        sensor = SmartHRTInteriorTempSensor(mock_coordinator, mock_config_entry)

        assert sensor._attr_name == "Température intérieure"
        assert sensor.icon == "mdi:home-thermometer"
        assert sensor.device_class == SensorDeviceClass.TEMPERATURE
        assert sensor.state_class == SensorStateClass.MEASUREMENT
        assert sensor.native_unit_of_measurement == UnitOfTemperature.CELSIUS

    def test_native_value(self, mock_coordinator_with_data, mock_config_entry):
        """Test de la valeur native."""
        sensor = SmartHRTInteriorTempSensor(
            mock_coordinator_with_data, mock_config_entry
        )

        assert sensor.native_value == 18.5

    def test_native_value_none(self, mock_coordinator, mock_config_entry):
        """Test quand la valeur est None."""
        mock_coordinator.data.interior_temp = None
        sensor = SmartHRTInteriorTempSensor(mock_coordinator, mock_config_entry)

        assert sensor.native_value is None


class TestSmartHRTExteriorTempSensor:
    """Tests pour le sensor de température extérieure."""

    def test_properties(self, mock_coordinator, mock_config_entry):
        """Test des propriétés du sensor."""
        sensor = SmartHRTExteriorTempSensor(mock_coordinator, mock_config_entry)

        assert sensor._attr_name == "Température extérieure"
        assert sensor.icon == "mdi:thermometer"
        assert sensor.device_class == SensorDeviceClass.TEMPERATURE
        assert sensor.native_unit_of_measurement == UnitOfTemperature.CELSIUS

    def test_native_value(self, mock_coordinator_with_data, mock_config_entry):
        """Test de la valeur native."""
        sensor = SmartHRTExteriorTempSensor(
            mock_coordinator_with_data, mock_config_entry
        )

        assert sensor.native_value == 5.0


class TestSmartHRTWindSpeedSensor:
    """Tests pour le sensor de vitesse du vent."""

    def test_properties(self, mock_coordinator, mock_config_entry):
        """Test des propriétés du sensor."""
        sensor = SmartHRTWindSpeedSensor(mock_coordinator, mock_config_entry)

        assert sensor._attr_name == "Vitesse du vent"
        assert sensor.icon == "mdi:weather-windy"
        assert sensor.device_class == SensorDeviceClass.WIND_SPEED
        assert sensor.native_unit_of_measurement == UnitOfSpeed.METERS_PER_SECOND

    def test_native_value(self, mock_coordinator_with_data, mock_config_entry):
        """Test de la valeur native."""
        sensor = SmartHRTWindSpeedSensor(mock_coordinator_with_data, mock_config_entry)

        assert sensor.native_value == 2.5

    def test_native_value_rounded(self, mock_coordinator_with_data, mock_config_entry):
        """Test que la valeur est arrondie."""
        mock_coordinator_with_data.data.wind_speed = 2.567
        sensor = SmartHRTWindSpeedSensor(mock_coordinator_with_data, mock_config_entry)

        assert sensor.native_value == 2.6


class TestSmartHRTWindchillSensor:
    """Tests pour le sensor de température ressentie."""

    def test_properties(self, mock_coordinator, mock_config_entry):
        """Test des propriétés du sensor."""
        sensor = SmartHRTWindchillSensor(mock_coordinator, mock_config_entry)

        assert sensor._attr_name == "Température ressentie"
        assert sensor.icon == "mdi:snowflake-thermometer"
        assert sensor.device_class == SensorDeviceClass.TEMPERATURE
        assert sensor.native_unit_of_measurement == UnitOfTemperature.CELSIUS

    def test_native_value(self, mock_coordinator_with_data, mock_config_entry):
        """Test de la valeur native."""
        mock_coordinator_with_data.data.windchill = 3.5
        sensor = SmartHRTWindchillSensor(mock_coordinator_with_data, mock_config_entry)

        assert sensor.native_value == 3.5


class TestSmartHRTRecoveryStartSensor:
    """Tests pour le sensor d'heure de relance."""

    def test_properties(self, mock_coordinator, mock_config_entry):
        """Test des propriétés du sensor."""
        sensor = SmartHRTRecoveryStartSensor(mock_coordinator, mock_config_entry)

        assert sensor._attr_name == "Heure de relance"
        assert sensor.icon == "mdi:radiator"

    def test_native_value(self, mock_coordinator_with_data, mock_config_entry):
        """Test de la valeur native."""
        recovery_time = dt_util.now() + timedelta(hours=2)
        mock_coordinator_with_data.data.recovery_start_hour = recovery_time
        sensor = SmartHRTRecoveryStartSensor(
            mock_coordinator_with_data, mock_config_entry
        )

        expected = recovery_time.strftime("%H:%M")
        assert sensor.native_value == expected

    def test_native_value_none(self, mock_coordinator, mock_config_entry):
        """Test quand l'heure de relance est None."""
        mock_coordinator.data.recovery_start_hour = None
        sensor = SmartHRTRecoveryStartSensor(mock_coordinator, mock_config_entry)

        assert sensor.native_value is None

    def test_extra_state_attributes(
        self, mock_coordinator_with_data, mock_config_entry
    ):
        """Test des attributs supplémentaires."""
        from datetime import time as dt_time

        recovery_time = dt_util.now() + timedelta(hours=2)
        mock_coordinator_with_data.data.recovery_start_hour = recovery_time
        mock_coordinator_with_data.data.target_hour = dt_time(6, 0, 0)
        sensor = SmartHRTRecoveryStartSensor(
            mock_coordinator_with_data, mock_config_entry
        )

        attrs = sensor.extra_state_attributes

        assert "datetime" in attrs
        assert attrs["target_hour"] == "06:00"


class TestSmartHRTRCthSensor:
    """Tests pour le sensor RCth."""

    def test_properties(self, mock_coordinator, mock_config_entry):
        """Test des propriétés du sensor."""
        sensor = SmartHRTRCthSensor(mock_coordinator, mock_config_entry)

        assert sensor._attr_name == "RCth"
        assert sensor.icon == "mdi:home-battery-outline"
        assert sensor.state_class == SensorStateClass.MEASUREMENT
        assert sensor.native_unit_of_measurement == UnitOfTime.HOURS

    def test_native_value(self, mock_coordinator_with_data, mock_config_entry):
        """Test de la valeur native."""
        mock_coordinator_with_data.data.rcth = 50.123
        sensor = SmartHRTRCthSensor(mock_coordinator_with_data, mock_config_entry)

        assert sensor.native_value == 50.12

    def test_extra_state_attributes(
        self, mock_coordinator_with_data, mock_config_entry
    ):
        """Test des attributs supplémentaires."""
        mock_coordinator_with_data.data.rcth_lw = 55.0
        mock_coordinator_with_data.data.rcth_hw = 45.0
        mock_coordinator_with_data.data.rcth_calculated = 52.0
        sensor = SmartHRTRCthSensor(mock_coordinator_with_data, mock_config_entry)

        attrs = sensor.extra_state_attributes

        assert attrs["rcth_lw"] == 55.0
        assert attrs["rcth_hw"] == 45.0
        assert attrs["rcth_calculated"] == 52.0


class TestSmartHRTRPthSensor:
    """Tests pour le sensor RPth."""

    def test_properties(self, mock_coordinator, mock_config_entry):
        """Test des propriétés du sensor."""
        sensor = SmartHRTRPthSensor(mock_coordinator, mock_config_entry)

        assert sensor._attr_name == "RPth"


class TestAsyncSetupEntry:
    """Tests pour async_setup_entry des sensors."""

    @pytest.mark.asyncio
    async def test_async_setup_entry(
        self, mock_hass, mock_config_entry, mock_coordinator
    ):
        """Test de la configuration des entités sensor."""
        from custom_components.SmartHRT.const import DATA_COORDINATOR

        mock_hass.data[DOMAIN] = {
            mock_config_entry.entry_id: {DATA_COORDINATOR: mock_coordinator}
        }

        entities_added = []

        def mock_add_entities(new_entities, update_before_add=False):
            entities_added.extend(new_entities)

        await async_setup_entry(mock_hass, mock_config_entry, mock_add_entities)

        # Vérifier que les entités ont été ajoutées
        assert len(entities_added) > 0

        # Vérifier les types d'entités
        entity_types = [type(e).__name__ for e in entities_added]
        assert "SmartHRTInteriorTempSensor" in entity_types
        assert "SmartHRTExteriorTempSensor" in entity_types
        assert "SmartHRTWindSpeedSensor" in entity_types
