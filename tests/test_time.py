"""Tests pour les entities time SmartHRT."""

from datetime import time as dt_time, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from homeassistant.helpers.device_registry import DeviceEntryType

from custom_components.SmartHRT.time import (
    SmartHRTBaseTime,
    SmartHRTTargetHourTime,
    SmartHRTRecoveryCalcHourTime,
    SmartHRTRecoveryStartHourTime,
    async_setup_entry,
)
from custom_components.SmartHRT.const import DOMAIN, DEVICE_MANUFACTURER


class TestSmartHRTTargetHourTime:
    """Tests pour l'entité time de l'heure cible."""

    def test_properties(self, mock_coordinator, mock_config_entry):
        """Test des propriétés."""
        time_entity = SmartHRTTargetHourTime(mock_coordinator, mock_config_entry)

        assert time_entity._attr_name == "Heure cible"
        assert time_entity.icon == "mdi:clock-end"

    def test_native_value(self, mock_coordinator_with_data, mock_config_entry):
        """Test de la valeur native."""
        mock_coordinator_with_data.data.target_hour = dt_time(6, 30, 0)
        time_entity = SmartHRTTargetHourTime(
            mock_coordinator_with_data, mock_config_entry
        )

        assert time_entity.native_value == dt_time(6, 30, 0)

    @pytest.mark.asyncio
    async def test_async_set_value(self, mock_coordinator_with_data, mock_config_entry):
        """Test de la modification de la valeur."""
        time_entity = SmartHRTTargetHourTime(
            mock_coordinator_with_data, mock_config_entry
        )
        mock_coordinator_with_data.set_target_hour = MagicMock()

        new_time = dt_time(7, 0, 0)
        await time_entity.async_set_value(new_time)

        mock_coordinator_with_data.set_target_hour.assert_called_once_with(new_time)


class TestSmartHRTRecoveryCalcHourTime:
    """Tests pour l'entité time de l'heure de coupure."""

    def test_properties(self, mock_coordinator, mock_config_entry):
        """Test des propriétés."""
        time_entity = SmartHRTRecoveryCalcHourTime(mock_coordinator, mock_config_entry)

        assert time_entity._attr_name == "Heure coupure chauffage"
        assert time_entity.icon == "mdi:clock-in"

    def test_native_value(self, mock_coordinator_with_data, mock_config_entry):
        """Test de la valeur native."""
        mock_coordinator_with_data.data.recoverycalc_hour = dt_time(22, 30, 0)
        time_entity = SmartHRTRecoveryCalcHourTime(
            mock_coordinator_with_data, mock_config_entry
        )

        assert time_entity.native_value == dt_time(22, 30, 0)

    @pytest.mark.asyncio
    async def test_async_set_value(self, mock_coordinator_with_data, mock_config_entry):
        """Test de la modification de la valeur."""
        time_entity = SmartHRTRecoveryCalcHourTime(
            mock_coordinator_with_data, mock_config_entry
        )
        mock_coordinator_with_data.set_recoverycalc_hour = MagicMock()

        new_time = dt_time(22, 0, 0)
        await time_entity.async_set_value(new_time)

        mock_coordinator_with_data.set_recoverycalc_hour.assert_called_once_with(
            new_time
        )


class TestSmartHRTRecoveryStartHourTime:
    """Tests pour l'entité time de l'heure de relance calculée."""

    def test_properties(self, mock_coordinator, mock_config_entry):
        """Test des propriétés."""
        time_entity = SmartHRTRecoveryStartHourTime(mock_coordinator, mock_config_entry)

        assert time_entity._attr_name == "Heure relance calculée"

    def test_native_value_with_datetime(
        self, mock_coordinator_with_data, mock_config_entry
    ):
        """Test de la valeur native avec une datetime."""
        recovery_time = datetime.now().replace(
            hour=5, minute=30, second=0, microsecond=0
        )
        mock_coordinator_with_data.data.recovery_start_hour = recovery_time
        time_entity = SmartHRTRecoveryStartHourTime(
            mock_coordinator_with_data, mock_config_entry
        )

        result = time_entity.native_value
        assert result.hour == 5
        assert result.minute == 30

    def test_native_value_none(self, mock_coordinator_with_data, mock_config_entry):
        """Test quand l'heure de relance est None."""
        mock_coordinator_with_data.data.recovery_start_hour = None
        time_entity = SmartHRTRecoveryStartHourTime(
            mock_coordinator_with_data, mock_config_entry
        )

        assert time_entity.native_value is None


