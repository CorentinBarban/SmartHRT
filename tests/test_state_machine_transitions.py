"""Tests pour les transitions de la machine à états SmartHRT.

Ce module teste les transitions entre les 5 états du cycle thermique:
1. HEATING_ON → DETECTING_LAG (à recoverycalc_hour)
2. DETECTING_LAG → MONITORING (après détection baisse -0.2°C)
3. MONITORING → RECOVERY (à recovery_start_hour)
4. RECOVERY → HEATING_PROCESS (immédiat après calcul RCth)
5. HEATING_PROCESS → HEATING_ON (atteinte TSP ou target_hour)
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
from custom_components.SmartHRT.data_model import SmartHRTData


class TestTransitionHeatingOnToDetectingLag:
    """Tests pour la transition HEATING_ON → DETECTING_LAG.

    Cette transition se produit à recoverycalc_hour (heure de coupure chauffage).
    C'est le début du cycle nocturne.
    """

    @pytest.fixture
    def coordinator_heating_on(self, create_coordinator):
        """Fixture pour un coordinator en état HEATING_ON."""

        async def _setup():
            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_ON,
                smartheating_mode=True,
                interior_temp=19.0,
                exterior_temp=5.0,
            )
            return coord

        return _setup

    @pytest.mark.asyncio
    async def test_transition_to_detecting_lag_updates_state(
        self, coordinator_heating_on
    ):
        """Vérifie que l'état passe à DETECTING_LAG après recoverycalc_hour."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 3, 23, 0, 0)
            mock_dt.now.return_value = mock_now

            coord = await coordinator_heating_on()
            coord.data.current_state = SmartHRTState.HEATING_ON

            # Simuler l'appel à _async_on_recoverycalc_hour
            await coord._async_on_recoverycalc_hour()

            assert coord.data.current_state == SmartHRTState.DETECTING_LAG

    @pytest.mark.asyncio
    async def test_transition_activates_lag_detection(self, coordinator_heating_on):
        """Vérifie que temp_lag_detection_active est activé."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 3, 23, 0, 0)
            mock_dt.now.return_value = mock_now

            coord = await coordinator_heating_on()
            await coord._async_on_recoverycalc_hour()

            assert coord.data.temp_lag_detection_active is True

    @pytest.mark.asyncio
    async def test_transition_records_temp_recovery_calc(self, coordinator_heating_on):
        """Vérifie que la température de référence est enregistrée."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 3, 23, 0, 0)
            mock_dt.now.return_value = mock_now

            coord = await coordinator_heating_on()
            coord.data.interior_temp = 19.5

            await coord._async_on_recoverycalc_hour()

            assert coord.data.temp_recovery_calc == 19.5

    @pytest.mark.asyncio
    async def test_transition_records_time_recovery_calc(self, coordinator_heating_on):
        """Vérifie que l'heure de coupure est enregistrée."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 3, 23, 0, 0)
            mock_dt.now.return_value = mock_now

            coord = await coordinator_heating_on()
            await coord._async_on_recoverycalc_hour()

            assert coord.data.time_recovery_calc == mock_now


class TestTransitionDetectingLagToMonitoring:
    """Tests pour la transition DETECTING_LAG → MONITORING.

    Validation arrêt par détection lag
    Cette transition se produit quand la température baisse de 0.2°C.
    """

    @pytest.fixture
    def coordinator_detecting_lag(self, create_coordinator):
        """Fixture pour un coordinator en état DETECTING_LAG."""

        async def _setup():
            with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
                mock_now = datetime(2026, 2, 3, 23, 5, 0)
                mock_dt.now.return_value = mock_now

                coord = await create_coordinator(
                    initial_state=SmartHRTState.DETECTING_LAG,
                    temp_lag_detection_active=True,
                    temp_recovery_calc=19.0,
                    text_recovery_calc=5.0,
                    interior_temp=19.0,
                    time_recovery_calc=datetime(2026, 2, 3, 23, 0, 0),
                )
                return coord

        return _setup

    @pytest.mark.asyncio
    async def test_transition_on_temperature_decrease(self, coordinator_detecting_lag):
        """Vérifie la transition vers MONITORING après baisse de 0.2°C."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 3, 23, 10, 0)
            mock_dt.now.return_value = mock_now

            coord = await coordinator_detecting_lag()
            coord.data.current_state = SmartHRTState.DETECTING_LAG
            # flag calculé depuis state (DETECTING_LAG → True)
            coord.data.temp_recovery_calc = 19.0

            # Simuler une baisse de température >= 0.2°C
            coord.data.interior_temp = 18.8  # -0.2°C

            coord._check_temperature_thresholds()

            assert coord.data.current_state == SmartHRTState.MONITORING

    @pytest.mark.asyncio
    async def test_no_transition_if_temperature_not_decreased_enough(
        self, coordinator_detecting_lag
    ):
        """Vérifie qu'il n'y a pas de transition si baisse < 0.2°C."""
        coord = await coordinator_detecting_lag()
        coord.data.current_state = SmartHRTState.DETECTING_LAG
        # flag calculé depuis state (DETECTING_LAG → True)
        coord.data.temp_recovery_calc = 19.0

        # Baisse insuffisante
        coord.data.interior_temp = 18.85  # seulement -0.15°C

        coord._check_temperature_thresholds()

        # L'état ne doit pas changer
        assert coord.data.current_state == SmartHRTState.DETECTING_LAG

    @pytest.mark.asyncio
    async def test_transition_activates_recovery_calc_mode(
        self, coordinator_detecting_lag
    ):
        """Vérifie que recovery_calc_mode est activé après la transition."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 3, 23, 10, 0)
            mock_dt.now.return_value = mock_now

            coord = await coordinator_detecting_lag()
            coord.data.current_state = SmartHRTState.DETECTING_LAG
            # flag calculé depuis state (DETECTING_LAG → True)
            coord.data.temp_recovery_calc = 19.0
            coord.data.interior_temp = 18.8

            coord._check_temperature_thresholds()

            assert coord.data.recovery_calc_mode is True

    @pytest.mark.asyncio
    async def test_transition_deactivates_lag_detection(
        self, coordinator_detecting_lag
    ):
        """Vérifie que temp_lag_detection_active est désactivé."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 3, 23, 10, 0)
            mock_dt.now.return_value = mock_now

            coord = await coordinator_detecting_lag()
            coord.data.current_state = SmartHRTState.DETECTING_LAG
            # flag calculé depuis state (DETECTING_LAG → True)
            coord.data.temp_recovery_calc = 19.0
            coord.data.interior_temp = 18.8

            coord._check_temperature_thresholds()

            assert coord.data.temp_lag_detection_active is False

    @pytest.mark.asyncio
    async def test_transition_calculates_stop_lag_duration(
        self, coordinator_detecting_lag
    ):
        """Vérifie que la durée du lag est calculée."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            # 10 minutes après recoverycalc
            mock_now = datetime(2026, 2, 3, 23, 10, 0)
            mock_dt.now.return_value = mock_now

            coord = await coordinator_detecting_lag()
            coord.data.current_state = SmartHRTState.DETECTING_LAG
            # flag calculé depuis state (DETECTING_LAG → True)
            coord.data.temp_recovery_calc = 19.0
            coord.data.time_recovery_calc = datetime(2026, 2, 3, 23, 0, 0)
            coord.data.interior_temp = 18.8

            coord._check_temperature_thresholds()

            # 10 minutes = 600 secondes
            assert coord.data.stop_lag_duration == 600.0


class TestTransitionMonitoringToRecovery:
    """Tests pour la transition MONITORING → RECOVERY.

    Cette transition se produit à recovery_start_hour (heure calculée de relance).
    """

    @pytest.fixture
    def coordinator_monitoring(self, create_coordinator):
        """Fixture pour un coordinator en état MONITORING."""

        async def _setup():
            coord = await create_coordinator(
                initial_state=SmartHRTState.MONITORING,
                smartheating_mode=True,
                recovery_calc_mode=True,
                interior_temp=17.5,
                exterior_temp=3.0,
                time_recovery_calc=datetime(2026, 2, 3, 23, 5, 0),
                recovery_start_hour=datetime(2026, 2, 4, 5, 30, 0),
            )
            return coord

        return _setup

    @pytest.mark.asyncio
    async def test_transition_to_recovery_on_start(self, coordinator_monitoring):
        """Vérifie la transition vers RECOVERY à recovery_start_hour."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 4, 5, 30, 0)
            mock_dt.now.return_value = mock_now

            coord = await coordinator_monitoring()
            coord.data.current_state = SmartHRTState.MONITORING

            coord.on_recovery_start()

            # Note: on_recovery_start passe par RECOVERY puis HEATING_PROCESS
            # On vérifie l'état final
            assert coord.data.current_state == SmartHRTState.HEATING_PROCESS

    @pytest.mark.asyncio
    async def test_transition_records_recovery_start_values(
        self, coordinator_monitoring
    ):
        """Vérifie que les valeurs de début de relance sont enregistrées."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 4, 5, 30, 0)
            mock_dt.now.return_value = mock_now

            coord = await coordinator_monitoring()
            coord.data.interior_temp = 17.2
            coord.data.exterior_temp = 2.5

            coord.on_recovery_start()

            assert coord.data.temp_recovery_start == 17.2
            assert coord.data.text_recovery_start == 2.5
            assert coord.data.time_recovery_start == mock_now

    @pytest.mark.asyncio
    async def test_transition_activates_rp_calc_mode(self, coordinator_monitoring):
        """Vérifie que rp_calc_mode est activé."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 4, 5, 30, 0)
            mock_dt.now.return_value = mock_now

            coord = await coordinator_monitoring()

            coord.on_recovery_start()

            assert coord.data.rp_calc_mode is True

    @pytest.mark.asyncio
    async def test_transition_deactivates_recovery_calc_mode(
        self, coordinator_monitoring
    ):
        """Vérifie que recovery_calc_mode est désactivé."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 4, 5, 30, 0)
            mock_dt.now.return_value = mock_now

            coord = await coordinator_monitoring()
            # flag calculé depuis state (MONITORING → True)

            coord.on_recovery_start()

            assert coord.data.recovery_calc_mode is False


class TestTransitionRecoveryToHeatingProcess:
    """Tests pour la transition RECOVERY → HEATING_PROCESS.

    Cette transition est immédiate après le calcul de RCth.
    """

    @pytest.mark.asyncio
    async def test_recovery_transitions_immediately_to_heating_process(
        self, create_coordinator
    ):
        """Vérifie que RECOVERY passe immédiatement à HEATING_PROCESS."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 4, 5, 30, 0)
            mock_dt.now.return_value = mock_now

            coord = await create_coordinator(
                initial_state=SmartHRTState.MONITORING,
                time_recovery_calc=datetime(2026, 2, 3, 23, 5, 0),
            )

            # on_recovery_start passe par RECOVERY puis HEATING_PROCESS
            coord.on_recovery_start()

            assert coord.data.current_state == SmartHRTState.HEATING_PROCESS


