"""Tests unitaires pour le module core/thermal.py.

Ces tests démontrent que le modèle thermique peut être testé
sans aucune dépendance à Home Assistant, avec des données synthétiques.
"""

import pytest
from datetime import datetime, time as dt_time, timedelta

from custom_components.SmartHRT.core.thermal import ThermalSolver
from custom_components.SmartHRT.core.types import (
    ThermalConfig,
    ThermalCoefficients,
    ThermalState,
)


class TestWindchillCalculation:
    """Tests pour le calcul de température ressentie."""

    def test_windchill_cold_and_windy(self):
        """Windchill actif quand temp < 10°C et vent > 1.34 m/s."""
        solver = ThermalSolver()
        # -5°C avec 5 m/s de vent
        result = solver.calculate_windchill(-5.0, 5.0)
        assert result < -5.0  # Doit être inférieur à la température réelle
        assert round(result, 1) == -11.2  # Formule JAG/TI

    def test_windchill_warm_temperature(self):
        """Windchill inactif quand temp >= 10°C."""
        solver = ThermalSolver()
        result = solver.calculate_windchill(15.0, 5.0)
        assert result == 15.0  # Pas de correction

    def test_windchill_no_wind(self):
        """Windchill inactif quand vent <= 1.34 m/s."""
        solver = ThermalSolver()
        result = solver.calculate_windchill(5.0, 1.0)
        assert result == 5.0  # Pas de correction

    def test_windchill_zero_wind(self):
        """Windchill avec vent nul."""
        solver = ThermalSolver()
        result = solver.calculate_windchill(0.0, 0.0)
        assert result == 0.0


class TestInterpolation:
    """Tests pour l'interpolation selon le vent."""

    def test_interpolation_at_low_wind(self):
        """À vent faible, utilise principalement la valeur low wind."""
        solver = ThermalSolver()
        result = solver.interpolate_for_wind(
            value_low_wind=50.0,
            value_high_wind=30.0,
            wind_kmh=10.0,  # WIND_LOW
        )
        assert result == pytest.approx(50.0)

    def test_interpolation_at_high_wind(self):
        """À vent fort, utilise principalement la valeur high wind."""
        solver = ThermalSolver()
        result = solver.interpolate_for_wind(
            value_low_wind=50.0,
            value_high_wind=30.0,
            wind_kmh=60.0,  # WIND_HIGH
        )
        assert result == pytest.approx(30.0)

    def test_interpolation_at_mid_wind(self):
        """À vent moyen, interpole entre les deux valeurs."""
        solver = ThermalSolver()
        result = solver.interpolate_for_wind(
            value_low_wind=50.0,
            value_high_wind=30.0,
            wind_kmh=35.0,  # Milieu
        )
        assert result == pytest.approx(40.0)

    def test_interpolation_clamped_below_low(self):
        """Vent sous WIND_LOW est traité comme WIND_LOW."""
        solver = ThermalSolver()
        result = solver.interpolate_for_wind(
            value_low_wind=50.0,
            value_high_wind=30.0,
            wind_kmh=5.0,  # Sous WIND_LOW
        )
        assert result == pytest.approx(50.0)

    def test_interpolation_clamped_above_high(self):
        """Vent au-dessus WIND_HIGH est traité comme WIND_HIGH."""
        solver = ThermalSolver()
        result = solver.interpolate_for_wind(
            value_low_wind=50.0,
            value_high_wind=30.0,
            wind_kmh=100.0,  # Au-dessus WIND_HIGH
        )
        assert result == pytest.approx(30.0)

    def test_interpolation_minimum_value(self):
        """La valeur interpolée ne peut pas être inférieure à 0.1."""
        solver = ThermalSolver()
        result = solver.interpolate_for_wind(
            value_low_wind=0.05,
            value_high_wind=0.05,
            wind_kmh=35.0,
        )
        assert result >= 0.1


