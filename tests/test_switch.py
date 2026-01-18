"""Tests pour les switches SmartHRT."""

from unittest.mock import MagicMock, patch

import pytest

from homeassistant.helpers.device_registry import DeviceEntryType

from custom_components.SmartHRT.switch import (
    SmartHRTBaseSwitch,
    SmartHRTSmartHeatingSwitch,
    SmartHRTAdaptiveSwitch,
    async_setup_entry,
)
from custom_components.SmartHRT.const import DOMAIN, DEVICE_MANUFACTURER


class TestSmartHRTBaseSwitch:
    """Tests pour la classe de base SmartHRTBaseSwitch."""

    def test_device_info(self, mock_coordinator, mock_config_entry):
        """Test des informations du device."""
        switch = SmartHRTSmartHeatingSwitch(mock_coordinator, mock_config_entry)

        device_info = switch.device_info

        assert device_info["entry_type"] == DeviceEntryType.SERVICE
        assert (DOMAIN, mock_config_entry.entry_id) in device_info["identifiers"]
        assert device_info["manufacturer"] == DEVICE_MANUFACTURER


class TestSmartHRTSmartHeatingSwitch:
    """Tests pour le switch du mode chauffage intelligent."""

    def test_properties(self, mock_coordinator, mock_config_entry):
        """Test des propriétés du switch."""
        switch = SmartHRTSmartHeatingSwitch(mock_coordinator, mock_config_entry)

        assert switch._attr_name == "Mode chauffage intelligent"

    def test_is_on_true(self, mock_coordinator_with_data, mock_config_entry):
        """Test quand le mode est actif."""
        mock_coordinator_with_data.data.smartheating_mode = True
        switch = SmartHRTSmartHeatingSwitch(
            mock_coordinator_with_data, mock_config_entry
        )

        assert switch.is_on is True

    def test_is_on_false(self, mock_coordinator_with_data, mock_config_entry):
        """Test quand le mode est inactif."""
        mock_coordinator_with_data.data.smartheating_mode = False
        switch = SmartHRTSmartHeatingSwitch(
            mock_coordinator_with_data, mock_config_entry
        )

        assert switch.is_on is False

    def test_icon_on(self, mock_coordinator_with_data, mock_config_entry):
        """Test de l'icône quand actif."""
        mock_coordinator_with_data.data.smartheating_mode = True
        switch = SmartHRTSmartHeatingSwitch(
            mock_coordinator_with_data, mock_config_entry
        )

        assert switch.icon == "mdi:home-thermometer"

    def test_icon_off(self, mock_coordinator_with_data, mock_config_entry):
        """Test de l'icône quand inactif."""
        mock_coordinator_with_data.data.smartheating_mode = False
        switch = SmartHRTSmartHeatingSwitch(
            mock_coordinator_with_data, mock_config_entry
        )

        assert switch.icon == "mdi:home-thermometer-outline"

    @pytest.mark.asyncio
    async def test_async_turn_on(self, mock_coordinator_with_data, mock_config_entry):
        """Test de l'activation du mode."""
        switch = SmartHRTSmartHeatingSwitch(
            mock_coordinator_with_data, mock_config_entry
        )
        mock_coordinator_with_data.set_smartheating_mode = MagicMock()

        await switch.async_turn_on()

        mock_coordinator_with_data.set_smartheating_mode.assert_called_once_with(True)

    @pytest.mark.asyncio
    async def test_async_turn_off(self, mock_coordinator_with_data, mock_config_entry):
        """Test de la désactivation du mode."""
        switch = SmartHRTSmartHeatingSwitch(
            mock_coordinator_with_data, mock_config_entry
        )
        mock_coordinator_with_data.set_smartheating_mode = MagicMock()

        await switch.async_turn_off()

        mock_coordinator_with_data.set_smartheating_mode.assert_called_once_with(False)


class TestSmartHRTAdaptiveSwitch:
    """Tests pour le switch du mode adaptatif."""

    def test_properties(self, mock_coordinator, mock_config_entry):
        """Test des propriétés du switch."""
        switch = SmartHRTAdaptiveSwitch(mock_coordinator, mock_config_entry)

        assert switch._attr_name == "Mode adaptatif"

    def test_is_on_true(self, mock_coordinator_with_data, mock_config_entry):
        """Test quand le mode est actif."""
        mock_coordinator_with_data.data.recovery_adaptive_mode = True
        switch = SmartHRTAdaptiveSwitch(mock_coordinator_with_data, mock_config_entry)

        assert switch.is_on is True

    def test_is_on_false(self, mock_coordinator_with_data, mock_config_entry):
        """Test quand le mode est inactif."""
        mock_coordinator_with_data.data.recovery_adaptive_mode = False
        switch = SmartHRTAdaptiveSwitch(mock_coordinator_with_data, mock_config_entry)

        assert switch.is_on is False

    def test_icon_on(self, mock_coordinator_with_data, mock_config_entry):
        """Test de l'icône quand actif."""
        mock_coordinator_with_data.data.recovery_adaptive_mode = True
        switch = SmartHRTAdaptiveSwitch(mock_coordinator_with_data, mock_config_entry)

        assert switch.icon == "mdi:brain"

    def test_icon_off(self, mock_coordinator_with_data, mock_config_entry):
        """Test de l'icône quand inactif."""
        mock_coordinator_with_data.data.recovery_adaptive_mode = False
        switch = SmartHRTAdaptiveSwitch(mock_coordinator_with_data, mock_config_entry)

        assert switch.icon == "mdi:brain-off-outline"

    @pytest.mark.asyncio
    async def test_async_turn_on(self, mock_coordinator_with_data, mock_config_entry):
        """Test de l'activation du mode."""
        switch = SmartHRTAdaptiveSwitch(mock_coordinator_with_data, mock_config_entry)
        mock_coordinator_with_data.set_adaptive_mode = MagicMock()

        await switch.async_turn_on()

        mock_coordinator_with_data.set_adaptive_mode.assert_called_once_with(True)

    @pytest.mark.asyncio
    async def test_async_turn_off(self, mock_coordinator_with_data, mock_config_entry):
        """Test de la désactivation du mode."""
        switch = SmartHRTAdaptiveSwitch(mock_coordinator_with_data, mock_config_entry)
        mock_coordinator_with_data.set_adaptive_mode = MagicMock()

        await switch.async_turn_off()

        mock_coordinator_with_data.set_adaptive_mode.assert_called_once_with(False)


class TestAsyncSetupEntry:
    """Tests pour async_setup_entry des switches."""

    @pytest.mark.asyncio
    async def test_async_setup_entry(
        self, mock_hass, mock_config_entry, mock_coordinator
    ):
        """Test de la configuration des entités switch."""
        from custom_components.SmartHRT.const import DATA_COORDINATOR

        mock_hass.data[DOMAIN] = {
            mock_config_entry.entry_id: {DATA_COORDINATOR: mock_coordinator}
        }

        entities_added = []

        def mock_add_entities(entities, update_before_add):
            entities_added.extend(entities)

        await async_setup_entry(mock_hass, mock_config_entry, mock_add_entities)

        # Vérifier que 2 entités ont été ajoutées
        assert len(entities_added) == 2

        # Vérifier les types d'entités
        entity_types = [type(e).__name__ for e in entities_added]
        assert "SmartHRTSmartHeatingSwitch" in entity_types
        assert "SmartHRTAdaptiveSwitch" in entity_types
