"""Tests pour les entities number SmartHRT."""

from unittest.mock import MagicMock

import pytest

from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.components.number import NumberMode
from homeassistant.helpers.device_registry import DeviceEntryType

from custom_components.SmartHRT.number import (
    SmartHRTBaseNumber,
    SmartHRTSetPointNumber,
    SmartHRTRCthNumber,
    SmartHRTRPthNumber,
    SmartHRTRCthLWNumber,
    SmartHRTRCthHWNumber,
    SmartHRTRPthLWNumber,
    SmartHRTRPthHWNumber,
    SmartHRTRelaxationNumber,
    async_setup_entry,
)
from custom_components.SmartHRT.const import (
    DOMAIN,
    DEVICE_MANUFACTURER,
    DEFAULT_TSP_MIN,
    DEFAULT_TSP_MAX,
    DEFAULT_TSP_STEP,
    DEFAULT_RCTH_MIN,
    DEFAULT_RCTH_MAX,
)


class TestSmartHRTSetPointNumber:
    """Tests pour l'entité number de consigne."""

    def test_properties(self, mock_coordinator, mock_config_entry):
        """Test des propriétés."""
        number = SmartHRTSetPointNumber(mock_coordinator, mock_config_entry)

        assert number._attr_name == "Consigne"
        assert number._attr_native_min_value == DEFAULT_TSP_MIN
        assert number._attr_native_max_value == DEFAULT_TSP_MAX
        assert number._attr_native_step == DEFAULT_TSP_STEP
        assert number._attr_native_unit_of_measurement == UnitOfTemperature.CELSIUS
        assert number._attr_mode == NumberMode.BOX
        assert number.icon == "mdi:thermometer"

    def test_native_value(self, mock_coordinator_with_data, mock_config_entry):
        """Test de la valeur native."""
        number = SmartHRTSetPointNumber(mock_coordinator_with_data, mock_config_entry)

        assert number.native_value == 19.0

    @pytest.mark.asyncio
    async def test_async_set_native_value(
        self, mock_coordinator_with_data, mock_config_entry
    ):
        """Test de la modification de la valeur."""
        number = SmartHRTSetPointNumber(mock_coordinator_with_data, mock_config_entry)
        mock_coordinator_with_data.set_tsp = MagicMock()

        await number.async_set_native_value(20.5)

        mock_coordinator_with_data.set_tsp.assert_called_once_with(20.5)


class TestSmartHRTRCthNumber:
    """Tests pour l'entité number RCth."""

    def test_properties(self, mock_coordinator, mock_config_entry):
        """Test des propriétés."""
        number = SmartHRTRCthNumber(mock_coordinator, mock_config_entry)

        assert number._attr_name == "RCth"
        assert number._attr_native_min_value == DEFAULT_RCTH_MIN
        assert number._attr_native_max_value == DEFAULT_RCTH_MAX
        assert number._attr_native_step == 0.5
        assert number._attr_native_unit_of_measurement == UnitOfTime.HOURS
        assert number.icon == "mdi:home-battery-outline"

    def test_native_value(self, mock_coordinator_with_data, mock_config_entry):
        """Test de la valeur native."""
        mock_coordinator_with_data.data.rcth = 52.567
        number = SmartHRTRCthNumber(mock_coordinator_with_data, mock_config_entry)

        assert number.native_value == 52.57

    @pytest.mark.asyncio
    async def test_async_set_native_value(
        self, mock_coordinator_with_data, mock_config_entry
    ):
        """Test de la modification de la valeur."""
        number = SmartHRTRCthNumber(mock_coordinator_with_data, mock_config_entry)
        mock_coordinator_with_data.set_rcth = MagicMock()

        await number.async_set_native_value(55.0)

        mock_coordinator_with_data.set_rcth.assert_called_once_with(55.0)


class TestSmartHRTRPthNumber:
    """Tests pour l'entité number RPth."""

    def test_properties(self, mock_coordinator, mock_config_entry):
        """Test des propriétés."""
        number = SmartHRTRPthNumber(mock_coordinator, mock_config_entry)

        assert number._attr_name == "RPth"
        assert number.icon == "mdi:home-lightning-bolt-outline"

    def test_native_value(self, mock_coordinator_with_data, mock_config_entry):
        """Test de la valeur native."""
        mock_coordinator_with_data.data.rpth = 48.33
        number = SmartHRTRPthNumber(mock_coordinator_with_data, mock_config_entry)

        assert number.native_value == 48.33

    @pytest.mark.asyncio
    async def test_async_set_native_value(
        self, mock_coordinator_with_data, mock_config_entry
    ):
        """Test de la modification de la valeur."""
        number = SmartHRTRPthNumber(mock_coordinator_with_data, mock_config_entry)
        mock_coordinator_with_data.set_rpth = MagicMock()

        await number.async_set_native_value(45.0)

        mock_coordinator_with_data.set_rpth.assert_called_once_with(45.0)


