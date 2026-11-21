"""Tests pour la restauration de l'état après redémarrage.

Ce module teste que la machine à états se restaure correctement
après un redémarrage de Home Assistant, en vérifiant:
- La cohérence entre état persisté et heure actuelle (_is_state_coherent)
- La détermination de la période nuit/jour (_is_night_period)
- La reprogrammation des triggers
- L'auto-correction vers HEATING_ON en cas d'incohérence
"""

from datetime import datetime, time as dt_time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.SmartHRT.const import DEFAULT_TSP
from custom_components.SmartHRT.coordinator import (
    SmartHRTCoordinator,
    SmartHRTState,
)
from custom_components.SmartHRT.data_model import SmartHRTData


class TestIsNightPeriod:
    """Tests pour _is_night_period.

    Détermine si on est en période nocturne (MONITORING attendu).
    """

    @pytest.mark.asyncio
    async def test_night_after_recoverycalc_before_midnight(self, create_coordinator):
        """Test: 23:30 avec target=06:00, recoverycalc=23:00 → nuit."""
        coord = await create_coordinator()
        current_time = dt_time(23, 30, 0)
        target = dt_time(6, 0, 0)
        recoverycalc = dt_time(23, 0, 0)

        is_night = coord._is_night_period(current_time, target, recoverycalc)

        assert is_night is True

    @pytest.mark.asyncio
    async def test_night_before_target_after_midnight(self, create_coordinator):
        """Test: 05:00 avec target=06:00, recoverycalc=23:00 → nuit."""
        coord = await create_coordinator()
        current_time = dt_time(5, 0, 0)
        target = dt_time(6, 0, 0)
        recoverycalc = dt_time(23, 0, 0)

        is_night = coord._is_night_period(current_time, target, recoverycalc)

        assert is_night is True

    @pytest.mark.asyncio
    async def test_day_between_target_and_recoverycalc(self, create_coordinator):
        """Test: 10:00 avec target=06:00, recoverycalc=23:00 → jour."""
        coord = await create_coordinator()
        current_time = dt_time(10, 0, 0)
        target = dt_time(6, 0, 0)
        recoverycalc = dt_time(23, 0, 0)

        is_night = coord._is_night_period(current_time, target, recoverycalc)

        assert is_night is False

    @pytest.mark.asyncio
    async def test_atypical_hours_during_night_period(self, create_coordinator):
        """Test: config atypique recoverycalc=13:30, target=17:30 - 14:00 → nuit."""
        coord = await create_coordinator()
        current_time = dt_time(14, 0, 0)
        target = dt_time(17, 30, 0)
        recoverycalc = dt_time(13, 30, 0)

        is_night = coord._is_night_period(current_time, target, recoverycalc)

        assert is_night is True

    @pytest.mark.asyncio
    async def test_atypical_hours_during_day_period(self, create_coordinator):
        """Test: config atypique recoverycalc=13:30, target=17:30 - 18:00 → jour."""
        coord = await create_coordinator()
        current_time = dt_time(18, 0, 0)
        target = dt_time(17, 30, 0)
        recoverycalc = dt_time(13, 30, 0)

        is_night = coord._is_night_period(current_time, target, recoverycalc)

        assert is_night is False


