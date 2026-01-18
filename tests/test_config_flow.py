"""Tests pour le config flow SmartHRT."""

from unittest.mock import patch, MagicMock, AsyncMock
import pytest

from homeassistant.data_entry_flow import FlowResultType

from custom_components.SmartHRT.config_flow import (
    SmartHRTConfigFlow,
    SmartHRTOptionsFlow,
    add_suggested_values_to_schema,
)
from custom_components.SmartHRT.const import (
    DOMAIN,
    CONF_NAME,
    CONF_TARGET_HOUR,
    CONF_RECOVERYCALC_HOUR,
    CONF_SENSOR_INTERIOR_TEMP,
    CONF_PHONE_ALARM,
    CONF_TSP,
)

import voluptuous as vol


class TestAddSuggestedValues:
    """Tests pour la fonction add_suggested_values_to_schema."""

    def test_add_suggested_values_basic(self):
        """Test de l'ajout de valeurs suggérées."""
        schema = vol.Schema(
            {
                vol.Required("name"): str,
                vol.Optional("value"): int,
            }
        )

        suggested = {"name": "test_name", "value": 42}

        result = add_suggested_values_to_schema(schema, suggested)

        assert result is not None
        assert isinstance(result, vol.Schema)

    def test_add_suggested_values_empty(self):
        """Test avec des valeurs suggérées vides."""
        schema = vol.Schema(
            {
                vol.Required("name"): str,
            }
        )

        result = add_suggested_values_to_schema(schema, {})

        assert result is not None


class TestSmartHRTConfigFlow:
    """Tests pour le config flow SmartHRT."""

    @pytest.fixture
    def config_flow(self):
        """Create a config flow instance."""
        flow = SmartHRTConfigFlow()
        flow.hass = MagicMock()
        return flow

    @pytest.mark.asyncio
    async def test_async_step_user_first_call(self, config_flow):
        """Test du premier appel de async_step_user."""
        result = await config_flow.async_step_user(None)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "user"

    @pytest.mark.asyncio
    async def test_async_step_user_with_input(self, config_flow):
        """Test de async_step_user avec user_input."""
        with patch.object(
            config_flow, "async_step_sensors", new_callable=AsyncMock
        ) as mock_sensors:
            mock_sensors.return_value = {
                "type": FlowResultType.FORM,
                "step_id": "sensors",
            }

            result = await config_flow.async_step_user({CONF_NAME: "Test SmartHRT"})

            mock_sensors.assert_called_once()
            assert config_flow._user_inputs[CONF_NAME] == "Test SmartHRT"

    @pytest.mark.asyncio
    async def test_async_step_sensors_first_call(self, config_flow):
        """Test du premier appel de async_step_sensors."""
        config_flow._user_inputs = {CONF_NAME: "Test SmartHRT"}

        result = await config_flow.async_step_sensors(None)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "sensors"

    @pytest.mark.asyncio
    async def test_async_step_sensors_with_input(self, config_flow):
        """Test de async_step_sensors avec user_input complet."""
        config_flow._user_inputs = {CONF_NAME: "Test SmartHRT"}

        user_input = {
            CONF_TARGET_HOUR: "06:00:00",
            CONF_RECOVERYCALC_HOUR: "23:00:00",
            CONF_SENSOR_INTERIOR_TEMP: "sensor.interior_temp",
            CONF_TSP: 19.0,
        }

        with patch.object(config_flow, "async_create_entry") as mock_create:
            mock_create.return_value = {"type": FlowResultType.CREATE_ENTRY}

            result = await config_flow.async_step_sensors(user_input)

            mock_create.assert_called_once()
            call_args = mock_create.call_args
            assert call_args[1]["title"] == "Test SmartHRT"

    @pytest.mark.asyncio
    async def test_async_step_sensors_with_phone_alarm(self, config_flow):
        """Test de async_step_sensors avec alarme téléphone."""
        config_flow._user_inputs = {CONF_NAME: "Test SmartHRT"}

        user_input = {
            CONF_TARGET_HOUR: "06:00:00",
            CONF_RECOVERYCALC_HOUR: "23:00:00",
            CONF_SENSOR_INTERIOR_TEMP: "sensor.interior_temp",
            CONF_PHONE_ALARM: "sensor.phone_alarm",
            CONF_TSP: 19.0,
        }

        with patch.object(config_flow, "async_create_entry") as mock_create:
            mock_create.return_value = {"type": FlowResultType.CREATE_ENTRY}

            result = await config_flow.async_step_sensors(user_input)

            assert config_flow._user_inputs[CONF_PHONE_ALARM] == "sensor.phone_alarm"