class TestSmartHRTRCthLWNumber:
    """Tests pour l'entité number RCth low wind."""

    def test_properties(self, mock_coordinator, mock_config_entry):
        """Test des propriétés."""
        number = SmartHRTRCthLWNumber(mock_coordinator, mock_config_entry)

        assert number._attr_name == "RCth (vent faible)"

    def test_native_value(self, mock_coordinator_with_data, mock_config_entry):
        """Test de la valeur native."""
        mock_coordinator_with_data.data.rcth_lw = 55.0
        number = SmartHRTRCthLWNumber(mock_coordinator_with_data, mock_config_entry)

        assert number.native_value == 55.0


class TestSmartHRTRCthHWNumber:
    """Tests pour l'entité number RCth high wind."""

    def test_properties(self, mock_coordinator, mock_config_entry):
        """Test des propriétés."""
        number = SmartHRTRCthHWNumber(mock_coordinator, mock_config_entry)

        assert number._attr_name == "RCth (vent fort)"

    def test_native_value(self, mock_coordinator_with_data, mock_config_entry):
        """Test de la valeur native."""
        mock_coordinator_with_data.data.rcth_hw = 45.0
        number = SmartHRTRCthHWNumber(mock_coordinator_with_data, mock_config_entry)

        assert number.native_value == 45.0


class TestSmartHRTRPthLWNumber:
    """Tests pour l'entité number RPth low wind."""

    def test_properties(self, mock_coordinator, mock_config_entry):
        """Test des propriétés."""
        number = SmartHRTRPthLWNumber(mock_coordinator, mock_config_entry)

        assert number._attr_name == "RPth (vent faible)"

    def test_native_value(self, mock_coordinator_with_data, mock_config_entry):
        """Test de la valeur native."""
        mock_coordinator_with_data.data.rpth_lw = 55.0
        number = SmartHRTRPthLWNumber(mock_coordinator_with_data, mock_config_entry)

        assert number.native_value == 55.0


class TestSmartHRTRPthHWNumber:
    """Tests pour l'entité number RPth high wind."""

    def test_properties(self, mock_coordinator, mock_config_entry):
        """Test des propriétés."""
        number = SmartHRTRPthHWNumber(mock_coordinator, mock_config_entry)

        assert number._attr_name == "RPth (vent fort)"

    def test_native_value(self, mock_coordinator_with_data, mock_config_entry):
        """Test de la valeur native."""
        mock_coordinator_with_data.data.rpth_hw = 45.0
        number = SmartHRTRPthHWNumber(mock_coordinator_with_data, mock_config_entry)

        assert number.native_value == 45.0


class TestSmartHRTRelaxationNumber:
    """Tests pour l'entité number du facteur de relaxation."""

    def test_properties(self, mock_coordinator, mock_config_entry):
        """Test des propriétés."""
        number = SmartHRTRelaxationNumber(mock_coordinator, mock_config_entry)

        assert number._attr_name == "Facteur de relaxation"

    def test_native_value(self, mock_coordinator_with_data, mock_config_entry):
        """Test de la valeur native."""
        mock_coordinator_with_data.data.relaxation_factor = 2.5
        number = SmartHRTRelaxationNumber(mock_coordinator_with_data, mock_config_entry)

        assert number.native_value == 2.5

    @pytest.mark.asyncio
    async def test_async_set_native_value(
        self, mock_coordinator_with_data, mock_config_entry
    ):
        """Test de la modification de la valeur."""
        number = SmartHRTRelaxationNumber(mock_coordinator_with_data, mock_config_entry)
        mock_coordinator_with_data.set_relaxation_factor = MagicMock()

        await number.async_set_native_value(3.0)

        mock_coordinator_with_data.set_relaxation_factor.assert_called_once_with(3.0)


class TestAsyncSetupEntry:
    """Tests pour async_setup_entry des numbers."""

    @pytest.mark.asyncio
    async def test_async_setup_entry(
        self, mock_hass, mock_config_entry, mock_coordinator
    ):
        """Test de la configuration des entités number."""
        from custom_components.SmartHRT.const import DATA_COORDINATOR

        mock_hass.data[DOMAIN] = {
            mock_config_entry.entry_id: {DATA_COORDINATOR: mock_coordinator}
        }

        entities_added = []

        def mock_add_entities(entities, update_before_add):
            entities_added.extend(entities)

        await async_setup_entry(mock_hass, mock_config_entry, mock_add_entities)

        # Vérifier que les entités ont été ajoutées
        assert len(entities_added) == 8

        # Vérifier les types d'entités
        entity_types = [type(e).__name__ for e in entities_added]
        assert "SmartHRTSetPointNumber" in entity_types
        assert "SmartHRTRCthNumber" in entity_types
        assert "SmartHRTRPthNumber" in entity_types