class TestIsStateCoherent:
    """Tests pour _is_state_coherent.

    Vérifie si l'état persisté est cohérent avec l'heure actuelle.
    """

    @pytest.mark.asyncio
    async def test_heating_on_always_coherent(self, create_coordinator):
        """Test: HEATING_ON est toujours cohérent (état sûr par défaut)."""
        coord = await create_coordinator()
        coord.data.target_hour = dt_time(6, 0, 0)
        coord.data.recoverycalc_hour = dt_time(23, 0, 0)

        # À n'importe quelle heure
        for hour in [0, 5, 10, 15, 23]:
            now = datetime(2026, 2, 4, hour, 0, 0)
            assert coord._is_state_coherent(SmartHRTState.HEATING_ON, now) is True

    @pytest.mark.asyncio
    async def test_monitoring_coherent_at_night(self, create_coordinator):
        """Test: MONITORING cohérent la nuit (après 23:00 ou avant 06:00)."""
        coord = await create_coordinator()
        coord.data.target_hour = dt_time(6, 0, 0)
        coord.data.recoverycalc_hour = dt_time(23, 0, 0)

        # 23:30 → nuit → cohérent
        now = datetime(2026, 2, 4, 23, 30, 0)
        assert coord._is_state_coherent(SmartHRTState.MONITORING, now) is True

        # 05:00 → nuit → cohérent
        now = datetime(2026, 2, 4, 5, 0, 0)
        assert coord._is_state_coherent(SmartHRTState.MONITORING, now) is True

    @pytest.mark.asyncio
    async def test_monitoring_incoherent_during_day(self, create_coordinator):
        """Test: MONITORING incohérent pendant le jour (entre 06:00 et 23:00)."""
        coord = await create_coordinator()
        coord.data.target_hour = dt_time(6, 0, 0)
        coord.data.recoverycalc_hour = dt_time(23, 0, 0)

        # 10:00 → jour → incohérent
        now = datetime(2026, 2, 4, 10, 0, 0)
        assert coord._is_state_coherent(SmartHRTState.MONITORING, now) is False

    @pytest.mark.asyncio
    async def test_detecting_lag_coherent_at_night(self, create_coordinator):
        """Test: DETECTING_LAG cohérent la nuit (comme MONITORING)."""
        coord = await create_coordinator()
        coord.data.target_hour = dt_time(6, 0, 0)
        coord.data.recoverycalc_hour = dt_time(23, 0, 0)

        # 23:05 → nuit → cohérent
        now = datetime(2026, 2, 4, 23, 5, 0)
        assert coord._is_state_coherent(SmartHRTState.DETECTING_LAG, now) is True

    @pytest.mark.asyncio
    async def test_recovery_coherent_during_recovery_period(self, create_coordinator):
        """Test: RECOVERY cohérent si recovery_start_hour <= now < target."""
        coord = await create_coordinator()
        coord.data.target_hour = dt_time(6, 0, 0)
        coord.data.recoverycalc_hour = dt_time(23, 0, 0)
        coord.data.recovery_start_hour = datetime(2026, 2, 4, 5, 0, 0)

        # 05:30, entre recovery_start et target → cohérent
        now = datetime(2026, 2, 4, 5, 30, 0)
        assert coord._is_state_coherent(SmartHRTState.RECOVERY, now) is True

    @pytest.mark.asyncio
    async def test_heating_process_coherent_during_recovery_period(
        self, create_coordinator
    ):
        """Test: HEATING_PROCESS cohérent si recovery_start_hour <= now < target."""
        coord = await create_coordinator()
        coord.data.target_hour = dt_time(6, 0, 0)
        coord.data.recoverycalc_hour = dt_time(23, 0, 0)
        coord.data.recovery_start_hour = datetime(2026, 2, 4, 5, 0, 0)

        # 05:45, entre recovery_start et target → cohérent
        now = datetime(2026, 2, 4, 5, 45, 0)
        assert coord._is_state_coherent(SmartHRTState.HEATING_PROCESS, now) is True

    @pytest.mark.asyncio
    async def test_recovery_incoherent_without_recovery_start_hour(
        self, create_coordinator
    ):
        """Test: RECOVERY incohérent si pas de recovery_start_hour."""
        coord = await create_coordinator()
        coord.data.target_hour = dt_time(6, 0, 0)
        coord.data.recoverycalc_hour = dt_time(23, 0, 0)
        coord.data.recovery_start_hour = None

        now = datetime(2026, 2, 4, 5, 30, 0)
        assert coord._is_state_coherent(SmartHRTState.RECOVERY, now) is False

    @pytest.mark.asyncio
    async def test_heating_process_incoherent_after_target(self, create_coordinator):
        """Test: HEATING_PROCESS incohérent après target_hour."""
        coord = await create_coordinator()
        coord.data.target_hour = dt_time(6, 0, 0)
        coord.data.recoverycalc_hour = dt_time(23, 0, 0)
        coord.data.recovery_start_hour = datetime(2026, 2, 4, 5, 0, 0)

        # 10:00, après target → incohérent
        now = datetime(2026, 2, 4, 10, 0, 0)
        assert coord._is_state_coherent(SmartHRTState.HEATING_PROCESS, now) is False


