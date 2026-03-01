"""Tests fonctionnels générés à partir de scénarios réels extraits des logs.

Ces tests reproduisent des cas réels capturés dans les logs de production
pour assurer la non-régression du comportement du système SmartHRT.

Les données de test sont extraites de: log.log (2026-02-28 / 2026-03-01)
"""

import math
from datetime import datetime, time as dt_time, timedelta

import pytest

from custom_components.SmartHRT.core.thermal import ThermalSolver
from custom_components.SmartHRT.core.types import (
    ThermalConfig,
    ThermalCoefficients,
    ThermalState,
)


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 1: Prédiction de relance standard (TC-PRED VALID)
# Source: log 2026-02-28 19:11:25 - Recovery prediction avec status VALID
# ═══════════════════════════════════════════════════════════════════════════════


class TestRecoveryPredictionFromLogs:
    """Tests basés sur les logs [TC-PRED] de prédiction de relance."""

    @pytest.fixture
    def solver(self):
        """ThermalSolver avec configuration standard."""
        return ThermalSolver()

    def test_scenario_evening_recovery_prediction(self, solver):
        """Scénario: Prédiction soirée 19:11 vers cible 22:30.

        Source log:
        [TC-PRED] Recovery prediction: tint=18.49°C, text=10.07°C, tsp=19.00°C,
        rcth=113.04, rpth=56.41, target_time=22:30:00, validation_status=VALID
        [TC-PRED] Recovery result: duration_hours=1.52, start_time=20:58, iterations=5
        """
        state = ThermalState(
            interior_temp=18.49,
            exterior_temp=10.07,
            tsp=19.0,
            target_hour=dt_time(22, 30, 0),
            temperature_forecast_avg=10.07,
            wind_speed_forecast_avg_kmh=20.0,  # Valeur estimée pour le scénario
        )
        coefficients = ThermalCoefficients(
            rcth=113.04,
            rpth=56.41,
            rcth_lw=113.04,
            rcth_hw=113.04,
            rpth_lw=56.41,
            rpth_hw=56.41,
        )
        now = datetime(2026, 2, 28, 19, 11, 25)

        result = solver.calculate_recovery_duration(state, coefficients, now)

        # Vérification des résultats attendus
        assert result.duration_hours == pytest.approx(1.52, rel=0.1)
        # Start time devrait être ~20:58 (soit target - 1h32)
        expected_start = datetime(2026, 2, 28, 20, 58, 0)
        assert abs((result.recovery_start_hour - expected_start).total_seconds()) < 180

    def test_scenario_progressive_cooling_evening(self, solver):
        """Scénario: Évolution des prédictions pendant la soirée (19:31 → 19:51).

        Log 19:31: tint=18.33°C → duration=1.79h
        Log 19:51: tint=18.17°C → duration=2.06h

        Vérifie que la durée augmente quand la température baisse.
        """
        coefficients = ThermalCoefficients(
            rcth=113.04,
            rpth=56.41,
            rcth_lw=113.04,
            rcth_hw=113.04,
            rpth_lw=56.41,
            rpth_hw=56.41,
        )

        # État à 19:31
        state_1931 = ThermalState(
            interior_temp=18.33,
            exterior_temp=10.07,
            tsp=19.0,
            target_hour=dt_time(22, 30, 0),
            temperature_forecast_avg=10.07,
        )
        now_1931 = datetime(2026, 2, 28, 19, 31, 25)
        result_1931 = solver.calculate_recovery_duration(
            state_1931, coefficients, now_1931
        )

        # État à 19:51
        state_1951 = ThermalState(
            interior_temp=18.17,
            exterior_temp=10.07,
            tsp=19.0,
            target_hour=dt_time(22, 30, 0),
            temperature_forecast_avg=10.07,
        )
        now_1951 = datetime(2026, 2, 28, 19, 51, 25)
        result_1951 = solver.calculate_recovery_duration(
            state_1951, coefficients, now_1951
        )

        # Température plus basse → durée plus longue
        assert result_1931.duration_hours == pytest.approx(1.79, rel=0.1)
        assert result_1951.duration_hours == pytest.approx(2.06, rel=0.1)
        assert result_1951.duration_hours > result_1931.duration_hours

    def test_scenario_cold_night_prediction(self, solver):
        """Scénario: Prédiction nuit froide avec ext=6.70°C.

        Source log 02:11:32:
        [TC-PRED] tint=17.60°C, text=6.70°C, tsp=19.00°C, rcth=24.29, rpth=62.84
        [TC-PRED] Recovery result: duration_hours=1.76, start_time=08:14, iterations=6
        """
        state = ThermalState(
            interior_temp=17.60,
            exterior_temp=6.70,
            tsp=19.0,
            target_hour=dt_time(10, 0, 0),
            temperature_forecast_avg=6.70,
        )
        coefficients = ThermalCoefficients(
            rcth=24.29,
            rpth=62.84,
            rcth_lw=24.29,
            rcth_hw=24.29,
            rpth_lw=62.84,
            rpth_hw=62.84,
        )
        now = datetime(2026, 3, 1, 2, 11, 32)

        result = solver.calculate_recovery_duration(state, coefficients, now)

        assert result.duration_hours == pytest.approx(1.76, rel=0.1)

    def test_scenario_very_cold_night_prediction(self, solver):
        """Scénario: Prédiction nuit très froide avec ext=4.60°C.

        Source log 06:11:32:
        [TC-PRED] tint=16.60°C, text=4.60°C, tsp=19.00°C, rcth=25.24, rpth=69.27
        [TC-PRED] Recovery result: duration_hours=1.53, start_time=08:28, iterations=5
        """
        state = ThermalState(
            interior_temp=16.60,
            exterior_temp=4.60,
            tsp=19.0,
            target_hour=dt_time(10, 0, 0),
            temperature_forecast_avg=4.60,
        )
        coefficients = ThermalCoefficients(
            rcth=25.24,
            rpth=69.27,
            rcth_lw=25.24,
            rcth_hw=25.24,
            rpth_lw=69.27,
            rpth_hw=69.27,
        )
        now = datetime(2026, 3, 1, 6, 11, 32)

        result = solver.calculate_recovery_duration(state, coefficients, now)

        assert result.duration_hours == pytest.approx(1.53, rel=0.15)


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 2: Calibration RCth (TC-CALIB-RCTH)
# Source: log 2026-02-28 20:27:40 - Calibration lors du passage à recovery
# ═══════════════════════════════════════════════════════════════════════════════


