"""Tests pour le module __init__ SmartHRT."""

from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from custom_components.SmartHRT import (
    async_setup_entry,
    async_unload_entry,
    update_listener,
)
from custom_components.SmartHRT.const import DOMAIN, PLATFORMS, DATA_COORDINATOR


class TestAsyncSetupEntry:
    """Tests pour async_setup_entry."""

    @pytest.mark.asyncio
    async def test_async_setup_entry_success(self, mock_hass, mock_config_entry):
        """Test de la configuration réussie."""
        with patch("custom_components.SmartHRT.SmartHRTCoordinator") as MockCoordinator:
            mock_coordinator = MagicMock()
            mock_coordinator.async_setup = AsyncMock()
            MockCoordinator.return_value = mock_coordinator

            result = await async_setup_entry(mock_hass, mock_config_entry)

            assert result is True
            assert DOMAIN in mock_hass.data
            assert mock_config_entry.entry_id in mock_hass.data[DOMAIN]
            mock_coordinator.async_setup.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_setup_entry_creates_coordinator(
        self, mock_hass, mock_config_entry
    ):
        """Test que le coordinateur est créé."""
        with patch("custom_components.SmartHRT.SmartHRTCoordinator") as MockCoordinator:
            mock_coordinator = MagicMock()
            mock_coordinator.async_setup = AsyncMock()
            MockCoordinator.return_value = mock_coordinator

            await async_setup_entry(mock_hass, mock_config_entry)

            MockCoordinator.assert_called_once_with(mock_hass, mock_config_entry)

    @pytest.mark.asyncio
    async def test_async_setup_entry_stores_coordinator(
        self, mock_hass, mock_config_entry
    ):
        """Test que le coordinateur est stocké."""
        with patch("custom_components.SmartHRT.SmartHRTCoordinator") as MockCoordinator:
            mock_coordinator = MagicMock()
            mock_coordinator.async_setup = AsyncMock()
            MockCoordinator.return_value = mock_coordinator

            await async_setup_entry(mock_hass, mock_config_entry)

            stored_data = mock_hass.data[DOMAIN][mock_config_entry.entry_id]
            assert DATA_COORDINATOR in stored_data
            assert stored_data[DATA_COORDINATOR] == mock_coordinator

    @pytest.mark.asyncio
    async def test_async_setup_entry_registers_update_listener(
        self, mock_hass, mock_config_entry
    ):
        """Test que l'update listener est enregistré."""
        with patch("custom_components.SmartHRT.SmartHRTCoordinator") as MockCoordinator:
            mock_coordinator = MagicMock()
            mock_coordinator.async_setup = AsyncMock()
            MockCoordinator.return_value = mock_coordinator

            await async_setup_entry(mock_hass, mock_config_entry)

            mock_config_entry.add_update_listener.assert_called_once()
            mock_config_entry.async_on_unload.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_setup_entry_forwards_platforms(
        self, mock_hass, mock_config_entry
    ):
        """Test que les plateformes sont forwarded."""
        with patch("custom_components.SmartHRT.SmartHRTCoordinator") as MockCoordinator:
            mock_coordinator = MagicMock()
            mock_coordinator.async_setup = AsyncMock()
            MockCoordinator.return_value = mock_coordinator

            await async_setup_entry(mock_hass, mock_config_entry)

            mock_hass.config_entries.async_forward_entry_setups.assert_called_once_with(
                mock_config_entry, PLATFORMS
            )


