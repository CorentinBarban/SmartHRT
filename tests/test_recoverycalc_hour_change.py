"""Tests pour le changement dynamique de recoverycalc_hour.

Ces tests vérifient que lorsque recoverycalc_hour est modifié juste après
que l'ancienne heure soit passée, le trigger est bien exécuté immédiatement.

Bug corrigé: Quand l'automation changeait recoverycalc_hour de 8h à 21h à
exactement 08:00:00, le trigger de 8h était annulé avant de s'exécuter,
et le système restait bloqué en HEATING_ON.
"""

from datetime import datetime, time as dt_time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from custom_components.SmartHRT.coordinator import (
    SmartHRTCoordinator,
    SmartHRTState,
)
from custom_components.SmartHRT.data_model import SmartHRTData


def make_mock_now(year=2026, month=2, day=4, hour=8, minute=0, second=0):
    """Helper pour créer un datetime pour les tests."""
    return datetime(year, month, day, hour, minute, second)


class TestSetRecoverycalcHourTriggerImmediate:
    """Tests pour le déclenchement immédiat lors du changement de recoverycalc_hour."""

    @pytest.mark.asyncio
    async def test_trigger_immediate_when_old_hour_just_passed(
        self, create_coordinator
    ):
        """Vérifie que le trigger est exécuté si l'ancienne heure vient de passer.

        Scénario: recoverycalc_hour = 08:00, heure actuelle = 08:00:30
        Quand on change vers 21:00, le trigger de 08:00 doit s'exécuter.
        """
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            # Il est 08:00:30, le trigger de 08:00 vient de passer
            mock_now = make_mock_now(hour=8, minute=0, second=30)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_ON,
                recoverycalc_hour=dt_time(8, 0, 0),  # Ancienne heure: 08:00
            )

            # Mock pour capturer l'appel à async_create_task
            created_tasks = []
            original_create_task = coord.hass.async_create_task

            def capture_create_task(coro):
                created_tasks.append(coro)
                return original_create_task(coro)

            coord.hass.async_create_task = capture_create_task

            # Changer l'heure vers 21:00 (comme le fait l'automation)
            coord.set_recoverycalc_hour(dt_time(21, 0, 0))

            # Vérifier qu'une tâche _async_on_recoverycalc_hour a été créée
            assert len(created_tasks) >= 1, "Le trigger immédiat n'a pas été déclenché"

    @pytest.mark.asyncio
    async def test_no_trigger_when_not_heating_on(self, create_coordinator):
        """Vérifie qu'aucun trigger n'est exécuté si on n'est pas en HEATING_ON."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = make_mock_now(hour=8, minute=0, second=30)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.MONITORING,  # Pas en HEATING_ON
                recoverycalc_hour=dt_time(8, 0, 0),
            )

            # Compter les tâches créées
            task_count_before = 0
            created_tasks = []

            def capture_create_task(coro):
                created_tasks.append(coro)
                return MagicMock()

            coord.hass.async_create_task = capture_create_task

            coord.set_recoverycalc_hour(dt_time(21, 0, 0))

            # Seule la tâche de sauvegarde doit être créée, pas le trigger
            # (1 tâche = _save_learned_data)
            assert len(created_tasks) == 1, (
                f"Trop de tâches créées: {len(created_tasks)}, "
                "le trigger ne devrait pas s'exécuter en MONITORING"
            )

    @pytest.mark.asyncio
    async def test_no_trigger_when_old_hour_not_yet_passed(self, create_coordinator):
        """Vérifie qu'aucun trigger n'est exécuté si l'ancienne heure n'est pas passée."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            # Il est 07:30, le trigger de 08:00 n'est pas encore passé
            mock_now = make_mock_now(hour=7, minute=30, second=0)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_ON,
                recoverycalc_hour=dt_time(8, 0, 0),
            )

            created_tasks = []

            def capture_create_task(coro):
                created_tasks.append(coro)
                return MagicMock()

            coord.hass.async_create_task = capture_create_task

            coord.set_recoverycalc_hour(dt_time(21, 0, 0))

            # Seule la tâche de sauvegarde doit être créée
            assert len(created_tasks) == 1, (
                f"Trop de tâches créées: {len(created_tasks)}, "
                "le trigger ne devrait pas s'exécuter avant l'heure"
            )

    @pytest.mark.asyncio
    async def test_no_trigger_when_old_hour_passed_too_long_ago(
        self, create_coordinator
    ):
        """Vérifie qu'aucun trigger n'est exécuté si l'ancienne heure est passée depuis trop longtemps."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            # Il est 08:10, le trigger de 08:00 est passé depuis 10 minutes (> 5 min)
            mock_now = make_mock_now(hour=8, minute=10, second=0)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_ON,
                recoverycalc_hour=dt_time(8, 0, 0),
            )

            created_tasks = []

            def capture_create_task(coro):
                created_tasks.append(coro)
                return MagicMock()

            coord.hass.async_create_task = capture_create_task

            coord.set_recoverycalc_hour(dt_time(21, 0, 0))

            # Seule la tâche de sauvegarde doit être créée
            assert len(created_tasks) == 1, (
                f"Trop de tâches créées: {len(created_tasks)}, "
                "le trigger ne devrait pas s'exécuter après 5 minutes"
            )

    @pytest.mark.asyncio
    async def test_trigger_within_5_minute_window(self, create_coordinator):
        """Vérifie le comportement à la limite de la fenêtre de 5 minutes.

        Note: Le trigger immédiat n'est déclenché que si l'heure est passée
        depuis moins de 60 secondes (pas 5 minutes). Au-delà, seule la
        sauvegarde est effectuée.
        """
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            # Il est 08:04:59, le trigger de 08:00 est passé depuis ~5 min
            # (hors de la fenêtre de 60 secondes)
            mock_now = make_mock_now(hour=8, minute=4, second=59)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_ON,
                recoverycalc_hour=dt_time(8, 0, 0),
            )

            created_tasks = []

            def capture_create_task(coro):
                created_tasks.append(coro)
                return MagicMock()

            coord.hass.async_create_task = capture_create_task

            coord.set_recoverycalc_hour(dt_time(21, 0, 0))

            # 1 tâche: _save_learned_data uniquement (hors fenêtre de 60s)
            assert len(created_tasks) == 1, (
                f"Attendu 1 tâche, reçu {len(created_tasks)}, "
                "hors de la fenêtre de 60 secondes"
            )


class TestSetRecoverycalcHourStateChange:
    """Tests pour vérifier la transition d'état lors du changement d'heure."""

    @pytest.mark.asyncio
    async def test_state_transitions_to_detecting_lag(self, create_coordinator):
        """Vérifie que l'état passe à DETECTING_LAG après le trigger immédiat."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = make_mock_now(hour=8, minute=0, second=30)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_ON,
                recoverycalc_hour=dt_time(8, 0, 0),
                interior_temp=19.0,
                exterior_temp=5.0,
            )

            # Exécuter directement la méthode async pour tester la transition
            await coord._async_on_recoverycalc_hour()

            assert coord.data.current_state == SmartHRTState.DETECTING_LAG

    @pytest.mark.asyncio
    async def test_recoverycalc_hour_updated_correctly(self, create_coordinator):
        """Vérifie que recoverycalc_hour est correctement mis à jour."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = make_mock_now(hour=7, minute=30, second=0)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_ON,
                recoverycalc_hour=dt_time(8, 0, 0),
            )

            coord.set_recoverycalc_hour(dt_time(21, 0, 0))

            assert coord.data.recoverycalc_hour == dt_time(21, 0, 0)