class TestRecoveryDurationCalculation:
    """Tests pour le calcul du temps de relance."""

    @pytest.fixture
    def solver(self):
        return ThermalSolver()

    @pytest.fixture
    def base_state(self):
        return ThermalState(
            interior_temp=17.0,
            exterior_temp=5.0,
            tsp=19.0,
            target_hour=dt_time(6, 0, 0),
            temperature_forecast_avg=3.0,
            wind_speed_forecast_avg_kmh=20.0,
        )

    @pytest.fixture
    def base_coefficients(self):
        return ThermalCoefficients(
            rcth=50.0,
            rpth=50.0,
            rcth_lw=50.0,
            rcth_hw=40.0,
            rpth_lw=50.0,
            rpth_hw=40.0,
        )

    def test_recovery_duration_positive(self, solver, base_state, base_coefficients):
        """Le temps de relance calculé est positif."""
        now = datetime(2026, 2, 5, 23, 0, 0)  # 23h, 7h avant target
        result = solver.calculate_recovery_duration(base_state, base_coefficients, now)
        assert result.duration_hours > 0

    def test_recovery_start_before_target(self, solver, base_state, base_coefficients):
        """L'heure de démarrage est avant l'heure cible."""
        now = datetime(2026, 2, 5, 23, 0, 0)
        result = solver.calculate_recovery_duration(base_state, base_coefficients, now)
        target_dt = datetime(2026, 2, 6, 6, 0, 0)
        assert result.recovery_start_hour < target_dt

    def test_cold_exterior_increases_duration(self, solver, base_coefficients):
        """Température extérieure plus froide augmente le temps de relance."""
        now = datetime(2026, 2, 5, 23, 0, 0)

        state_mild = ThermalState(
            interior_temp=17.0,
            tsp=19.0,
            target_hour=dt_time(6, 0, 0),
            temperature_forecast_avg=10.0,  # Doux
        )
        state_cold = ThermalState(
            interior_temp=17.0,
            tsp=19.0,
            target_hour=dt_time(6, 0, 0),
            temperature_forecast_avg=-5.0,  # Froid
        )

        result_mild = solver.calculate_recovery_duration(
            state_mild, base_coefficients, now
        )
        result_cold = solver.calculate_recovery_duration(
            state_cold, base_coefficients, now
        )

        assert result_cold.duration_hours > result_mild.duration_hours

    def test_higher_tsp_increases_duration(self, solver, base_coefficients):
        """TSP plus élevé augmente le temps de relance."""
        now = datetime(2026, 2, 5, 23, 0, 0)

        state_low_tsp = ThermalState(
            interior_temp=17.0,
            tsp=18.0,
            target_hour=dt_time(6, 0, 0),
            temperature_forecast_avg=5.0,
        )
        state_high_tsp = ThermalState(
            interior_temp=17.0,
            tsp=21.0,
            target_hour=dt_time(6, 0, 0),
            temperature_forecast_avg=5.0,
        )

        result_low = solver.calculate_recovery_duration(
            state_low_tsp, base_coefficients, now
        )
        result_high = solver.calculate_recovery_duration(
            state_high_tsp, base_coefficients, now
        )

        assert result_high.duration_hours > result_low.duration_hours


class TestRecoveryUpdateTime:
    """Tests pour le calcul de l'heure de mise à jour."""

    def test_far_from_recovery_schedules_in_20min_max(self):
        """Loin de la relance, reprogramme dans 20min max."""
        solver = ThermalSolver()
        now = datetime(2026, 2, 5, 20, 0, 0)
        recovery_start = datetime(2026, 2, 6, 5, 0, 0)  # 9h après

        result = solver.calculate_recovery_update_time(recovery_start, now)

        # 9h = 32400s, divisé par 3 = 10800s > 1200s, donc plafonné à 1200s (20min)
        expected_max = now + timedelta(seconds=1200)
        assert result <= expected_max

    def test_close_to_recovery_schedules_after(self):
        """Proche de la relance (< 30min), reprogramme après."""
        solver = ThermalSolver()
        now = datetime(2026, 2, 6, 4, 45, 0)
        recovery_start = datetime(2026, 2, 6, 5, 0, 0)  # 15min après

        result = solver.calculate_recovery_update_time(recovery_start, now)

        # Moins de 30min restant, donc 3600s après
        expected = now + timedelta(seconds=3600)
        assert result == expected


class TestCoefficientUpdate:
    """Tests pour la mise à jour des coefficients."""

    def test_update_reduces_error_over_iterations(self):
        """L'apprentissage réduit l'erreur au fil des itérations."""
        solver = ThermalSolver()

        # Valeurs initiales
        lw, hw, main = 50.0, 40.0, 45.0
        calculated = 55.0  # Valeur mesurée différente

        # Première mise à jour
        result1 = solver.update_coefficients(
            coef_type="rcth",
            current_lw=lw,
            current_hw=hw,
            current_main=main,
            calculated_value=calculated,
            wind_kmh=35.0,
            relaxation_factor=2.0,
        )

        # Deuxième mise à jour avec les nouvelles valeurs
        result2 = solver.update_coefficients(
            coef_type="rcth",
            current_lw=result1.coef_lw,
            current_hw=result1.coef_hw,
            current_main=result1.coef_main,
            calculated_value=calculated,
            wind_kmh=35.0,
            relaxation_factor=2.0,
        )

        # L'erreur doit diminuer
        assert abs(result2.error) < abs(result1.error)

    def test_coefficient_hw_never_exceeds_lw(self):
        """hw ne dépasse jamais lw (plus de pertes par vent fort)."""
        solver = ThermalSolver()

        result = solver.update_coefficients(
            coef_type="rcth",
            current_lw=30.0,
            current_hw=50.0,  # hw > lw anormal
            current_main=40.0,
            calculated_value=35.0,
            wind_kmh=35.0,
            relaxation_factor=2.0,
        )

        assert result.coef_hw <= result.coef_lw

    def test_coefficient_minimum_respected(self):
        """Les coefficients principaux respectent la valeur minimum."""
        solver = ThermalSolver()

        result = solver.update_coefficients(
            coef_type="rcth",
            current_lw=0.05,
            current_hw=0.05,
            current_main=0.05,
            calculated_value=0.05,
            wind_kmh=35.0,
            relaxation_factor=2.0,
        )

        # Le coefficient principal respecte la limite minimum
        assert result.coef_main >= 0.1
        # Les coefficients lw/hw peuvent temporairement être sous 0.1
        # car ils sont limités par coef_max, pas par coef_min dans update_coefficients
        # La limite minimum est appliquée lors de l'interpolation


