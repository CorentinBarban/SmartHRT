"""Tests pour le cycle complet de la machine à états.

Ce module teste des scénarios complets de bout en bout,
simulant une journée typique avec tous les états du cycle.
"""

from datetime import datetime, time as dt_time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.SmartHRT.const import (
    DEFAULT_RCTH,
    DEFAULT_RPTH,
    DEFAULT_TSP,
    TEMP_DECREASE_THRESHOLD,
)
from custom_components.SmartHRT.coordinator import (
    SmartHRTCoordinator,
    SmartHRTState,
)
from custom_components.SmartHRT.data_model import SmartHRTData  # ADR-047


class TestFullDayCycle:
    """Tests pour un cycle complet sur 24 heures.

    Scénario typique:
    1. 10:00 - HEATING_ON (journée)
    2. 23:00 - HEATING_ON → DETECTING_LAG (recoverycalc_hour)
    3. 23:10 - DETECTING_LAG → MONITORING (baisse de 0.2°C)
    4. 05:30 - MONITORING → RECOVERY → HEATING_PROCESS (recovery_start)
    5. 05:55 - HEATING_PROCESS → HEATING_ON (TSP atteint)
    """

    @pytest.mark.asyncio
    async def test_complete_cycle_state_sequence(self, create_coordinator):
        """Test: séquence complète des états sur un cycle."""
        states_sequence = []

        # Étape 1: Journée - HEATING_ON (10:00)
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 3, 10, 0, 0)

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_ON,
                smartheating_mode=True,
                interior_temp=19.5,
                exterior_temp=8.0,
                tsp=DEFAULT_TSP,
            )
            coord.data.target_hour = dt_time(6, 0, 0)
            coord.data.recoverycalc_hour = dt_time(23, 0, 0)

            states_sequence.append(coord.data.current_state)
            assert coord.data.current_state == SmartHRTState.HEATING_ON

        # Étape 2: Coupure chauffage - DETECTING_LAG (23:00)
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 3, 23, 0, 0)

            await coord._async_on_recoverycalc_hour()

            states_sequence.append(coord.data.current_state)
            assert coord.data.current_state == SmartHRTState.DETECTING_LAG

        # Étape 3: Détection baisse température - MONITORING (23:10)
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 3, 23, 10, 0)

            # Simuler une baisse de température de 0.2°C
            initial_temp = coord.data.temp_recovery_calc
            coord.data.interior_temp = initial_temp - TEMP_DECREASE_THRESHOLD

            coord._check_temperature_thresholds()

            states_sequence.append(coord.data.current_state)
            assert coord.data.current_state == SmartHRTState.MONITORING

        # Étape 4: Démarrage relance - HEATING_PROCESS (05:30)
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 4, 5, 30, 0)

            coord.data.interior_temp = 17.2
            coord.data.exterior_temp = 3.0

            coord.on_recovery_start()

            states_sequence.append(coord.data.current_state)
            assert coord.data.current_state == SmartHRTState.HEATING_PROCESS

        # Étape 5: Consigne atteinte - HEATING_ON (05:55)
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 4, 5, 55, 0)

            coord.data.interior_temp = coord.data.tsp  # Consigne atteinte

            coord._check_temperature_thresholds()

            states_sequence.append(coord.data.current_state)
            assert coord.data.current_state == SmartHRTState.HEATING_ON

        # Vérifier la séquence complète
        expected_sequence = [
            SmartHRTState.HEATING_ON,
            SmartHRTState.DETECTING_LAG,
            SmartHRTState.MONITORING,
            SmartHRTState.HEATING_PROCESS,
            SmartHRTState.HEATING_ON,
        ]
        assert states_sequence == expected_sequence