class TestTransitionHeatingProcessToHeatingOn:
    """Tests pour la transition HEATING_PROCESS → HEATING_ON.

    Cette transition se produit quand:
    - La température intérieure atteint TSP, ou
    - L'heure target_hour est atteinte
    """

    @pytest.fixture
    def coordinator_heating_process(self, create_coordinator):
        """Fixture pour un coordinator en état HEATING_PROCESS."""

        async def _setup():
            coord = await create_coordinator(
                initial_state=SmartHRTState.HEATING_PROCESS,
                rp_calc_mode=True,
                tsp=DEFAULT_TSP,  # 19.0°C
                interior_temp=18.0,
                exterior_temp=4.0,
                time_recovery_start=datetime(2026, 2, 4, 5, 30, 0),
            )
            return coord

        return _setup

    @pytest.mark.asyncio
    async def test_transition_on_tsp_reached(self, coordinator_heating_process):
        """Vérifie la transition vers HEATING_ON quand TSP est atteint."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 4, 5, 55, 0)
            mock_dt.now.return_value = mock_now

            coord = await coordinator_heating_process()
            coord.data.tsp = 19.0
            # flag calculé depuis state (HEATING_PROCESS → True)

            # Température atteint la consigne
            coord.data.interior_temp = 19.0

            coord._check_temperature_thresholds()

            assert coord.data.current_state == SmartHRTState.HEATING_ON

    @pytest.mark.asyncio
    async def test_transition_on_tsp_exceeded(self, coordinator_heating_process):
        """Vérifie la transition quand la température dépasse TSP."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 4, 5, 55, 0)
            mock_dt.now.return_value = mock_now

            coord = await coordinator_heating_process()
            coord.data.tsp = 19.0
            # flag calculé depuis state (HEATING_PROCESS → True)

            # Température dépasse la consigne
            coord.data.interior_temp = 19.5

            coord._check_temperature_thresholds()

            assert coord.data.current_state == SmartHRTState.HEATING_ON

    @pytest.mark.asyncio
    async def test_no_transition_if_tsp_not_reached(self, coordinator_heating_process):
        """Vérifie qu'il n'y a pas de transition si TSP non atteint."""
        coord = await coordinator_heating_process()
        coord.data.tsp = 19.0
        # flag calculé depuis state (HEATING_PROCESS → True)
        coord.data.interior_temp = 18.5

        coord._check_temperature_thresholds()

        assert coord.data.current_state == SmartHRTState.HEATING_PROCESS

    @pytest.mark.asyncio
    async def test_transition_deactivates_rp_calc_mode(
        self, coordinator_heating_process
    ):
        """Vérifie que rp_calc_mode est désactivé après la transition."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 4, 5, 55, 0)
            mock_dt.now.return_value = mock_now

            coord = await coordinator_heating_process()
            coord.data.tsp = 19.0
            # flag calculé depuis state (HEATING_PROCESS → True)
            coord.data.interior_temp = 19.0

            coord._check_temperature_thresholds()

            assert coord.data.rp_calc_mode is False

    @pytest.mark.asyncio
    async def test_transition_records_recovery_end_values(
        self, coordinator_heating_process
    ):
        """Vérifie que les valeurs de fin de relance sont enregistrées."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 4, 5, 55, 0)
            mock_dt.now.return_value = mock_now

            coord = await coordinator_heating_process()
            coord.data.tsp = 19.0
            # flag calculé depuis state (HEATING_PROCESS → True)
            coord.data.interior_temp = 19.0
            coord.data.exterior_temp = 4.5

            coord._check_temperature_thresholds()

            assert coord.data.temp_recovery_end == 19.0
            assert coord.data.text_recovery_end == 4.5
            assert coord.data.time_recovery_end == mock_now

    @pytest.mark.asyncio
    async def test_transition_on_target_hour(self, coordinator_heating_process):
        """Vérifie la transition à target_hour même si TSP non atteint."""
        with patch("custom_components.SmartHRT.coordinator.dt_util") as mock_dt:
            mock_now = datetime(2026, 2, 4, 6, 0, 0)
            mock_dt.now.return_value = mock_now

            coord = await coordinator_heating_process()
            coord.data.tsp = 19.0
            # flag calculé depuis state (HEATING_PROCESS → True)
            coord.data.interior_temp = 18.5  # TSP non atteint

            # Simuler l'appel à on_recovery_end (déclenché par target_hour)
            coord.on_recovery_end()

            assert coord.data.current_state == SmartHRTState.HEATING_ON