class TestRCthFastCalculation:
    """Tests pour le calcul dynamique de RCth."""

    def test_rcth_fast_during_cooling(self):
        """Calcule RCth pendant le refroidissement."""
        solver = ThermalSolver()

        result = solver.calculate_rcth_fast(
            interior_temp=18.0,  # Température actuelle
            exterior_temp=5.0,
            temp_at_start=20.0,  # Température au début
            text_at_start=5.0,
            time_since_start_hours=2.0,  # 2 heures écoulées
        )

        assert result is not None
        assert result > 0

    def test_rcth_fast_returns_none_if_temp_not_decreasing(self):
        """Retourne None si la température n'a pas baissé."""
        solver = ThermalSolver()

        result = solver.calculate_rcth_fast(
            interior_temp=21.0,  # Plus chaud qu'au début
            exterior_temp=5.0,
            temp_at_start=20.0,
            text_at_start=5.0,
            time_since_start_hours=2.0,
        )

        assert result is None


class TestCustomConfig:
    """Tests avec configuration personnalisée."""

    def test_custom_wind_thresholds(self):
        """Configuration avec seuils de vent personnalisés."""
        config = ThermalConfig(
            wind_low_kmh=5.0,
            wind_high_kmh=30.0,
        )
        solver = ThermalSolver(config)

        # À mi-chemin (17.5 km/h)
        result = solver.interpolate_for_wind(
            value_low_wind=100.0,
            value_high_wind=50.0,
            wind_kmh=17.5,
        )
        assert result == pytest.approx(75.0)

    def test_custom_iteration_count(self):
        """Configuration avec nombre d'itérations personnalisé."""
        config = ThermalConfig(max_iterations=5)
        solver = ThermalSolver(config)

        # Le calcul doit fonctionner avec moins d'itérations
        state = ThermalState(
            interior_temp=17.0,
            tsp=19.0,
            target_hour=dt_time(6, 0, 0),
            temperature_forecast_avg=5.0,
        )
        coeffs = ThermalCoefficients()
        now = datetime(2026, 2, 5, 23, 0, 0)

        result = solver.calculate_recovery_duration(state, coeffs, now)
        assert result.duration_hours > 0


class TestConvergence:
    """Tests pour la convergence adaptative."""

    @pytest.fixture
    def solver(self):
        return ThermalSolver()

    @pytest.fixture
    def base_state(self):
        return ThermalState(
            interior_temp=17.0,
            exterior_temp=5.0,
            tsp=19.0,
            target_hour=dt_time(6, 0, 0),
            temperature_forecast_avg=3.0,
            wind_speed_forecast_avg_kmh=20.0,
        )

    @pytest.fixture
    def base_coefficients(self):
        return ThermalCoefficients(
            rcth=50.0,
            rpth=50.0,
            rcth_lw=50.0,
            rcth_hw=40.0,
            rpth_lw=50.0,
            rpth_hw=40.0,
        )

    def test_convergence_threshold_respected(
        self, solver, base_state, base_coefficients
    ):
        """Le calcul converge avec le seuil configuré."""
        now = datetime(2026, 2, 5, 23, 0, 0)
        result = solver.calculate_recovery_duration(base_state, base_coefficients, now)

        # Le résultat doit être valide
        assert result.duration_hours >= 0
        assert result.recovery_start_hour is not None

    def test_fast_convergence_with_tight_threshold(self):
        """Convergence rapide avec un seuil strict."""
        config = ThermalConfig(
            max_iterations=50,
            convergence_threshold=0.001,  # Seuil très strict (~3.6s)
        )
        solver = ThermalSolver(config)

        state = ThermalState(
            interior_temp=17.0,
            tsp=19.0,
            target_hour=dt_time(6, 0, 0),
            temperature_forecast_avg=5.0,
            wind_speed_forecast_avg_kmh=20.0,
        )
        coeffs = ThermalCoefficients()
        now = datetime(2026, 2, 5, 23, 0, 0)

        result = solver.calculate_recovery_duration(state, coeffs, now)
        assert result.duration_hours > 0

    def test_max_iterations_prevents_infinite_loop(self):
        """Le max_iterations empêche les boucles infinies."""
        config = ThermalConfig(
            max_iterations=3,  # Très peu d'itérations
            convergence_threshold=0.0001,  # Seuil quasi impossible
        )
        solver = ThermalSolver(config)

        state = ThermalState(
            interior_temp=17.0,
            tsp=19.0,
            target_hour=dt_time(6, 0, 0),
            temperature_forecast_avg=5.0,
        )
        coeffs = ThermalCoefficients()
        now = datetime(2026, 2, 5, 23, 0, 0)

        # Ne doit pas boucler indéfiniment
        result = solver.calculate_recovery_duration(state, coeffs, now)
        assert result.duration_hours >= 0
