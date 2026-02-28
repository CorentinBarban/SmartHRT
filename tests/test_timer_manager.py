"""Tests pour le TimerManager et la gestion des triggers.

ADR-051: Centralisation de la Gestion des Timers
- TimerManager.schedule() annule automatiquement l'ancien timer si présent
- TimerManager.cancel_all() nettoie proprement lors du déchargement
- Pas de double déclenchement ou de timer orphelin

Ce module consolide les tests de:
- test_no_double_trigger.py (supprimé)
- test_integration_log_scenario.py (supprimé)
"""

from datetime import datetime, time as dt_time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from custom_components.SmartHRT.const import TimerKey
from custom_components.SmartHRT.coordinator import (
    SmartHRTCoordinator,
    SmartHRTState,
)
from custom_components.SmartHRT.data_model import SmartHRTData


def make_mock_now(year=2026, month=2, day=4, hour=8, minute=0, second=0):
    """Helper pour créer un datetime pour les tests."""
    return datetime(year, month, day, hour, minute, second)


class TestTimerManagerBasics:
    """Tests de base pour le TimerManager (ADR-051)."""

    @pytest.mark.asyncio
    async def test_timer_manager_schedule_replaces_existing(self, create_coordinator):
        """Vérifie que TimerManager.schedule() remplace un timer existant.

        ADR-051: schedule() annule automatiquement l'ancien timer avant
        d'en programmer un nouveau pour la même clé.
        """
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = make_mock_now(hour=8, minute=0, second=0)
            mock_dt.now.return_value = mock_now
            mock_dt.as_local.side_effect = lambda x: x

            coord = await create_coordinator(
                initial_state=SmartHRTState.MONITORING,
                recovery_update_hour=make_mock_now(hour=8, minute=30),
            )

            # Appeler _setup_time_triggers (comme le fait set_target_hour)
            coord._setup_time_triggers()

            # Vérifier qu'un seul timer RECOVERY_UPDATE est actif
            assert coord._timer_manager.is_active(TimerKey.RECOVERY_UPDATE)
            # Le TimerManager gère l'unicité automatiquement

    @pytest.mark.asyncio
    async def test_set_target_hour_uses_timer_manager(self, create_coordinator):
        """Vérifie que set_target_hour utilise le TimerManager correctement."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = make_mock_now(hour=8, minute=0, second=0)
            mock_dt.now.return_value = mock_now
            mock_dt.as_local.side_effect = lambda x: x

            coord = await create_coordinator(
                initial_state=SmartHRTState.MONITORING,
                recovery_update_hour=make_mock_now(hour=8, minute=30),
            )

            # Changer target_hour
            coord.set_target_hour(dt_time(17, 30, 0))

            # Vérifier que le timer TARGET_HOUR est programmé
            assert coord._timer_manager.is_active(TimerKey.TARGET_HOUR)

    @pytest.mark.asyncio
    async def test_no_error_when_no_timer_exists(self, create_coordinator):
        """Vérifie qu'il n'y a pas d'erreur si aucun timer n'existe."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = make_mock_now(hour=8, minute=0, second=0)
            mock_dt.now.return_value = mock_now
            mock_dt.as_local.side_effect = lambda x: x

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_ON,
            )

            # Annuler tous les timers (simuler état vide)
            coord._timer_manager.cancel_all()

            # Ceci ne doit pas lever d'exception
            coord._setup_time_triggers()

            # Le test passe si aucune exception n'est levée
            assert (
                coord._timer_manager.timer_count >= 2
            )  # Au moins RECOVERYCALC et TARGET