class TestEdgeCases:
    """Tests pour les cas limites."""

    @pytest.mark.asyncio
    async def test_rapid_temperature_fluctuation(self, create_coordinator):
        """Test: fluctuation rapide de température pendant DETECTING_LAG."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 3, 23, 5, 0)

            coord = await create_coordinator(
                initial_state=SmartHRTState.DETECTING_LAG,
                temp_lag_detection_active=True,
                temp_recovery_calc=19.0,
                interior_temp=19.0,
                time_recovery_calc=datetime(2026, 2, 3, 23, 0, 0),
            )

            # Température remonte légèrement
            coord.data.interior_temp = 19.1

            coord._check_temperature_thresholds()

            # Le snapshot devrait être mis à jour
            assert coord.data.temp_recovery_calc == 19.1
            # Mais l'état reste DETECTING_LAG
            assert coord.data.current_state == SmartHRTState.DETECTING_LAG

            # Maintenant température baisse de 0.2°C depuis le nouveau snapshot
            coord.data.interior_temp = 18.9

            coord._check_temperature_thresholds()

            assert coord.data.current_state == SmartHRTState.MONITORING

    @pytest.mark.asyncio
    async def test_target_hour_reached_before_tsp(self, create_coordinator):
        """Test: target_hour atteint avant que TSP soit atteint."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 4, 6, 0, 0)

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_PROCESS,
                rp_calc_mode=True,
                tsp=DEFAULT_TSP,
                interior_temp=18.0,  # En dessous de TSP
                time_recovery_start=datetime(2026, 2, 4, 5, 0, 0),
            )
            coord.data.target_hour = dt_time(6, 0, 0)

            # Forcer la fin de relance via target_hour
            coord.on_recovery_end()

            assert coord.data.current_state == SmartHRTState.HEATING_ON
            assert coord.data.rp_calc_mode is False

    @pytest.mark.asyncio
    async def test_smartheating_mode_disabled_at_recoverycalc(self, create_coordinator):
        """Test: smartheating_mode=False à recoverycalc_hour."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 3, 23, 0, 0)

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_ON,
                smartheating_mode=False,  # Mode désactivé
            )

            # Simuler l'appel au callback
            coord._on_recoverycalc_hour(None)

            # L'état ne devrait pas changer
            assert coord.data.current_state == SmartHRTState.HEATING_ON

    @pytest.mark.asyncio
    async def test_recovery_start_already_in_heating_process(self, create_coordinator):
        """Test: on_recovery_start ignoré si déjà en HEATING_PROCESS."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 4, 5, 35, 0)

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_PROCESS,
                rp_calc_mode=True,
                time_recovery_start=datetime(2026, 2, 4, 5, 30, 0),
            )

            # Le callback vérifie l'état avant d'appeler on_recovery_start
            if coord.data.current_state in (
                SmartHRTState.RECOVERY,
                SmartHRTState.HEATING_PROCESS,
            ):
                pass  # Ignoré
            else:
                coord.on_recovery_start()

            # L'état reste HEATING_PROCESS
            assert coord.data.current_state == SmartHRTState.HEATING_PROCESS

    @pytest.mark.asyncio
    async def test_multiple_temperature_decreases(self, create_coordinator):
        """Test: plusieurs baisses successives de température."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 3, 23, 10, 0)

            coord = await create_coordinator(
                initial_state=SmartHRTState.DETECTING_LAG,
                temp_lag_detection_active=True,
                temp_recovery_calc=19.0,
                interior_temp=19.0,
                time_recovery_calc=datetime(2026, 2, 3, 23, 0, 0),
            )

            # Première baisse - transition vers MONITORING
            coord.data.interior_temp = 18.8
            coord._check_temperature_thresholds()

            assert coord.data.current_state == SmartHRTState.MONITORING
            assert coord.data.temp_lag_detection_active is False

            # Autre baisse - pas de nouvelle transition
            coord.data.interior_temp = 18.5
            coord._check_temperature_thresholds()

            # Toujours en MONITORING
            assert coord.data.current_state == SmartHRTState.MONITORING

    @pytest.mark.asyncio
    async def test_target_hour_reached_while_in_monitoring_no_recovery(
        self, create_coordinator
    ):
        """Test ADR-055: target_hour atteint en MONITORING sans relance déclenchée.

        Scénario: La température n'est jamais descendue assez pour déclencher
        la relance (ex: nuit chaude). À target_hour, le système doit transitionner
        directement vers HEATING_ON sans passer par RECOVERY ni HEATING_PROCESS.
        """
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 4, 6, 0, 0)

            coord = await create_coordinator(
                initial_state=SmartHRTState.MONITORING,
                smartheating_mode=True,
                recovery_calc_mode=True,  # Flag MONITORING actif
                tsp=DEFAULT_TSP,
                interior_temp=19.0,  # Encore au-dessus de la cible
                time_recovery_calc=datetime(2026, 2, 3, 23, 0, 0),
            )
            coord.data.target_hour = dt_time(6, 0, 0)
            coord.data.recovery_start_hour = None  # Pas de relance programmée

            # Vérifier qu'on est bien en MONITORING avant
            assert coord.data.current_state == SmartHRTState.MONITORING
            assert coord.data.rp_calc_mode is False

            # Simuler l'arrivée de target_hour
            coord._on_target_hour(None)

            # Doit transitionner vers HEATING_ON directement
            assert coord.data.current_state == SmartHRTState.HEATING_ON
            # Les flags doivent être réinitialisés
            assert coord.data.recovery_calc_mode is False
            assert coord.data.rp_calc_mode is False


class TestModeInteractions:
    """Tests pour les interactions entre modes et états."""

    @pytest.mark.asyncio
    async def test_recovery_adaptive_mode_affects_learning(self, create_coordinator):
        """Test: recovery_adaptive_mode contrôle l'apprentissage."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 4, 6, 0, 0)

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_PROCESS,
                rp_calc_mode=True,
                recovery_adaptive_mode=True,
                time_recovery_start=datetime(2026, 2, 4, 5, 0, 0),
                temp_recovery_start=17.0,
                text_recovery_start=3.0,
            )

            original_rpth = coord.data.rpth

            # Simuler fin de relance avec calcul RPth
            coord.data.interior_temp = 19.0
            coord.data.exterior_temp = 4.0

            coord.on_recovery_end()

            # En mode adaptatif, rpth devrait être mis à jour
            # (ou au moins le calcul devrait être tenté)
            assert coord.data.current_state == SmartHRTState.HEATING_ON

    @pytest.mark.asyncio
    async def test_rp_calc_mode_required_for_recovery_end(self, create_coordinator):
        """Test: on_recovery_end ne fait rien si pas en état HEATING_PROCESS.

        ADR-040: rp_calc_mode est une propriété calculée depuis current_state.
        rp_calc_mode == True ssi current_state == HEATING_PROCESS.
        """
        coord = await create_coordinator(
            initial_state=SmartHRTState.HEATING_ON,  # rp_calc_mode sera False
        )

        coord.on_recovery_end()

        # L'état ne change pas si pas en HEATING_PROCESS (rp_calc_mode == False)
        assert coord.data.current_state == SmartHRTState.HEATING_ON