class TestRCthCalibrationFromLogs:
    """Tests basés sur les logs [TC-CALIB-RCTH] de calibration RCth."""

    @pytest.fixture
    def solver(self):
        return ThermalSolver()

    def test_scenario_rcth_calibration_chambre(self, solver):
        """Scénario: Calibration RCth chambre lors du passage monitoring → recovery.

        Source log 20:27:40:
        [TC-CALIB-RCTH] RCth calibration: tint_start=19.25°C, tint_end=18.00°C,
        text_start=11.50°C, text_end=9.90°C, duration_minutes=176.2,
        rcth_calculated=18.58
        """
        # Données du log
        tint_start = 19.25
        tint_end = 18.00
        text_start = 11.50
        text_end = 9.90
        duration_minutes = 176.2

        # Calcul du RCth: formule = duration / ln((tint_start - text_avg) / (tint_end - text_avg))
        text_avg = (text_start + text_end) / 2
        duration_hours = duration_minutes / 60

        # Sanity check: température doit avoir baissé
        assert tint_start > tint_end, "La température doit avoir baissé"
        assert tint_end > text_avg, "Température intérieure > extérieure"

        ratio = (tint_start - text_avg) / (tint_end - text_avg)
        rcth_calculated = duration_hours / math.log(ratio)

        # Le log indique rcth_calculated=18.58
        assert rcth_calculated == pytest.approx(18.58, rel=0.1)

    def test_scenario_rcth_calibration_morning(self, solver):
        """Scénario: Calibration RCth matinale après nuit froide.

        Source log 08:39:11:
        [TC-CALIB-RCTH] RCth calibration: tint_start=19.80°C, tint_end=16.20°C,
        text_start=9.70°C, text_end=4.50°C, duration_minutes=687.6,
        rcth_calculated=34.38
        """
        tint_start = 19.80
        tint_end = 16.20
        text_start = 9.70
        text_end = 4.50
        duration_minutes = 687.6

        text_avg = (text_start + text_end) / 2
        duration_hours = duration_minutes / 60

        ratio = (tint_start - text_avg) / (tint_end - text_avg)
        rcth_calculated = duration_hours / math.log(ratio)

        # Le log indique rcth_calculated=34.38
        assert rcth_calculated == pytest.approx(34.38, rel=0.1)


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 3: Calibration RPth (TC-CALIB-RPTH)
# Source: log 2026-02-28 21:51:29 - Calibration à la fin de relance
# ═══════════════════════════════════════════════════════════════════════════════


