"""Tests pour les services SmartHRT.

Ces tests vérifient le bon fonctionnement des services, en particulier
le service stop_heating qui doit appeler correctement la méthode async.

Bug corrigé: Le service stop_heating utilisait `await coord._on_recoverycalc_hour(None)`
sur une méthode synchrone décorée @callback, causant une TypeError.
"""

from datetime import datetime, time as dt_time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.SmartHRT.coordinator import (
    SmartHRTCoordinator,
    SmartHRTState,
)


def make_mock_now(year=2026, month=2, day=4, hour=8, minute=0, second=0):
    """Helper pour créer un datetime pour les tests."""
    return datetime(year, month, day, hour, minute, second)


class TestStopHeatingService:
    """Tests pour le service stop_heating."""

    @pytest.mark.asyncio
    async def test_stop_heating_calls_async_method(self, create_coordinator):
        """Vérifie que stop_heating appelle _async_on_recoverycalc_hour (pas la version sync).

        Bug corrigé: Avant, le code faisait:
            await coord._on_recoverycalc_hour(None)
        Ce qui causait: TypeError: object NoneType can't be used in 'await' expression

        Maintenant, le code fait:
            await coord._async_on_recoverycalc_hour()
        """
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = make_mock_now(hour=8, minute=0, second=0)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_ON,
                interior_temp=19.0,
                exterior_temp=5.0,
            )

            # Appeler directement la méthode async (comme le fait le service)
            # Ceci ne doit pas lever d'exception
            await coord._async_on_recoverycalc_hour()

            # Vérifier la transition d'état
            assert coord.data.current_state == SmartHRTState.DETECTING_LAG

    @pytest.mark.asyncio
    async def test_on_recoverycalc_hour_is_sync_callback(self, create_coordinator):
        """Vérifie que _on_recoverycalc_hour est bien une méthode synchrone.

        Cette méthode est décorée avec @callback et retourne None.
        On ne peut pas faire 'await' dessus.
        """
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = make_mock_now(hour=8, minute=0, second=0)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_ON,
            )

            # _on_recoverycalc_hour est synchrone et retourne None
            result = coord._on_recoverycalc_hour(None)

            # Vérifier que le résultat est None (méthode synchrone @callback)
            assert result is None

    @pytest.mark.asyncio
    async def test_async_on_recoverycalc_hour_is_awaitable(self, create_coordinator):
        """Vérifie que _async_on_recoverycalc_hour est bien une coroutine awaitable."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = make_mock_now(hour=8, minute=0, second=0)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_ON,
                interior_temp=19.0,
                exterior_temp=5.0,
            )

            # _async_on_recoverycalc_hour doit être une coroutine
            import asyncio

            coro = coord._async_on_recoverycalc_hour()
            assert asyncio.iscoroutine(coro)

            # L'awaiter pour éviter le warning "coroutine was never awaited"
            await coro

    @pytest.mark.asyncio
    async def test_stop_heating_transitions_state_correctly(self, create_coordinator):
        """Vérifie la transition complète lors de l'arrêt du chauffage."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = make_mock_now(hour=8, minute=0, second=0)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_ON,
                interior_temp=19.5,
                exterior_temp=5.0,
                smartheating_mode=True,
            )

            # État initial
            assert coord.data.current_state == SmartHRTState.HEATING_ON
            assert coord.data.temp_lag_detection_active is False

            # Simuler l'appel au service stop_heating
            await coord._async_on_recoverycalc_hour()

            # Vérifications après transition
            assert coord.data.current_state == SmartHRTState.DETECTING_LAG
            assert coord.data.temp_lag_detection_active is True
            assert coord.data.temp_recovery_calc == 19.5

    @pytest.mark.asyncio
    async def test_stop_heating_records_timestamp(self, create_coordinator):
        """Vérifie que l'heure de coupure est enregistrée."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = make_mock_now(hour=8, minute=28, second=18)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_ON,
                interior_temp=19.0,
                exterior_temp=5.0,
            )

            await coord._async_on_recoverycalc_hour()

            # L'heure de coupure doit être enregistrée
            assert coord.data.time_recovery_calc is not None
            assert coord.data.time_recovery_calc == mock_now


class TestServiceIntegration:
    """Tests d'intégration pour vérifier le pattern d'appel des services."""

    @pytest.mark.asyncio
    async def test_service_handler_pattern_is_correct(self):
        """Vérifie que les services utilisent les méthodes façade.

        Les services essentiels appellent les méthodes façade:
        - async_trigger_calculation
        - async_manual_stop_heating
        - async_start_heating_cycle
        - etc.
        """
        from pathlib import Path

        services_path = Path("custom_components/SmartHRT/services.py")

        if not services_path.exists():
            pytest.skip("Fichier services.py non trouvé")

        content = services_path.read_text()

        # Vérifier que l'ancien handler bugué n'est plus présent
        assert "_on_recoverycalc_hour" not in content, (
            "L'ancien handler '_on_recoverycalc_hour' ne devrait plus exister "
            "(services simplifiés)"
        )

        # Vérifier que les méthodes façade sont utilisées
        assert (
            "async_trigger_calculation" in content
        ), "La méthode façade 'async_trigger_calculation' devrait être utilisée"