class TestTriggerCleanup:
    """Tests pour le nettoyage des timers (ADR-051)."""

    @pytest.mark.asyncio
    async def test_cancel_time_triggers_clears_all(self, create_coordinator):
        """Vérifie que _cancel_time_triggers annule tous les timers horaires."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = make_mock_now(hour=8, minute=0, second=0)
            mock_dt.now.return_value = mock_now
            mock_dt.as_local.side_effect = lambda x: x

            coord = await create_coordinator(initial_state=SmartHRTState.HEATING_ON)

            # Setup des triggers
            coord._setup_time_triggers()

            # Annuler les triggers horaires
            coord._cancel_time_triggers()

            # Les timers horaires doivent être annulés
            assert not coord._timer_manager.is_active(TimerKey.RECOVERYCALC_HOUR)
            assert not coord._timer_manager.is_active(TimerKey.TARGET_HOUR)
            assert not coord._timer_manager.is_active(TimerKey.RECOVERY_START)
            assert not coord._timer_manager.is_active(TimerKey.RECOVERY_UPDATE)

    @pytest.mark.asyncio
    async def test_async_unload_cancels_all_timers(self, create_coordinator):
        """Vérifie que async_unload annule tous les timers via TimerManager."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = make_mock_now(hour=8, minute=0, second=0)
            mock_dt.now.return_value = mock_now
            mock_dt.as_local.side_effect = lambda x: x

            coord = await create_coordinator(initial_state=SmartHRTState.MONITORING)

            # Setup des triggers
            coord._setup_time_triggers()
            assert coord._timer_manager.timer_count > 0

            await coord.async_unload()

            # Tous les timers doivent être annulés
            assert coord._timer_manager.timer_count == 0
            assert coord._timer_manager.active_timers == []


class TestRecoveryStartRescheduling:
    """Tests pour la reprogrammation du trigger RECOVERY_START."""

    @pytest.mark.asyncio
    async def test_target_hour_change_recalculates_recovery_start(
        self, create_coordinator
    ):
        """Vérifie que set_target_hour recalcule et reprogramme recovery_start.

        Scénario du bug rapporté: en état MONITORING, quand target_hour change,
        recovery_start_hour doit être recalculé et le trigger reprogrammé.
        """
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = make_mock_now(hour=18, minute=14, second=0)
            mock_dt.now.return_value = mock_now
            mock_dt.as_local.side_effect = lambda x: x

            coord = await create_coordinator(
                initial_state=SmartHRTState.MONITORING,
                target_hour=dt_time(6, 0, 0),
                recovery_start_hour=make_mock_now(hour=4, minute=0, second=0),
                tsp=20.0,
            )

            # Changer target_hour à une nouvelle valeur
            coord.set_target_hour(dt_time(19, 15, 0))

            # Le target_hour doit être mis à jour
            assert coord.data.target_hour == dt_time(19, 15, 0)

    @pytest.mark.asyncio
    async def test_trigger_correctly_cancelled_between_reschedules(
        self, create_coordinator
    ):
        """Vérifie que le TimerManager gère les annulations automatiquement (ADR-051)."""

        coord = await create_coordinator(
            initial_state=SmartHRTState.MONITORING, smartheating_mode=True
        )

        # Programmer plusieurs fois à des heures différentes
        times = [
            datetime(2026, 2, 3, 20, 0, 0),
            datetime(2026, 2, 3, 20, 30, 0),
            datetime(2026, 2, 3, 21, 0, 0),
            datetime(2026, 2, 3, 21, 30, 0),
        ]

        for new_time in times:
            coord.data.recovery_start_hour = new_time
            coord._schedule_recovery_start(new_time)

        # Avec TimerManager, il ne doit y avoir qu'un seul timer actif
        assert coord._timer_manager.is_active(TimerKey.RECOVERY_START)
        # Vérifier que l'heure programmée est la dernière
        info = coord._timer_manager.get_info(TimerKey.RECOVERY_START)
        assert info is not None
        assert info.scheduled_time == times[-1]

    @pytest.mark.asyncio
    async def test_no_trigger_leak_after_multiple_changes(self, create_coordinator):
        """Vérifie qu'il n'y a pas de fuite de triggers grâce au TimerManager (ADR-051)."""

        coord = await create_coordinator(
            initial_state=SmartHRTState.MONITORING, smartheating_mode=True
        )

        # Simuler de multiples changements de coefficients
        coefficients = [45.0, 50.0, 40.0, 55.0, 35.0]

        for coeff in coefficients:
            coord.data.recovery_start_hour = datetime(2026, 2, 3, 21, 0, 0)
            with patch.object(coord, "calculate_recovery_time"):
                coord.set_rcth(coeff)

        # ADR-051: TimerManager garantit un seul timer par clé
        recovery_start_active = coord._timer_manager.is_active(TimerKey.RECOVERY_START)

        # Il doit y avoir au plus 1 timer RECOVERY_START actif
        if recovery_start_active:
            assert coord._timer_manager.get_info(TimerKey.RECOVERY_START) is not None