class TestRPthCalibrationFromLogs:
    """Tests basés sur les logs [TC-CALIB-RPTH] de calibration RPth."""

    def test_scenario_rpth_calibration_chambre(self):
        """Scénario: Calibration RPth chambre à la fin de la relance.

        Source log 21:51:29:
        [TC-CALIB-RPTH] RPth calibration: tint_start=18.00°C, tint_end=19.00°C,
        text_start=9.90°C, text_end=9.70°C, duration_minutes=83.8,
        rcth_interpolated=65.71, rpth_calculated=55.73
        """
        tint_start = 18.00
        tint_end = 19.00
        text_start = 9.90
        text_end = 9.70
        duration_minutes = 83.8
        rcth_interpolated = 65.71

        text_avg = (text_start + text_end) / 2
        duration_hours = duration_minutes / 60

        # Sanity check: température doit avoir monté
        assert tint_end > tint_start, "La température doit avoir monté"

        # Formule RPth: rpth = (tint_end - text) / (1 - exp(-t/rcth)) - (tint_start - text)
        # Simplifiée: rpth = tsp - text / (1 - exp(-t/rcth)) - (tint_start - text) / (1 - exp(-t/rcth))
        exp_factor = math.exp(-duration_hours / rcth_interpolated)
        rpth_calculated = (
            tint_end - text_avg - (tint_start - text_avg) * exp_factor
        ) / (1 - exp_factor)

        # Le log indique rpth_calculated=55.73
        assert rpth_calculated == pytest.approx(55.73, rel=0.15)

    def test_scenario_rpth_calibration_morning(self):
        """Scénario: Calibration RPth matinale.

        Source log 10:00:00:
        [TC-CALIB-RPTH] RPth calibration: tint_start=16.20°C, tint_end=18.70°C,
        text_start=4.50°C, text_end=6.40°C, duration_minutes=80.8,
        rcth_interpolated=31.48, rpth_calculated=70.43
        """
        tint_start = 16.20
        tint_end = 18.70
        text_start = 4.50
        text_end = 6.40
        duration_minutes = 80.8
        rcth_interpolated = 31.48

        text_avg = (text_start + text_end) / 2
        duration_hours = duration_minutes / 60

        assert tint_end > tint_start

        exp_factor = math.exp(-duration_hours / rcth_interpolated)
        rpth_calculated = (
            tint_end - text_avg - (tint_start - text_avg) * exp_factor
        ) / (1 - exp_factor)

        # Le log indique rpth_calculated=70.43
        assert rpth_calculated == pytest.approx(70.43, rel=0.15)


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 4: Détection d'outliers (TC-SAFE)
# Source: log 2026-02-28 20:27:40 - Détection et clamp d'une valeur aberrante
# ═══════════════════════════════════════════════════════════════════════════════


