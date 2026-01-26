"""Tests pour le module services.py - Gestion centralisée des services SmartHRT."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from custom_components.SmartHRT.const import (
    DOMAIN,
    DATA_COORDINATOR,
    SERVICE_CALCULATE_RECOVERY_TIME,
    SERVICE_RESET_LEARNING,
)
from custom_components.SmartHRT.services import (
    async_setup_services,
    async_unload_services,
    _get_coordinator,
    DATA_SERVICES_REGISTERED,
    SERVICES,
)


class TestGetCoordinator:
    """Tests pour la fonction _get_coordinator."""

    def test_get_coordinator_domain_not_in_data(self):
        """Test quand le domaine n'est pas dans hass.data."""
        mock_hass = MagicMock()
        mock_hass.data = {}

        result = _get_coordinator(mock_hass, None)

        assert result is None

    def test_get_coordinator_with_entry_id(self):
        """Test avec un entry_id spécifique."""
        mock_hass = MagicMock()
        mock_coordinator = MagicMock()
        mock_hass.data = {
            DOMAIN: {
                "test_entry_id": {DATA_COORDINATOR: mock_coordinator},
            }
        }

        result = _get_coordinator(mock_hass, "test_entry_id")

        assert result is mock_coordinator

    def test_get_coordinator_with_invalid_entry_id(self):
        """Test avec un entry_id invalide."""
        mock_hass = MagicMock()
        mock_coordinator = MagicMock()
        mock_hass.data = {
            DOMAIN: {
                "other_entry_id": {DATA_COORDINATOR: mock_coordinator},
            }
        }

        result = _get_coordinator(mock_hass, "invalid_id")

        # Avec la nouvelle implémentation, retourne None si l'entry_id est invalide
        assert result is None

    def test_get_coordinator_first_available(self):
        """Test sans entry_id, retourne le premier coordinateur."""
        mock_hass = MagicMock()
        mock_coordinator = MagicMock()
        mock_hass.data = {
            DOMAIN: {
                "entry1": {DATA_COORDINATOR: mock_coordinator},
                "entry2": {DATA_COORDINATOR: MagicMock()},
            }
        }

        result = _get_coordinator(mock_hass, None)

        assert result is not None

    def test_get_coordinator_multiple_instances_with_entry_id(self):
        """Test avec plusieurs instances et entry_id spécifié."""
        mock_hass = MagicMock()
        mock_coordinator1 = MagicMock()
        mock_coordinator1.name = "Instance 1"
        mock_coordinator2 = MagicMock()
        mock_coordinator2.name = "Instance 2"

        mock_hass.data = {
            DOMAIN: {
                "entry1": {DATA_COORDINATOR: mock_coordinator1},
                "entry2": {DATA_COORDINATOR: mock_coordinator2},
            }
        }

        # Récupérer la deuxième instance spécifiquement
        result = _get_coordinator(mock_hass, "entry2")

        assert result is mock_coordinator2
        assert result.name == "Instance 2"

    def test_get_coordinator_multiple_instances_without_entry_id(self):
        """Test avec plusieurs instances sans entry_id (warning attendu)."""
        mock_hass = MagicMock()
        mock_coordinator1 = MagicMock()
        mock_coordinator2 = MagicMock()

        mock_hass.data = {
            DOMAIN: {
                "entry1": {DATA_COORDINATOR: mock_coordinator1},
                "entry2": {DATA_COORDINATOR: mock_coordinator2},
            }
        }

        # Sans entry_id, retourne le premier (avec warning dans les logs)
        result = _get_coordinator(mock_hass, None)

        assert result is not None
        # Le résultat devrait être l'un des deux coordinateurs
        assert result in [mock_coordinator1, mock_coordinator2]