class TestSmartHRTRecoveryUpdateHourTime:
    """Tests pour l'entité time de l'heure de mise à jour du calcul."""

    def test_properties(self, mock_coordinator, mock_config_entry):
        """Test des propriétés."""
        from custom_components.SmartHRT.time import SmartHRTRecoveryUpdateHourTime

        time_entity = SmartHRTRecoveryUpdateHourTime(
            mock_coordinator, mock_config_entry
        )

        assert time_entity._attr_name == "Heure prochaine mise à jour calcul"
        assert time_entity.icon == "mdi:update"

    def test_native_value_with_datetime(
        self, mock_coordinator_with_data, mock_config_entry
    ):
        """Test de la valeur native avec une datetime."""
        from custom_components.SmartHRT.time import SmartHRTRecoveryUpdateHourTime

        update_time = datetime.now().replace(hour=2, minute=45, second=0, microsecond=0)
        mock_coordinator_with_data.data.recovery_update_hour = update_time
        time_entity = SmartHRTRecoveryUpdateHourTime(
            mock_coordinator_with_data, mock_config_entry
        )

        result = time_entity.native_value
        assert result.hour == 2
        assert result.minute == 45

    def test_native_value_none(self, mock_coordinator_with_data, mock_config_entry):
        """Test quand l'heure de mise à jour est None."""
        from custom_components.SmartHRT.time import SmartHRTRecoveryUpdateHourTime

        mock_coordinator_with_data.data.recovery_update_hour = None
        time_entity = SmartHRTRecoveryUpdateHourTime(
            mock_coordinator_with_data, mock_config_entry
        )

        assert time_entity.native_value is None


class TestSmartHRTBaseTime:
    """Tests pour la classe de base SmartHRTBaseTime."""

    def test_device_info(self, mock_coordinator, mock_config_entry):
        """Test des informations du device."""
        time_entity = SmartHRTTargetHourTime(mock_coordinator, mock_config_entry)

        device_info = time_entity.device_info

        assert device_info["entry_type"] == DeviceEntryType.SERVICE
        assert (DOMAIN, mock_config_entry.entry_id) in device_info["identifiers"]
        assert device_info["manufacturer"] == DEVICE_MANUFACTURER


class TestAsyncSetupEntry:
    """Tests pour async_setup_entry des time entities."""

    @pytest.mark.asyncio
    async def test_async_setup_entry(
        self, mock_hass, mock_config_entry, mock_coordinator
    ):
        """Test de la configuration des entités time."""
        from custom_components.SmartHRT.const import DATA_COORDINATOR

        mock_hass.data[DOMAIN] = {
            mock_config_entry.entry_id: {DATA_COORDINATOR: mock_coordinator}
        }

        entities_added = []

        def mock_add_entities(entities, update_before_add):
            entities_added.extend(entities)

        await async_setup_entry(mock_hass, mock_config_entry, mock_add_entities)

        # Vérifier que 4 entités ont été ajoutées
        assert len(entities_added) == 4

        # Vérifier les types d'entités
        entity_types = [type(e).__name__ for e in entities_added]
        assert "SmartHRTTargetHourTime" in entity_types
        assert "SmartHRTRecoveryCalcHourTime" in entity_types
        assert "SmartHRTRecoveryStartHourTime" in entity_types
        assert "SmartHRTRecoveryUpdateHourTime" in entity_types