class TestAsyncUnloadEntry:
    """Tests pour async_unload_entry."""

    @pytest.mark.asyncio
    async def test_async_unload_entry_success(self, mock_hass, mock_config_entry):
        """Test du déchargement réussi."""
        mock_coordinator = MagicMock()
        mock_coordinator.async_unload = AsyncMock()

        mock_hass.data[DOMAIN] = {
            mock_config_entry.entry_id: {DATA_COORDINATOR: mock_coordinator}
        }

        result = await async_unload_entry(mock_hass, mock_config_entry)

        assert result is True
        mock_coordinator.async_unload.assert_called_once()
        assert mock_config_entry.entry_id not in mock_hass.data[DOMAIN]

    @pytest.mark.asyncio
    async def test_async_unload_entry_no_coordinator(
        self, mock_hass, mock_config_entry
    ):
        """Test du déchargement sans coordinateur."""
        mock_hass.data[DOMAIN] = {}

        result = await async_unload_entry(mock_hass, mock_config_entry)

        assert result is True

    @pytest.mark.asyncio
    async def test_async_unload_entry_unloads_platforms(
        self, mock_hass, mock_config_entry
    ):
        """Test que les plateformes sont déchargées."""
        mock_coordinator = MagicMock()
        mock_coordinator.async_unload = AsyncMock()

        mock_hass.data[DOMAIN] = {
            mock_config_entry.entry_id: {DATA_COORDINATOR: mock_coordinator}
        }

        await async_unload_entry(mock_hass, mock_config_entry)

        mock_hass.config_entries.async_unload_platforms.assert_called_once_with(
            mock_config_entry, PLATFORMS
        )


class TestUpdateListener:
    """Tests pour update_listener."""

    @pytest.mark.asyncio
    async def test_update_listener_applies_options(self, mock_hass, mock_config_entry):
        """Test que l'update listener applique les options au coordinateur."""
        from unittest.mock import MagicMock
        from custom_components.SmartHRT.const import (
            CONF_TSP,
            CONF_TARGET_HOUR,
            CONF_RECOVERYCALC_HOUR,
        )

        # Créer un mock du coordinateur
        mock_coordinator = MagicMock()
        mock_coordinator._parse_time = lambda x: x  # Simplify for test
        mock_coordinator.set_tsp = MagicMock()
        mock_coordinator.set_target_hour = MagicMock()
        mock_coordinator.set_recoverycalc_hour = MagicMock()

        # Configurer les options du config_entry
        mock_config_entry.options = {
            CONF_TSP: 21.0,
            CONF_TARGET_HOUR: "07:00:00",
            CONF_RECOVERYCALC_HOUR: "22:00:00",
        }

        # Configurer hass.data
        mock_hass.data[DOMAIN] = {
            mock_config_entry.entry_id: {DATA_COORDINATOR: mock_coordinator}
        }

        await update_listener(mock_hass, mock_config_entry)

        # Vérifier que les setters ont été appelés
        mock_coordinator.set_tsp.assert_called_once_with(21.0)
        mock_coordinator.set_target_hour.assert_called_once()
        mock_coordinator.set_recoverycalc_hour.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_listener_no_coordinator(self, mock_hass, mock_config_entry):
        """Test que l'update listener gère l'absence de coordinateur."""
        mock_hass.data[DOMAIN] = {mock_config_entry.entry_id: {}}

        # Ne devrait pas lever d'exception
        await update_listener(mock_hass, mock_config_entry)


class TestRemoveObsoleteEntities:
    """Tests pour la suppression des entités obsolètes (ADR-016)."""

    @pytest.mark.asyncio
    async def test_remove_obsolete_entities_no_entities(
        self, mock_hass, mock_config_entry
    ):
        """Test que la fonction ne fait rien si les entités n'existent pas."""
        from custom_components.SmartHRT import _remove_obsolete_entities

        # Mock du registre d'entités
        with patch("custom_components.SmartHRT.er.async_get") as mock_get_registry:
            mock_registry = MagicMock()
            mock_get_registry.return_value = mock_registry

            # Simuler que les entités n'existent pas
            mock_registry.async_get_entity_id.return_value = None

            # Appeler la fonction de nettoyage
            await _remove_obsolete_entities(mock_hass, mock_config_entry)

            # Vérifier qu'aucune suppression n'a été tentée
            mock_registry.async_remove.assert_not_called()