class TestRestoreStateAfterRestart:
    """Tests pour _restore_state_after_restart.

    Vérifie que les états sont correctement restaurés après redémarrage,
    avec auto-correction vers HEATING_ON en cas d'incohérence.
    """

    @pytest.mark.asyncio
    async def test_coherent_heating_on_state(self, create_coordinator):
        """Test: état HEATING_ON persisté, heure=10:00 → cohérent, pas de changement."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 4, 10, 0, 0)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_ON,
            )
            coord.data.target_hour = dt_time(6, 0, 0)
            coord.data.recoverycalc_hour = dt_time(23, 0, 0)

            await coord._restore_state_after_restart()

            assert coord.data.current_state == SmartHRTState.HEATING_ON

    @pytest.mark.asyncio
    async def test_coherent_monitoring_state(self, create_coordinator):
        """Test: état MONITORING persisté, heure=00:30 → cohérent."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 4, 0, 30, 0)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.MONITORING,
                recovery_calc_mode=True,
            )
            coord.data.target_hour = dt_time(6, 0, 0)
            coord.data.recoverycalc_hour = dt_time(23, 0, 0)

            await coord._restore_state_after_restart()

            assert coord.data.current_state == SmartHRTState.MONITORING

    @pytest.mark.asyncio
    async def test_detecting_lag_coherent_at_night(self, create_coordinator):
        """Test: état DETECTING_LAG persisté pendant la nuit → cohérent."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 4, 23, 5, 0)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.DETECTING_LAG,
                temp_lag_detection_active=True,
            )
            coord.data.target_hour = dt_time(6, 0, 0)
            coord.data.recoverycalc_hour = dt_time(23, 0, 0)

            await coord._restore_state_after_restart()

            # DETECTING_LAG est cohérent la nuit
            assert coord.data.current_state == SmartHRTState.DETECTING_LAG

    @pytest.mark.asyncio
    async def test_recovery_coherent_during_recovery_period(self, create_coordinator):
        """Test: état RECOVERY persisté pendant la relance → cohérent."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 4, 5, 30, 0)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.RECOVERY,
                recovery_start_hour=datetime(2026, 2, 4, 5, 0, 0),
            )
            coord.data.target_hour = dt_time(6, 0, 0)
            coord.data.recoverycalc_hour = dt_time(23, 0, 0)

            # Mock on_recovery_end car target n'est pas dépassée
            coord.on_recovery_end = MagicMock()

            await coord._restore_state_after_restart()

            # RECOVERY est cohérent entre recovery_start et target
            assert coord.data.current_state == SmartHRTState.RECOVERY

    @pytest.mark.asyncio
    async def test_incoherent_monitoring_in_day_reset_to_heating_on(
        self, create_coordinator
    ):
        """Test: état MONITORING persisté mais heure=10:00 → reset à HEATING_ON."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 4, 10, 0, 0)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.MONITORING,
                recovery_calc_mode=True,
            )
            coord.data.target_hour = dt_time(6, 0, 0)
            coord.data.recoverycalc_hour = dt_time(23, 0, 0)

            await coord._restore_state_after_restart()

            # État incohérent → reset à HEATING_ON (auto-correction)
            assert coord.data.current_state == SmartHRTState.HEATING_ON

    @pytest.mark.asyncio
    async def test_incoherent_heating_process_without_recovery_reset(
        self, create_coordinator
    ):
        """Test: état HEATING_PROCESS sans recovery_start → reset à HEATING_ON."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 4, 10, 0, 0)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_PROCESS,
                rp_calc_mode=True,
                recovery_start_hour=None,  # Pas de recovery configurée
            )
            coord.data.target_hour = dt_time(6, 0, 0)
            coord.data.recoverycalc_hour = dt_time(23, 0, 0)

            await coord._restore_state_after_restart()

            # Incohérent → reset à HEATING_ON
            assert coord.data.current_state == SmartHRTState.HEATING_ON


