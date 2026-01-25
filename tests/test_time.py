"""Tests pour les entities time SmartHRT."""

from datetime import time as dt_time, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from homeassistant.util import dt as dt_util

from homeassistant.helpers.device_registry import DeviceEntryType

from custom_components.SmartHRT.time import (
    SmartHRTBaseTime,
    SmartHRTTargetHourTime,
    SmartHRTRecoveryCalcHourTime,
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

        # Vérifier que 3 entités ont été ajoutées (2 modifiables + 1 lecture seule)
        assert len(entities_added) == 3

        # Vérifier les types d'entités
        entity_types = [type(e).__name__ for e in entities_added]
        assert "SmartHRTTargetHourTime" in entity_types
        assert "SmartHRTRecoveryCalcHourTime" in entity_types
        assert "SmartHRTRecoveryStartTime" in entity_types