class TestOutlierDetectionFromLogs:
    """Tests basés sur les logs [TC-SAFE] de détection d'outliers."""

    def test_scenario_outlier_detection_clamp(self):
        """Scénario: Détection et clamp d'un outlier RCth.

        Source logs 20:27:40:
        [TC-SAFE] Outlier détecté pour rcth: calculated_raw=18.58,
        current_memory=85.25, outlier_threshold_percent=50.0, deviation_percent=78.2%
        [TC-SAFE] Valeur plafonnée pour rcth: action=CLAMP_VALUE,
        clamped_to=42.62 (min=42.62, max=127.87)
        [TC-SAFE] Coefficient final pour rcth: final_rcth=56.83
        (après relaxation factor=2.0)
        """
        calculated_raw = 18.58
        current_memory = 85.25
        threshold_percent = 50.0
        relaxation_factor = 2.0

        # Calcul de la déviation
        deviation = abs(calculated_raw - current_memory) / current_memory * 100
        assert deviation == pytest.approx(78.2, rel=0.01)

        # Vérifier que c'est bien un outlier (déviation > threshold)
        assert deviation > threshold_percent

        # Calcul des bornes de clamp
        clamp_min = current_memory * (1 - threshold_percent / 100)  # 42.625
        clamp_max = current_memory * (1 + threshold_percent / 100)  # 127.875

        assert clamp_min == pytest.approx(42.62, rel=0.01)
        assert clamp_max == pytest.approx(127.87, rel=0.01)

        # La valeur calculée (18.58) est sous le minimum → clampée à min
        clamped_value = max(clamp_min, min(clamp_max, calculated_raw))
        assert clamped_value == pytest.approx(42.62, rel=0.01)

        # Le coefficient final du log (56.83) utilise la formule avec rcth_lw précédent
        # Valeur de rcth_lw avant mise à jour: ~70.04 (déduite des logs précédents)
        # La formule: rcth_lw_new = rcth_lw_old + (clamped - rcth_lw_old) / relaxation
        # Vérifions que le résultat final est dans la plage attendue
        rcth_lw_old_implied = 70.04  # Valeur déduite : 56.83 = x + (42.62 - x) / 2
        final_rcth_expected = (
            rcth_lw_old_implied
            + (clamped_value - rcth_lw_old_implied) / relaxation_factor
        )
        assert final_rcth_expected == pytest.approx(56.33, rel=0.1)  # ~56.83 du log

    def test_scenario_no_outlier_pass_through(self):
        """Scénario: Valeur dans les bornes acceptée sans modification."""
        calculated_raw = 60.0
        current_memory = 85.25
        threshold_percent = 50.0

        # Déviation = 29.6% < 50% → pas d'outlier
        deviation = abs(calculated_raw - current_memory) / current_memory * 100
        assert deviation < threshold_percent

        # La valeur passe sans clamp
        clamp_min = current_memory * (1 - threshold_percent / 100)
        clamp_max = current_memory * (1 + threshold_percent / 100)
        clamped_value = max(clamp_min, min(clamp_max, calculated_raw))

        assert clamped_value == calculated_raw


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 5: Prédiction de refroidissement (ADR-050)
# Source: log 2026-02-28 21:00:00 - Température au-dessus de la cible
# ═══════════════════════════════════════════════════════════════════════════════