class TestAsyncSetupServices:
    """Tests pour async_setup_services."""

    @pytest.mark.asyncio
    async def test_services_already_registered(self):
        """Test que les services ne sont pas ré-enregistrés."""
        mock_hass = MagicMock()
        mock_hass.data = {DOMAIN: {DATA_SERVICES_REGISTERED: True}}

        await async_setup_services(mock_hass)

        # async_register ne devrait pas être appelé
        mock_hass.services.async_register.assert_not_called()

    @pytest.mark.asyncio
    async def test_services_registered_first_time(self):
        """Test que les services sont enregistrés la première fois."""
        mock_hass = MagicMock()
        mock_hass.data = {}
        mock_hass.services.async_register = MagicMock()

        await async_setup_services(mock_hass)

        # Vérifier que tous les services ont été enregistrés
        assert mock_hass.services.async_register.call_count == len(SERVICES)

        # Vérifier que le flag est défini
        assert mock_hass.data[DOMAIN][DATA_SERVICES_REGISTERED] is True


class TestAsyncUnloadServices:
    """Tests pour async_unload_services."""

    @pytest.mark.asyncio
    async def test_unload_with_remaining_coordinators(self):
        """Test que les services ne sont pas désenregistrés s'il reste des coordinateurs."""
        mock_hass = MagicMock()
        mock_hass.data = {
            DOMAIN: {
                "entry1": {DATA_COORDINATOR: MagicMock()},
                DATA_SERVICES_REGISTERED: True,
            }
        }

        await async_unload_services(mock_hass)

        # async_remove ne devrait pas être appelé
        mock_hass.services.async_remove.assert_not_called()

    @pytest.mark.asyncio
    async def test_unload_last_coordinator(self):
        """Test que les services sont désenregistrés quand c'est le dernier coordinateur."""
        mock_hass = MagicMock()
        mock_hass.data = {
            DOMAIN: {
                DATA_SERVICES_REGISTERED: True,
            }
        }
        mock_hass.services.has_service = MagicMock(return_value=True)
        mock_hass.services.async_remove = MagicMock()

        await async_unload_services(mock_hass)

        # Vérifier que tous les services ont été désenregistrés
        assert mock_hass.services.async_remove.call_count == len(SERVICES)

        # Vérifier que le flag a été supprimé
        assert DATA_SERVICES_REGISTERED not in mock_hass.data[DOMAIN]

    @pytest.mark.asyncio
    async def test_unload_domain_not_in_data(self):
        """Test quand le domaine n'est pas dans hass.data."""
        mock_hass = MagicMock()
        mock_hass.data = {}

        # Ne devrait pas lever d'exception
        await async_unload_services(mock_hass)


class TestMultipleInstances:
    """Tests pour la gestion de plusieurs instances."""

    @pytest.mark.asyncio
    async def test_two_instances_setup(self):
        """Test que les services ne sont enregistrés qu'une seule fois avec deux instances."""
        mock_hass = MagicMock()
        mock_hass.data = {}
        mock_hass.services.async_register = MagicMock()

        # Première instance
        await async_setup_services(mock_hass)
        first_call_count = mock_hass.services.async_register.call_count

        # Deuxième instance - ne devrait pas ré-enregistrer
        await async_setup_services(mock_hass)
        second_call_count = mock_hass.services.async_register.call_count

        assert first_call_count == len(SERVICES)
        assert second_call_count == first_call_count  # Pas de nouveaux appels

    @pytest.mark.asyncio
    async def test_first_instance_unload_keeps_services(self):
        """Test que le déchargement de la première instance conserve les services."""
        mock_hass = MagicMock()
        mock_hass.data = {
            DOMAIN: {
                "entry1": {DATA_COORDINATOR: MagicMock()},
                "entry2": {DATA_COORDINATOR: MagicMock()},
                DATA_SERVICES_REGISTERED: True,
            }
        }

        # Simuler le déchargement de la première instance
        # (entry1 est déjà supprimé avant l'appel à async_unload_services)
        del mock_hass.data[DOMAIN]["entry1"]

        await async_unload_services(mock_hass)

        # Les services ne doivent pas être désenregistrés
        mock_hass.services.async_remove.assert_not_called()