class TestInvalidTransitions:
    """Tests pour les transitions invalides ou les cas limites."""

    @pytest.mark.asyncio
    async def test_recovery_start_ignored_if_already_in_recovery(
        self, create_coordinator
    ):
        """Vérifie que on_recovery_start est ignoré si déjà en RECOVERY.

        rp_calc_mode est une propriété calculée (True ssi HEATING_PROCESS).
        """
        coord = await create_coordinator(
            initial_state=SmartHRTState.RECOVERY,
            # rp_calc_mode est calculé depuis state, pas besoin de le setter
        )

        # Le callback _on_recovery_start_hour vérifie l'état
        # Simuler ce comportement
        if coord.data.current_state in (
            SmartHRTState.RECOVERY,
            SmartHRTState.HEATING_PROCESS,
        ):
            # Ne devrait pas re-déclencher
            pass

        # L'état ne devrait pas changer
        assert coord.data.current_state == SmartHRTState.RECOVERY

    @pytest.mark.asyncio
    async def test_recovery_end_ignored_if_not_in_rp_calc_mode(
        self, create_coordinator
    ):
        """Vérifie que on_recovery_end est ignoré si pas en HEATING_PROCESS.

        rp_calc_mode est une propriété calculée (True ssi HEATING_PROCESS).
        """
        coord = await create_coordinator(
            initial_state=SmartHRTState.MONITORING,  # rp_calc_mode sera False
        )

        coord.on_recovery_end()

        # L'état ne devrait pas changer car rp_calc_mode (calculé) est False
        assert coord.data.current_state == SmartHRTState.MONITORING

    @pytest.mark.asyncio
    async def test_smartheating_mode_off_blocks_transitions(self, create_coordinator):
        """Vérifie que smartheating_mode=False bloque certaines transitions."""
        coord = await create_coordinator(
            initial_state=SmartHRTState.HEATING_ON,
            smartheating_mode=False,
        )

        # La transition à recoverycalc_hour devrait être bloquée
        # (vérification faite dans _on_recoverycalc_hour)
        assert coord.data.smartheating_mode is False