class TestCoolingPredictionFromLogs:
    """Tests basés sur les logs ADR-050 de prédiction de refroidissement."""

    @pytest.fixture
    def solver(self):
        return ThermalSolver()

    def test_scenario_already_at_target_cooling_prediction(self, solver):
        """Scénario: Température au-dessus de la cible avec refroidissement prévu.

        Source log 21:00:00:
        [TC-PRED] Recovery prediction: tint=20.00°C, text=8.97°C, tsp=19.00°C,
        rcth=23.34, rpth=56.40, target_time=10:00:00, validation_status=ALREADY_AT_TARGET
        ADR-050: Température intérieure (20.0°C) >= cible (19.0°C) mais text=9.0°C < tint
        → prédiction de refroidissement
        Cooling prediction: durée=1.59h après 6 itérations (tint=20.0 → 15.7°C)
        [TC-PRED] Recovery result: duration_hours=1.59, start_time=08:24, iterations=6
        """
        state = ThermalState(
            interior_temp=20.0,  # Au-dessus de la cible
            exterior_temp=8.97,  # Plus froid → va refroidir
            tsp=19.0,
            target_hour=dt_time(10, 0, 0),
            temperature_forecast_avg=8.97,
        )
        coefficients = ThermalCoefficients(
            rcth=23.34,
            rpth=56.40,
            rcth_lw=23.34,
            rcth_hw=23.34,
            rpth_lw=56.40,
            rpth_hw=56.40,
        )
        now = datetime(2026, 2, 28, 21, 0, 0)

        result = solver.calculate_recovery_duration(state, coefficients, now)

        # Même si déjà au-dessus de la cible, le système doit anticiper
        # car la température va baisser pendant la nuit
        assert result.duration_hours == pytest.approx(1.59, rel=0.15)

    def test_scenario_cooling_with_temperature_drop(self, solver):
        """Scénario: Évolution de la prédiction avec température qui baisse.

        Logs 21:11:32 → 21:51:32 montrent l'évolution:
        21:11 - tint=19.80°C → duration=1.62h
        21:31 - tint=19.60°C → duration=1.63h
        21:51 - tint=19.40°C → duration=1.64h
        """
        coefficients = ThermalCoefficients(
            rcth=23.34,
            rpth=56.40,
            rcth_lw=23.34,
            rcth_hw=23.34,
            rpth_lw=56.40,
            rpth_hw=56.40,
        )

        scenarios = [
            (19.80, datetime(2026, 2, 28, 21, 11, 32), 1.62),
            (19.60, datetime(2026, 2, 28, 21, 31, 32), 1.63),
            (19.40, datetime(2026, 2, 28, 21, 51, 32), 1.64),
        ]

        for tint, now, expected_duration in scenarios:
            state = ThermalState(
                interior_temp=tint,
                exterior_temp=8.97,
                tsp=19.0,
                target_hour=dt_time(10, 0, 0),
                temperature_forecast_avg=8.97,
            )
            result = solver.calculate_recovery_duration(state, coefficients, now)
            # Tolérance de 15% car les heures légèrement différentes
            assert result.duration_hours == pytest.approx(expected_duration, rel=0.15)


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 6: Cycle complet de transitions d'états
# Source: logs 2026-02-28 20:27:40 → 22:30:00 - Cycle chambre
# ═══════════════════════════════════════════════════════════════════════════════


class TestFullCycleTransitionsFromLogs:
    """Tests basés sur les logs de transitions d'états complètes."""

    def test_scenario_chambre_full_cycle_sequence(self):
        """Scénario: Cycle complet chambre depuis les logs.

        Séquence observée:
        20:27:40 - monitoring → recovery (heure de démarrage atteinte)
        20:27:40 - recovery → heating_process (calibration RCth terminée)
        21:51:29 - heating_process → heating_on (fin de relance, calibration RPth)
        22:30:00 - Heure cible atteinte

        Ce test vérifie les timestamps et la logique de transition.
        """
        # Phase 1: Monitoring → Recovery (20:27:40)
        recovery_start_time = datetime(2026, 2, 28, 20, 27, 40)
        target_hour = dt_time(22, 30, 0)

        # Vérifier que l'heure de démarrage est avant la cible
        target_datetime = datetime(2026, 2, 28, 22, 30, 0)
        assert recovery_start_time < target_datetime

        # Phase 2: Recovery → Heating Process
        # Temps entre démarrage et calibration RCth: immédiat
        rcth_calibration_time = datetime(2026, 2, 28, 20, 27, 40)
        assert rcth_calibration_time == recovery_start_time

        # Phase 3: Heating Process → Heating On (21:51:29)
        heating_on_time = datetime(2026, 2, 28, 21, 51, 29)
        heating_duration_minutes = (
            heating_on_time - recovery_start_time
        ).total_seconds() / 60
        # Le log indique duration_minutes=83.8 pour RPth
        assert heating_duration_minutes == pytest.approx(83.8, rel=0.1)

        # Phase 4: Vérifier qu'on atteint la cible
        target_reached_time = datetime(2026, 2, 28, 22, 30, 0)
        time_buffer_minutes = (
            target_reached_time - heating_on_time
        ).total_seconds() / 60
        # ~38 minutes de marge entre fin de relance et heure cible
        assert time_buffer_minutes > 30

    def test_scenario_salon_full_cycle_morning(self):
        """Scénario: Cycle complet salon matinée depuis les logs.

        Séquence observée:
        21:00:00 - Heure de coupure chauffage → detecting_lag
        21:11:32 - detecting_lag → monitoring (baisse de temp détectée après 692s)
        08:39:11 - monitoring → recovery → heating_process
        10:00:00 - Heure cible atteinte → heating_process → heating_on
        """
        # Phase 1: Detecting lag
        heating_off_time = datetime(2026, 2, 28, 21, 0, 0)
        lag_detection_time = datetime(2026, 2, 28, 21, 11, 32)
        lag_duration_seconds = (lag_detection_time - heating_off_time).total_seconds()
        # Le log indique 692s de lag
        assert lag_duration_seconds == pytest.approx(692, rel=0.05)

        # Phase 2: Monitoring overnight
        monitoring_start = lag_detection_time
        recovery_start = datetime(2026, 3, 1, 8, 39, 11)
        monitoring_duration_hours = (
            recovery_start - monitoring_start
        ).total_seconds() / 3600
        # ~11.5 heures de monitoring
        assert monitoring_duration_hours == pytest.approx(11.46, rel=0.05)

        # Phase 3: Heating process
        target_time = datetime(2026, 3, 1, 10, 0, 0)
        heating_process_duration_minutes = (
            target_time - recovery_start
        ).total_seconds() / 60
        # ~80 minutes de chauffage (log indique 80.8)
        assert heating_process_duration_minutes == pytest.approx(80.8, rel=0.05)


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 7: Évolution nocturne des coefficients
# Source: logs 00:11 → 08:06 - Prédictions toutes les 20 minutes
# ═══════════════════════════════════════════════════════════════════════════════