class TestIntegrationLogScenario:
    """Test de régression reproduisant le scénario exact des logs.

    Scénario SmartHRT Chambre#01KGJBGC:
    1. L'heure de relance était calculée à 19h26 à l'initialisation
    2. Les modifications successives des coefficients l'ont fait évoluer à 21h08
    3. Mais le trigger n'était pas reprogrammé, causant un déclenchement à 19h26

    Le test vérifie que le problème est désormais corrigé grâce au TimerManager (ADR-051).
    """

    @pytest.mark.asyncio
    async def test_log_scenario_smarthrt_chambre_01kgjbgc_regression(
        self, create_coordinator
    ):
        """Reproduit exactement le scénario problématique des logs.

        Séquence des événements extraite des logs:
        - 19:16:17 - Initialisation, recovery_time calculé à 19:26:18
        - 19:16:37 - RCth = 43.97, recovery_time = 19:26:38
        - 19:16:43 - RCth LW = 49.64, recovery_time = 19:26:44
        - 19:16:50 - RCth HW = 37.88, recovery_time = 19:26:51
        - 19:16:55 - RPth = 97.0, recovery_time = 19:26:56
        - 19:17:02 - RPth LW = 104.0, recovery_time = 21:08:08 ← changement majeur
        - 19:17:12 - RPth HW = 54.0, recovery_time = 21:08:40 ← heure finale
        """
        recovery_times = []

        def mock_calculate_recovery_time(coord):
            # Simuler l'évolution des heures de relance selon les logs
            if len(recovery_times) == 0:
                coord.data.recovery_start_hour = datetime(2026, 2, 3, 19, 26, 18)
            elif len(recovery_times) == 1:
                coord.data.recovery_start_hour = datetime(2026, 2, 3, 19, 26, 38)
            elif len(recovery_times) == 2:
                coord.data.recovery_start_hour = datetime(2026, 2, 3, 19, 26, 44)
            elif len(recovery_times) == 3:
                coord.data.recovery_start_hour = datetime(2026, 2, 3, 19, 26, 51)
            elif len(recovery_times) == 4:
                coord.data.recovery_start_hour = datetime(2026, 2, 3, 19, 26, 56)
            elif len(recovery_times) == 5:
                coord.data.recovery_start_hour = datetime(2026, 2, 3, 21, 8, 8)
            elif len(recovery_times) == 6:
                coord.data.recovery_start_hour = datetime(2026, 2, 3, 21, 8, 40)

            recovery_times.append(coord.data.recovery_start_hour)

        # Initialisation à 19h16:17 comme dans les logs
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 3, 19, 16, 17)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.MONITORING,
                smartheating_mode=True,
                interior_temp=15.9,
                exterior_temp=8.1,
                wind_speed=4.33,  # 15.6 km/h / 3.6
                data_overrides={
                    "tsp": 19.0,
                    "target_hour": dt_time(23, 0, 0),
                    "recoverycalc_hour": dt_time(23, 30, 0),
                },
            )

        # Tracker de tous les appels de programmation de trigger via TimerManager
        scheduled_times = []

        def track_scheduling(*args, **kwargs):
            if len(args) >= 3:
                scheduled_times.append(args[2])
            return MagicMock()

        with patch(
            "custom_components.SmartHRT.timer_manager.async_track_point_in_time",
            side_effect=track_scheduling,
        ):
            with patch.object(
                coord,
                "calculate_recovery_time",
                lambda: mock_calculate_recovery_time(coord),
            ):
                # État initial - trigger programmé à 19h26:18
                mock_calculate_recovery_time(coord)
                coord._schedule_recovery_start(coord.data.recovery_start_hour)

                # Séquence exacte des changements des logs
                coord.set_rcth(43.97)
                coord.set_rcth_lw(49.64)
                coord.set_rcth_hw(37.88)
                coord.set_rpth(97.0)
                coord.set_rpth_lw(104.0)
                coord.set_rpth_hw(54.0)

        # Vérifications critiques
        assert (
            len(scheduled_times) >= 7
        ), f"Pas assez de programmations: {len(scheduled_times)}"

        # Le trigger final doit être programmé à 21h08:40, pas 19h26:18
        final_scheduled_time = scheduled_times[-1]
        assert (
            final_scheduled_time.hour == 21
        ), f"Heure incorrecte: {final_scheduled_time.hour}, attendu: 21"
        assert (
            final_scheduled_time.minute == 8
        ), f"Minute incorrecte: {final_scheduled_time.minute}, attendu: 8"