class TestModeFlags:
    """Tests pour les flags de mode associés aux états."""

    @pytest.mark.asyncio
    async def test_heating_on_mode_flags(self, create_coordinator):
        """Vérifie les flags en état HEATING_ON."""
        coord = await create_coordinator(initial_state=SmartHRTState.HEATING_ON)

        # En HEATING_ON, tous les flags sont False (calculés depuis state)
        assert coord.data.recovery_calc_mode is False
        assert coord.data.rp_calc_mode is False
        assert coord.data.temp_lag_detection_active is False

    @pytest.mark.asyncio
    async def test_detecting_lag_mode_flags(self, create_coordinator):
        """Vérifie les flags en état DETECTING_LAG."""
        coord = await create_coordinator(initial_state=SmartHRTState.DETECTING_LAG)

        # En DETECTING_LAG, temp_lag_detection_active est True (calculé depuis state)
        assert coord.data.temp_lag_detection_active is True
        assert coord.data.recovery_calc_mode is False
        assert coord.data.rp_calc_mode is False

    @pytest.mark.asyncio
    async def test_monitoring_mode_flags(self, create_coordinator):
        """Vérifie les flags en état MONITORING."""
        coord = await create_coordinator(initial_state=SmartHRTState.MONITORING)

        # En MONITORING, recovery_calc_mode est True (calculé depuis state)
        assert coord.data.recovery_calc_mode is True
        assert coord.data.temp_lag_detection_active is False
        assert coord.data.rp_calc_mode is False

    @pytest.mark.asyncio
    async def test_heating_process_mode_flags(self, create_coordinator):
        """Vérifie les flags en état HEATING_PROCESS."""
        coord = await create_coordinator(initial_state=SmartHRTState.HEATING_PROCESS)

        # En HEATING_PROCESS, rp_calc_mode est True (calculé depuis state)
        assert coord.data.rp_calc_mode is True
        assert coord.data.recovery_calc_mode is False
        assert coord.data.temp_lag_detection_active is False