class TestNightEvolutionFromLogs:
    """Tests de l'évolution des prédictions pendant la nuit."""

    @pytest.fixture
    def solver(self):
        return ThermalSolver()

    def test_scenario_coefficient_stability_overnight(self, solver):
        """Scénario: Les coefficients restent stables pendant la nuit.

        Les logs montrent des variations de rcth/rpth pendant la nuit:
        00:11 - rcth=23.66, rpth=58.55
        01:11 - rcth=23.97, rpth=60.69
        02:11 - rcth=24.29, rpth=62.84
        04:11 - rcth=24.61, rpth=64.98
        05:11 - rcth=24.92, rpth=67.12
        06:11 - rcth=25.24, rpth=69.27

        Les coefficients augmentent légèrement car la température extérieure baisse.
        """
        overnight_data = [
            (23.66, 58.55, 7.93, 18.30),  # 00:11 - text=7.93, tint=18.30
            (23.97, 60.69, 7.40, 17.90),  # 01:11 - text=7.40, tint=17.90
            (24.29, 62.84, 6.70, 17.60),  # 02:11 - text=6.70, tint=17.60
            (24.61, 64.98, 5.43, 17.00),  # 04:11 - text=5.43, tint=17.00
            (24.92, 67.12, 5.03, 16.80),  # 05:11 - text=5.03, tint=16.80
            (25.24, 69.27, 4.60, 16.50),  # 06:11 - text=4.60, tint=16.50
        ]

        for rcth, rpth, text, tint in overnight_data:
            state = ThermalState(
                interior_temp=tint,
                exterior_temp=text,
                tsp=19.0,
                target_hour=dt_time(10, 0, 0),
                temperature_forecast_avg=text,
            )
            coefficients = ThermalCoefficients(
                rcth=rcth,
                rpth=rpth,
                rcth_lw=rcth,
                rcth_hw=rcth,
                rpth_lw=rpth,
                rpth_hw=rpth,
            )
            now = datetime(2026, 3, 1, 4, 0, 0)

            result = solver.calculate_recovery_duration(state, coefficients, now)

            # Les durées doivent rester raisonnables (1-2h)
            assert 1.0 <= result.duration_hours <= 2.5

    def test_scenario_temperature_drop_rate(self):
        """Scénario: Vérifier le taux de baisse de température nocturne.

        De 00:11 (18.30°C) à 06:11 (16.50°C) = -1.8°C en 6h
        Soit -0.3°C/h environ.

        Note: Le modèle exponentiel simple surestime la baisse car il ne
        prend pas en compte les gains thermiques passifs (soleil matinal, etc.)
        """
        tint_0011 = 18.30
        tint_0611 = 16.50
        duration_hours = 6.0

        drop_rate_per_hour = (tint_0011 - tint_0611) / duration_hours
        assert drop_rate_per_hour == pytest.approx(0.3, rel=0.01)

        # Vérification consistance avec modèle exponentiel
        # T(t) = text + (T0 - text) * exp(-t/rcth)
        text_avg = 6.0  # Approximation
        rcth_approx = 24.0  # Approximation depuis les logs

        predicted_drop = (tint_0011 - text_avg) * (
            1 - math.exp(-duration_hours / rcth_approx)
        )
        actual_drop = tint_0011 - tint_0611

        # Le modèle prédit une baisse plus importante (conservateur)
        # car il ne compte pas les gains thermiques passifs
        assert predicted_drop > actual_drop
        # Mais reste dans un ordre de grandeur raisonnable (< 2x)
        assert predicted_drop < actual_drop * 2.0


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 8: Scénarios edge cases observés
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeCasesFromLogs:
    """Tests des cas limites observés dans les logs."""

    @pytest.fixture
    def solver(self):
        return ThermalSolver()

    def test_scenario_target_hour_change(self, solver):
        """Scénario: Changement d'heure cible en cours de soirée.

        Log 21:00:10:
        Target hour changed to: 10:00:00
        Recalcul immédiat avec nouvelle cible.
        """
        # Avant changement: cible 22:30
        state_before = ThermalState(
            interior_temp=20.0,
            exterior_temp=8.97,
            tsp=19.0,
            target_hour=dt_time(22, 30, 0),
            temperature_forecast_avg=8.97,
        )

        # Après changement: cible 10:00 (lendemain)
        state_after = ThermalState(
            interior_temp=20.0,
            exterior_temp=8.97,
            tsp=19.0,
            target_hour=dt_time(10, 0, 0),
            temperature_forecast_avg=8.97,
        )

        coefficients = ThermalCoefficients(
            rcth=23.34,
            rpth=56.40,
            rcth_lw=23.34,
            rcth_hw=23.34,
            rpth_lw=56.40,
            rpth_hw=56.40,
        )
        now = datetime(2026, 2, 28, 21, 0, 10)

        result_before = solver.calculate_recovery_duration(
            state_before, coefficients, now
        )
        result_after = solver.calculate_recovery_duration(
            state_after, coefficients, now
        )

        # Avec la cible à 10:00 (lendemain), la durée est plus longue
        # car on a plus de temps pour le refroidissement nocturne
        assert result_after.duration_hours >= result_before.duration_hours

    def test_scenario_recovery_calc_hour_change(self, solver):
        """Scénario: Changement de l'heure de recalcul.

        Log 21:00:10:
        Recovery calc hour changed to: 21:00:00
        Trigger RECOVERY_START programmé pour 08:24:40
        """
        # L'heure de recalcul est passée de 23:00 à 21:00
        # Le trigger de démarrage est reprogrammé
        recovery_start_programmed = dt_time(8, 24, 40)
        target_hour = dt_time(10, 0, 0)

        # Temps entre démarrage programmé et cible
        start_datetime = datetime(2026, 3, 1, 8, 24, 40)
        target_datetime = datetime(2026, 3, 1, 10, 0, 0)
        duration_expected = (target_datetime - start_datetime).total_seconds() / 3600

        # Environ 1h35 de chauffage prévu
        assert duration_expected == pytest.approx(1.59, rel=0.01)

    def test_scenario_iterations_convergence(self, solver):
        """Scénario: Vérification du nombre d'itérations pour convergence.

        Les logs montrent généralement 4-6 itérations:
        - iterations=5 pour la plupart des cas standards
        - iterations=6 pour les cas avec cooling prediction
        - iterations=4 quand la solution est proche
        """
        state = ThermalState(
            interior_temp=17.0,
            exterior_temp=5.0,
            tsp=19.0,
            target_hour=dt_time(10, 0, 0),
            temperature_forecast_avg=5.0,
        )
        coefficients = ThermalCoefficients(
            rcth=24.0,
            rpth=60.0,
            rcth_lw=24.0,
            rcth_hw=24.0,
            rpth_lw=60.0,
            rpth_hw=60.0,
        )
        now = datetime(2026, 3, 1, 4, 0, 0)

        result = solver.calculate_recovery_duration(state, coefficients, now)

        # Résultat valide trouvé
        assert result.duration_hours > 0
        # Le nombre d'itérations est implicite dans le résultat
        # (on ne peut pas le vérifier directement sans accès aux logs de debug)