class TestSmartHRTOptionsFlow:
    """Tests pour le options flow SmartHRT."""

    @pytest.fixture
    def mock_config_entry(self):
        """Create a mock config entry."""
        entry = MagicMock()
        entry.entry_id = "test_entry_id"
        entry.data = {
            CONF_NAME: "Test SmartHRT",
            CONF_TARGET_HOUR: "06:00:00",
            CONF_RECOVERYCALC_HOUR: "23:00:00",
            CONF_SENSOR_INTERIOR_TEMP: "sensor.interior_temp",
            CONF_TSP: 19.0,
        }
        return entry

    @pytest.fixture
    def options_flow(self, mock_config_entry):
        """Create an options flow instance."""
        return SmartHRTOptionsFlow(mock_config_entry)

    def test_options_flow_init(self, options_flow, mock_config_entry):
        """Test de l'initialisation du options flow."""
        assert options_flow.config_entry == mock_config_entry
        assert options_flow._user_inputs[CONF_NAME] == "Test SmartHRT"

    @pytest.mark.asyncio
    async def test_async_step_init_first_call(self, options_flow):
        """Test du premier appel de async_step_init."""
        result = await options_flow.async_step_init(None)

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"

    @pytest.mark.asyncio
    async def test_async_step_init_with_input(self, options_flow):
        """Test de async_step_init avec user_input."""
        user_input = {
            CONF_NAME: "Updated SmartHRT",
            CONF_TARGET_HOUR: "07:00:00",
            CONF_RECOVERYCALC_HOUR: "22:00:00",
            CONF_SENSOR_INTERIOR_TEMP: "sensor.new_temp",
            CONF_TSP: 20.0,
        }

        # Mock the hass attribute on options_flow
        mock_hass = MagicMock()
        mock_hass.config_entries = MagicMock()
        mock_hass.config_entries.async_update_entry = MagicMock()
        options_flow.hass = mock_hass

        with patch.object(options_flow, "async_create_entry") as mock_create:
            mock_create.return_value = {"type": FlowResultType.CREATE_ENTRY}

            result = await options_flow.async_step_init(user_input)

            # The flow should complete successfully


class TestConfigFlowIntegration:
    """Tests d'intégration pour le config flow."""

    @pytest.mark.asyncio
    async def test_full_config_flow(self):
        """Test du flux complet de configuration."""
        flow = SmartHRTConfigFlow()
        flow.hass = MagicMock()

        # Étape 1: user
        result1 = await flow.async_step_user(None)
        assert result1["type"] == FlowResultType.FORM
        assert result1["step_id"] == "user"

        # Étape 2: user avec input
        with patch.object(
            flow, "async_step_sensors", new_callable=AsyncMock
        ) as mock_sensors:
            mock_sensors.return_value = {
                "type": FlowResultType.FORM,
                "step_id": "sensors",
            }
            result2 = await flow.async_step_user({CONF_NAME: "My SmartHRT"})

    @pytest.mark.asyncio
    async def test_async_get_options_flow(self):
        """Test de la récupération du options flow."""
        mock_entry = MagicMock()
        mock_entry.data = {CONF_NAME: "Test"}

        options_flow = SmartHRTConfigFlow.async_get_options_flow(mock_entry)

        assert isinstance(options_flow, SmartHRTOptionsFlow)