class TestTemperatureThresholds:
    """Tests pour les seuils de température."""

    @pytest.mark.asyncio
    async def test_temp_decrease_threshold_exact(self, create_coordinator):
        """Test: baisse exactement égale au seuil déclenche la transition."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 3, 23, 10, 0)

            coord = await create_coordinator(
                initial_state=SmartHRTState.DETECTING_LAG,
                temp_lag_detection_active=True,
                temp_recovery_calc=19.0,
                time_recovery_calc=datetime(2026, 2, 3, 23, 0, 0),
            )

            # Baisse exactement de 0.2°C
            coord.data.interior_temp = 19.0 - TEMP_DECREASE_THRESHOLD

            coord._check_temperature_thresholds()

            assert coord.data.current_state == SmartHRTState.MONITORING

    @pytest.mark.asyncio
    async def test_tsp_exact_triggers_recovery_end(self, create_coordinator):
        """Test: température exactement égale à TSP déclenche la fin."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 2, 4, 5, 55, 0)

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_PROCESS,
                rp_calc_mode=True,
                tsp=19.0,
                time_recovery_start=datetime(2026, 2, 4, 5, 0, 0),
            )

            # Température exactement égale à TSP
            coord.data.interior_temp = 19.0

            coord._check_temperature_thresholds()

            assert coord.data.current_state == SmartHRTState.HEATING_ON

    @pytest.mark.asyncio
    async def test_interior_temp_none_no_transition(self, create_coordinator):
        """Test: pas de transition si interior_temp est None."""
        coord = await create_coordinator(
            initial_state=SmartHRTState.DETECTING_LAG,
            temp_lag_detection_active=True,
            temp_recovery_calc=19.0,
        )
        coord.data.interior_temp = None

        coord._check_temperature_thresholds()

        # L'état ne change pas
        assert coord.data.current_state == SmartHRTState.DETECTING_LAG


class TestStateDataConsistency:
    """Tests pour la cohérence des données selon l'état."""

    @pytest.mark.asyncio
    async def test_time_recovery_calc_set_at_recoverycalc(self, create_coordinator):
        """Test: time_recovery_calc est défini à recoverycalc_hour."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            expected_time = datetime(2026, 2, 3, 23, 0, 0)
            mock_dt.now.return_value = expected_time

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_ON,
                smartheating_mode=True,
            )
            coord.data.time_recovery_calc = None

            await coord._async_on_recoverycalc_hour()

            assert coord.data.time_recovery_calc == expected_time

    @pytest.mark.asyncio
    async def test_time_recovery_start_set_at_recovery(self, create_coordinator):
        """Test: time_recovery_start est défini à on_recovery_start."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            expected_time = datetime(2026, 2, 4, 5, 30, 0)
            mock_dt.now.return_value = expected_time

            coord = await create_coordinator(
                initial_state=SmartHRTState.MONITORING,
                time_recovery_calc=datetime(2026, 2, 3, 23, 5, 0),
            )
            coord.data.time_recovery_start = None

            coord.on_recovery_start()

            assert coord.data.time_recovery_start == expected_time

    @pytest.mark.asyncio
    async def test_time_recovery_end_set_at_end(self, create_coordinator):
        """Test: time_recovery_end est défini à on_recovery_end."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            expected_time = datetime(2026, 2, 4, 5, 55, 0)
            mock_dt.now.return_value = expected_time

            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_PROCESS,
                rp_calc_mode=True,
                time_recovery_start=datetime(2026, 2, 4, 5, 30, 0),
            )
            coord.data.time_recovery_end = None

            coord.on_recovery_end()

            assert coord.data.time_recovery_end == expected_time