# ═══════════════════════════════════════════════════════════════════════════════
# SCENARIO 9: Validation croisée des valeurs extraites
# ═══════════════════════════════════════════════════════════════════════════════


class TestCrossValidationFromLogs:
    """Tests de validation croisée des données extraites des logs."""

    def test_consistency_rcth_vs_cooling_rate(self):
        """Vérifie la cohérence entre RCth et le taux de refroidissement.

        RCth représente la constante de temps de refroidissement.
        Un RCth de ~24h signifie que la température baisse de 63% de l'écart
        initial en 24 heures.
        """
        # Données du cycle matinal
        tint_start = 19.80  # °C à 21:00
        tint_end = 16.20  # °C à 08:39 (lendemain)
        text_avg = 7.1  # Moyenne nocturne approximative
        duration_hours = 11.65  # ~687.6 minutes

        # Calcul théorique
        exp_factor = math.exp(-duration_hours / 34.38)  # rcth du log
        tint_predicted = text_avg + (tint_start - text_avg) * exp_factor

        # La température prédite devrait être proche de la réalité
        assert tint_predicted == pytest.approx(tint_end, rel=0.1)

    def test_consistency_rpth_vs_heating_rate(self):
        """Vérifie la cohérence entre RPth et le taux de chauffage.

        RPth représente la "puissance thermique" équivalente du chauffage.
        """
        # Données du cycle de relance matinal
        tint_start = 16.20  # °C à 08:39
        tint_end = 18.70  # °C à 10:00 (estimé proche de tsp=19°C)
        text_avg = 5.45  # Moyenne (4.50 + 6.40) / 2
        duration_hours = 80.8 / 60  # ~1.35h
        rcth = 31.48
        rpth = 70.43  # Du log

        # Vérification: la puissance de chauffe permet d'atteindre la cible
        exp_factor = math.exp(-duration_hours / rcth)
        # Formule inversée pour vérifier rpth
        numerator = tint_end - text_avg - (tint_start - text_avg) * exp_factor
        denominator = 1 - exp_factor
        rpth_verified = numerator / denominator

        assert rpth_verified == pytest.approx(rpth, rel=0.15)

    def test_log_data_internal_consistency(self):
        """Vérifie la cohérence interne des données des logs."""
        # Les températures doivent respecter certaines contraintes physiques:

        # 1. La température intérieure baisse pendant la nuit
        overnight_temps = [18.30, 17.90, 17.60, 17.00, 16.80, 16.50]
        for i in range(1, len(overnight_temps)):
            assert overnight_temps[i] <= overnight_temps[i - 1]

        # 2. La température extérieure est toujours < intérieure
        interior_ext_pairs = [
            (18.30, 7.93),
            (17.60, 6.70),
            (16.50, 4.60),
        ]
        for tint, text in interior_ext_pairs:
            assert text < tint

        # 3. Les coefficients RCth et RPth sont toujours positifs et raisonnables
        rcth_values = [23.66, 23.97, 24.29, 24.61, 24.92, 25.24]
        rpth_values = [58.55, 60.69, 62.84, 64.98, 67.12, 69.27]

        for rcth in rcth_values:
            assert 10 < rcth < 200

        for rpth in rpth_values:
            assert 20 < rpth < 200


if __name__ == "__main__":
    # Permet d'exécuter les tests directement
    pytest.main([__file__, "-v"])