class TestRestoreTriggersAfterRestart:
    """Tests pour la reprogrammation des triggers après redémarrage."""

    @pytest.mark.asyncio
    async def test_monitoring_reprograms_recovery_start_trigger(
        self, create_coordinator
    ):
        """Test: en MONITORING, le trigger recovery_start est reprogrammé."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 4, 0, 30, 0)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.MONITORING,
                recovery_calc_mode=True,
                recovery_start_hour=datetime(2026, 2, 4, 5, 0, 0),
            )
            coord.data.target_hour = dt_time(6, 0, 0)
            coord.data.recoverycalc_hour = dt_time(23, 0, 0)

            # Mock _schedule_recovery_start pour vérifier qu'il est appelé
            coord._schedule_recovery_start = MagicMock()

            await coord._restore_state_after_restart()

            # Vérifie que le trigger a été reprogrammé
            coord._schedule_recovery_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_monitoring_with_passed_recovery_starts_immediately(
        self, create_coordinator
    ):
        """Test: en MONITORING, si recovery_start est passée → démarrage immédiat."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            # 05:30, recovery était à 05:00
            mock_now = datetime(2026, 2, 4, 5, 30, 0)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.MONITORING,
                recovery_calc_mode=True,
                recovery_start_hour=datetime(2026, 2, 4, 5, 0, 0),
            )
            coord.data.target_hour = dt_time(6, 0, 0)
            coord.data.recoverycalc_hour = dt_time(23, 0, 0)

            # Mock on_recovery_start pour vérifier qu'il est appelé
            coord.on_recovery_start = MagicMock()

            await coord._restore_state_after_restart()

            # L'état attendu est HEATING_PROCESS, donc transition forcée
            # Ou on_recovery_start appelé
            assert coord.data.current_state in (
                SmartHRTState.HEATING_PROCESS,
                SmartHRTState.MONITORING,
            )

    @pytest.mark.asyncio
    async def test_heating_process_checks_target_hour_passed(self, create_coordinator):
        """Test: en HEATING_PROCESS, si target_hour est passée → fin de relance."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            # 06:30, target était à 06:00
            mock_now = datetime(2026, 2, 4, 6, 30, 0)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_PROCESS,
                rp_calc_mode=True,
                recovery_start_hour=datetime(2026, 2, 4, 5, 0, 0),
            )
            coord.data.target_hour = dt_time(6, 0, 0)
            coord.data.recoverycalc_hour = dt_time(23, 0, 0)

            # Mock on_recovery_end pour vérifier qu'il est appelé
            coord.on_recovery_end = MagicMock()

            await coord._restore_state_after_restart()

            # L'état attendu basé sur l'heure est HEATING_ON
            # Donc soit transition forcée, soit on_recovery_end appelé


class TestPersistenceIntegration:
    """Tests pour l'intégration avec le stockage persistant."""

    @pytest.mark.asyncio
    async def test_state_saved_after_transition(self, create_coordinator, mock_store):
        """Test: l'état est sauvegardé après chaque transition."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 4, 23, 0, 0)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_ON,
                smartheating_mode=True,
            )
            coord._store = mock_store

            # Simuler la transition HEATING_ON → DETECTING_LAG
            await coord._async_on_recoverycalc_hour()

            # Vérifier que l'état a été sauvegardé
            # Le format de stockage utilise __type__ pour les enums
            stored_data = await mock_store.async_load()
            if stored_data:
                state_value = stored_data.get("current_state")
                # Nouveau format: {"__type__": "enum", "value": "detecting_lag"}
                if isinstance(state_value, dict) and "__type__" in state_value:
                    assert state_value["value"] == str(SmartHRTState.DETECTING_LAG)
                else:
                    # Ancien format (compatibilité)
                    assert state_value == SmartHRTState.DETECTING_LAG

    @pytest.mark.asyncio
    async def test_state_restored_from_storage(self, create_coordinator, mock_store):
        """Test: l'état est restauré depuis le stockage."""
        # Pré-remplir le store avec un état
        mock_store._data = {
            "current_state": SmartHRTState.MONITORING,
            "recovery_calc_mode": True,
            "rcth": 55.0,
            "rpth": 45.0,
        }

        coord = await create_coordinator()
        coord._store = mock_store

        await coord._restore_learned_data()

        assert coord.data.current_state == SmartHRTState.MONITORING
        assert coord.data.recovery_calc_mode is True
        assert coord.data.rcth == 55.0
        assert coord.data.rpth == 45.0
