"""Tests pour les sensors SmartHRT."""

from datetime import datetime, timedelta, time as dt_time
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
    SmartHRTRCthSensor,
    SmartHRTRPthSensor,
    SmartHRTRecoveryStartTimestampSensor,
    SmartHRTTargetHourTimestampSensor,
    SmartHRTRecoveryCalcHourTimestampSensor,
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
        assert "SmartHRTRecoveryStartTimestampSensor" in entity_types
        assert "SmartHRTTargetHourTimestampSensor" in entity_types
        assert "SmartHRTRecoveryCalcHourTimestampSensor" in entity_types


class TestSmartHRTTimestampSensors:
    """Tests pour les sensors timestamp utilisés dans les automatisations."""

    def test_recovery_start_timestamp_sensor(
        self, mock_coordinator_with_data, mock_config_entry
    ):
        """Test du sensor timestamp de relance."""
        recovery_time = dt_util.now() + timedelta(hours=3)
        mock_coordinator_with_data.data.recovery_start_hour = recovery_time

        sensor = SmartHRTRecoveryStartTimestampSensor(
            mock_coordinator_with_data, mock_config_entry
        )

        assert sensor._attr_name == "Heure de relance"
        assert sensor.device_class == SensorDeviceClass.TIMESTAMP
        # Le sensor retourne le datetime localisé
        assert sensor.native_value == dt_util.as_local(recovery_time)
        assert sensor.icon == "mdi:clock-start"

    def test_target_hour_timestamp_sensor(
        self, mock_coordinator_with_data, mock_config_entry
    ):
        """Test du sensor timestamp d'heure cible."""
        mock_coordinator_with_data.data.target_hour = dt_time(6, 30, 0)

        sensor = SmartHRTTargetHourTimestampSensor(
            mock_coordinator_with_data, mock_config_entry
        )

        assert sensor._attr_name == "Heure cible"
        assert sensor.device_class == SensorDeviceClass.TIMESTAMP
        assert sensor.icon == "mdi:clock-end"

        # Vérifie que le timestamp retourné est bien un datetime
        value = sensor.native_value
        assert value is not None
        assert isinstance(value, datetime)
        assert value.hour == 6
        assert value.minute == 30

    def test_recoverycalc_hour_timestamp_sensor(
        self, mock_coordinator_with_data, mock_config_entry
    ):
        """Test du sensor timestamp de coupure chauffage."""
        mock_coordinator_with_data.data.recoverycalc_hour = dt_time(23, 0, 0)

        sensor = SmartHRTRecoveryCalcHourTimestampSensor(
            mock_coordinator_with_data, mock_config_entry
        )

        assert sensor._attr_name == "Heure coupure chauffage"
        assert sensor.device_class == SensorDeviceClass.TIMESTAMP
        assert sensor.icon == "mdi:clock-in"

        # Vérifie que le timestamp retourné est bien un datetime
        value = sensor.native_value
        assert value is not None
        assert isinstance(value, datetime)
        assert value.hour == 23
        assert value.minute == 0
