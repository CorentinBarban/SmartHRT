"""Tests pour le coordinator SmartHRT."""

import math
from datetime import datetime, time as dt_time, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.util import dt as dt_util

from custom_components.SmartHRT.coordinator import (
    SmartHRTCoordinator,
    SmartHRTData,
)
from custom_components.SmartHRT.const import (
    DOMAIN,
    WIND_HIGH,
    WIND_LOW,
    DEFAULT_RCTH,
    DEFAULT_RPTH,
    TEMP_DECREASE_THRESHOLD,
)


class TestSmartHRTData:
    """Tests pour la dataclass SmartHRTData."""

    def test_default_values(self):
        """Test des valeurs par défaut de SmartHRTData."""
        data = SmartHRTData()

        assert data.name == "SmartHRT"
        assert data.tsp == 19.0
        assert data.smartheating_mode is True
        assert data.recovery_adaptive_mode is True
        assert data.recovery_calc_mode is False
        assert data.rp_calc_mode is False
        assert data.rcth == DEFAULT_RCTH
        assert data.rpth == DEFAULT_RPTH
        assert data.interior_temp is None
        assert data.exterior_temp is None
        assert data.wind_speed == 0.0

    def test_custom_values(self, sample_smarthrt_data):
        """Test avec des valeurs personnalisées."""
        data = sample_smarthrt_data

        assert data.name == "Test SmartHRT"
        assert data.tsp == 19.0
        assert data.interior_temp == 18.5
        assert data.exterior_temp == 5.0
        assert data.wind_speed == 2.5


class TestSmartHRTCoordinatorInit:
    """Tests pour l'initialisation du coordinator."""

    def test_coordinator_creation(self, mock_coordinator):
        """Test de la création du coordinator."""
        assert mock_coordinator is not None
        assert mock_coordinator.data.name == "Test SmartHRT"
        assert mock_coordinator.data.tsp == 19.0
        assert mock_coordinator.data.target_hour == dt_time(6, 0, 0)
        assert mock_coordinator.data.recoverycalc_hour == dt_time(23, 0, 0)

    def test_parse_time_valid(self, mock_coordinator):
        """Test du parsing d'une heure valide."""
        assert mock_coordinator._parse_time("06:30:00") == dt_time(6, 30, 0)
        assert mock_coordinator._parse_time("23:00:00") == dt_time(23, 0, 0)
        assert mock_coordinator._parse_time("12:15") == dt_time(12, 15, 0)

    def test_parse_time_invalid(self, mock_coordinator):
        """Test du parsing d'une heure invalide."""
        # En cas d'erreur, retourne 6:00:00 par défaut
        assert mock_coordinator._parse_time("invalid") == dt_time(6, 0, 0)
        assert mock_coordinator._parse_time("") == dt_time(6, 0, 0)


class TestInterpolation:
    """Tests pour les fonctions d'interpolation."""

    def test_interpolate_low_wind(self, mock_coordinator_with_data):
        """Test de l'interpolation avec vent faible."""
        coord = mock_coordinator_with_data
        # À vent faible (10 km/h), retourne la valeur LW
        result = coord._interpolate(50.0, 30.0, WIND_LOW)
        assert result == 50.0

    def test_interpolate_high_wind(self, mock_coordinator_with_data):
        """Test de l'interpolation avec vent fort."""
        coord = mock_coordinator_with_data
        # À vent fort (60 km/h), retourne la valeur HW
        result = coord._interpolate(50.0, 30.0, WIND_HIGH)
        assert result == 30.0

    def test_interpolate_mid_wind(self, mock_coordinator_with_data):
        """Test de l'interpolation avec vent moyen."""
        coord = mock_coordinator_with_data
        mid_wind = (WIND_LOW + WIND_HIGH) / 2
        result = coord._interpolate(50.0, 30.0, mid_wind)
        # À mi-chemin, on doit avoir la moyenne
        assert result == pytest.approx(40.0, abs=0.1)

    def test_interpolate_clamped_below(self, mock_coordinator_with_data):
        """Test du clamp en dessous du minimum."""
        coord = mock_coordinator_with_data
        result = coord._interpolate(50.0, 30.0, 0.0)  # Vent 0
        assert result == 50.0  # Clampé à WIND_LOW -> valeur LW

    def test_interpolate_clamped_above(self, mock_coordinator_with_data):
        """Test du clamp au-dessus du maximum."""
        coord = mock_coordinator_with_data
        result = coord._interpolate(50.0, 30.0, 100.0)  # Vent 100
        assert result == 30.0  # Clampé à WIND_HIGH -> valeur HW

    def test_get_interpolated_rcth(self, mock_coordinator_with_data):
        """Test de l'interpolation RCth."""
        coord = mock_coordinator_with_data
        coord.data.rcth_lw = 60.0
        coord.data.rcth_hw = 40.0

        result = coord._get_interpolated_rcth(WIND_LOW)
        assert result == 60.0

        result = coord._get_interpolated_rcth(WIND_HIGH)
        assert result == 40.0

    def test_get_interpolated_rpth(self, mock_coordinator_with_data):
        """Test de l'interpolation RPth."""
        coord = mock_coordinator_with_data
        coord.data.rpth_lw = 70.0
        coord.data.rpth_hw = 50.0

        result = coord._get_interpolated_rpth(WIND_LOW)
        assert result == 70.0

        result = coord._get_interpolated_rpth(WIND_HIGH)
        assert result == 50.0


class TestWindchill:
    """Tests pour le calcul du windchill."""

    def test_windchill_cold_windy(self, mock_coordinator_with_data):
        """Test du windchill avec conditions froides et venteuses."""
        coord = mock_coordinator_with_data
        coord.data.exterior_temp = 5.0
        coord.data.wind_speed = 5.56  # 20 km/h

        coord._calculate_windchill()

        # Formule: 13.12 + 0.6215*5 - 11.37*20^0.16 + 0.3965*5*20^0.16
        assert coord.data.windchill is not None
        assert coord.data.windchill < 5.0  # Doit être inférieur à la temp réelle

    def test_windchill_warm(self, mock_coordinator_with_data):
        """Test du windchill avec température >= 10°C."""
        coord = mock_coordinator_with_data
        coord.data.exterior_temp = 15.0
        coord.data.wind_speed = 5.56

        coord._calculate_windchill()

        # Pas de windchill calculé si temp >= 10°C
        assert coord.data.windchill == 15.0

    def test_windchill_calm(self, mock_coordinator_with_data):
        """Test du windchill sans vent."""
        coord = mock_coordinator_with_data
        coord.data.exterior_temp = 5.0
        coord.data.wind_speed = 1.0  # < 4.8 km/h

        coord._calculate_windchill()

        # Pas de windchill si vent < 4.8 km/h
        assert coord.data.windchill == 5.0

    def test_windchill_no_temp(self, mock_coordinator_with_data):
        """Test du windchill sans température extérieure."""
        coord = mock_coordinator_with_data
        coord.data.exterior_temp = None
        coord.data.windchill = None

        coord._calculate_windchill()

        assert coord.data.windchill is None


class TestRecoveryTimeCalculation:
    """Tests pour le calcul de l'heure de relance."""

    def test_calculate_recovery_time_basic(self, mock_coordinator_with_data):
        """Test du calcul de l'heure de relance."""
        coord = mock_coordinator_with_data

        with (
            patch.object(coord, "_schedule_recovery_start"),
            patch.object(coord, "_schedule_recovery_update"),
        ):
            coord.calculate_recovery_time()

        assert coord.data.recovery_start_hour is not None
        # L'heure de relance doit être avant l'heure cible
        now = dt_util.now()
        target_dt = now.replace(
            hour=coord.data.target_hour.hour,
            minute=coord.data.target_hour.minute,
            second=0,
        )
        if target_dt < now:
            target_dt += timedelta(days=1)

        assert coord.data.recovery_start_hour <= target_dt

    def test_calculate_recovery_time_no_interior_temp(self, mock_coordinator_with_data):
        """Test sans température intérieure."""
        coord = mock_coordinator_with_data
        coord.data.interior_temp = None

        coord.calculate_recovery_time()

        # Ne doit rien faire sans température intérieure

    def test_calculate_recovery_time_uses_forecasts(self, mock_coordinator_with_data):
        """Test que les prévisions météo sont utilisées."""
        coord = mock_coordinator_with_data
        coord.data.temperature_forecast_avg = 2.0  # Prévision plus froide
        coord.data.wind_speed_forecast_avg = 25.0

        with (
            patch.object(coord, "_schedule_recovery_start"),
            patch.object(coord, "_schedule_recovery_update"),
        ):
            coord.calculate_recovery_time()

        update_time = coord.calculate_recovery_update_time()

        assert update_time is not None
        assert update_time < coord.data.recovery_start_hour


class TestRCthFastCalculation:
    """Tests pour le calcul de RCth fast."""

    def test_calculate_rcth_fast(self, mock_coordinator_with_data):
        """Test du calcul de RCth fast."""
        coord = mock_coordinator_with_data
        coord.data.time_recovery_calc = dt_util.now() - timedelta(hours=2)
        coord.data.temp_recovery_calc = 20.0
        coord.data.text_recovery_calc = 5.0
        coord.data.interior_temp = 18.0  # Température a baissé
        coord.data.exterior_temp = 5.0

        coord.calculate_rcth_fast()

        # rcth_fast doit être calculé
        assert coord.data.rcth_fast > 0

    def test_calculate_rcth_fast_missing_data(self, mock_coordinator_with_data):
        """Test sans données nécessaires."""
        coord = mock_coordinator_with_data
        coord.data.time_recovery_calc = None

        initial_rcth_fast = coord.data.rcth_fast
        coord.calculate_rcth_fast()

        # Ne doit pas modifier rcth_fast
        assert coord.data.rcth_fast == initial_rcth_fast


class TestThermalCoefficients:
    """Tests pour la mise à jour des coefficients thermiques."""

    def test_update_coefficients_rcth(self, mock_coordinator_with_data):
        """Test de mise à jour de RCth avec relaxation."""
        coord = mock_coordinator_with_data
        coord.data.rcth_calculated = 55.0
        coord.data.wind_speed = 2.78  # 10 km/h

        initial_rcth = coord.data.rcth
        coord._update_coefficients("rcth")

        # RCth doit avoir changé
        assert coord.data.rcth != initial_rcth

    def test_update_coefficients_rpth(self, mock_coordinator_with_data):
        """Test de mise à jour de RPth avec relaxation."""
        coord = mock_coordinator_with_data
        coord.data.rpth_calculated = 55.0
        coord.data.wind_speed = 2.78

        initial_rpth = coord.data.rpth
        coord._update_coefficients("rpth")

        # RPth doit avoir changé
        assert coord.data.rpth != initial_rpth


class TestSetters:
    """Tests pour les setters du coordinator."""

    def test_set_tsp(self, mock_coordinator_with_data):
        """Test du setter de consigne."""
        coord = mock_coordinator_with_data
        listener = MagicMock()
        coord.register_listener(listener)

        with patch.object(coord, "calculate_recovery_time"):
            coord.set_tsp(20.0)

        assert coord.data.tsp == 20.0
        listener.assert_called()

    def test_set_target_hour(self, mock_coordinator_with_data):
        """Test du setter d'heure cible."""
        coord = mock_coordinator_with_data

        with (
            patch.object(coord, "_setup_time_triggers"),
            patch.object(coord, "calculate_recovery_time"),
        ):
            coord.set_target_hour(dt_time(7, 0, 0))

        assert coord.data.target_hour == dt_time(7, 0, 0)

    def test_set_recoverycalc_hour(self, mock_coordinator_with_data):
        """Test du setter de l'heure de coupure."""
        coord = mock_coordinator_with_data

        with patch.object(coord, "_setup_time_triggers"):
            coord.set_recoverycalc_hour(dt_time(22, 30, 0))

        assert coord.data.recoverycalc_hour == dt_time(22, 30, 0)

    def test_set_smartheating_mode(self, mock_coordinator_with_data):
        """Test du setter du mode chauffage intelligent."""
        coord = mock_coordinator_with_data

        coord.set_smartheating_mode(False)
        assert coord.data.smartheating_mode is False

        coord.set_smartheating_mode(True)
        assert coord.data.smartheating_mode is True

    def test_set_adaptive_mode(self, mock_coordinator_with_data):
        """Test du setter du mode adaptatif."""
        coord = mock_coordinator_with_data

        coord.set_adaptive_mode(False)
        assert coord.data.recovery_adaptive_mode is False

    def test_set_rcth(self, mock_coordinator_with_data):
        """Test du setter de RCth."""
        coord = mock_coordinator_with_data

        with patch.object(coord, "calculate_recovery_time"):
            coord.set_rcth(60.0)
        assert coord.data.rcth == 60.0

    def test_set_rpth(self, mock_coordinator_with_data):
        """Test du setter de RPth."""
        coord = mock_coordinator_with_data

        with patch.object(coord, "calculate_recovery_time"):
            coord.set_rpth(60.0)
        listener = MagicMock()

        coord.register_listener(listener)

        assert listener in coord._listeners

    def test_unregister_listener(self, mock_coordinator_with_data):
        """Test du désenregistrement d'un listener."""
        coord = mock_coordinator_with_data
        listener = MagicMock()
        coord.register_listener(listener)

        coord.unregister_listener(listener)

        assert listener not in coord._listeners

    def test_notify_listeners(self, mock_coordinator_with_data):
        """Test de la notification des listeners."""
        coord = mock_coordinator_with_data
        listener1 = MagicMock()
        listener2 = MagicMock()
        coord.register_listener(listener1)
        coord.register_listener(listener2)

        coord._notify_listeners()

        listener1.assert_called_once()
        listener2.assert_called_once()


class TestHeatingStopRecoveryEvents:
    """Tests pour les événements de chauffage."""

    def test_on_heating_stop(self, mock_coordinator_with_data):
        """Test de l'événement d'arrêt du chauffage."""
        coord = mock_coordinator_with_data

        with patch.object(coord, "calculate_recovery_time"):
            coord.on_heating_stop()

    def test_on_recovery_start(self, mock_coordinator_with_data):
        """Test de l'événement de début de relance."""
        coord = mock_coordinator_with_data
        coord.data.time_recovery_calc = dt_util.now() - timedelta(hours=6)
        coord.data.temp_recovery_calc = 20.0
        coord.data.text_recovery_calc = 5.0

        coord.on_recovery_start()

        assert coord.data.time_recovery_start is not None
        assert coord.data.temp_recovery_start == coord.data.interior_temp
        assert coord.data.rp_calc_mode is True
        assert coord.data.recovery_calc_mode is False

    def test_on_recovery_end(self, mock_coordinator_with_data):
        """Test de l'événement de fin de relance."""
        coord = mock_coordinator_with_data
        coord.data.rp_calc_mode = True
        coord.data.time_recovery_start = dt_util.now() - timedelta(hours=1)
        coord.data.temp_recovery_start = 17.0
        coord.data.text_recovery_start = 5.0

        coord.on_recovery_end()

        assert coord.data.time_recovery_end is not None
        assert coord.data.rp_calc_mode is False

    def test_on_recovery_end_not_in_mode(self, mock_coordinator_with_data):
        """Test de l'événement de fin de relance quand pas en mode RP calc."""
        coord = mock_coordinator_with_data
        coord.data.rp_calc_mode = False

        coord.on_recovery_end()

        # Ne doit rien faire
        assert coord.data.time_recovery_end is None


class TestTemperatureThresholds:
    """Tests pour la vérification des seuils de température."""

    def test_check_temperature_decrease(self, mock_coordinator_with_data):
        """Test de la détection de baisse de température."""
        coord = mock_coordinator_with_data
        coord.data.temp_lag_detection_active = True
        coord.data.temp_recovery_calc = 20.0
        coord.data.time_recovery_calc = dt_util.now()
        coord.data.interior_temp = 19.7  # Baisse de 0.3°C

        with patch.object(coord, "calculate_recovery_time"):
            coord._check_temperature_thresholds()

        # La baisse doit avoir été détectée
        assert coord.data.recovery_calc_mode is True

    def test_check_temperature_increase(self, mock_coordinator_with_data):
        """Test quand la température augmente."""
        coord = mock_coordinator_with_data
        coord.data.temp_lag_detection_active = True
        coord.data.temp_recovery_calc = 20.0
        coord.data.interior_temp = 20.5  # Température augmente

        coord._check_temperature_thresholds()

        # Le snapshot doit être mis à jour
        assert coord.data.temp_recovery_calc == 20.5

    def test_setpoint_reached_ends_recovery(self, mock_coordinator_with_data):
        """Test que l'atteinte de la consigne termine la relance."""
        coord = mock_coordinator_with_data
        coord.data.rp_calc_mode = True
        coord.data.tsp = 19.0
        coord.data.interior_temp = 19.5
        coord.data.time_recovery_start = dt_util.now() - timedelta(hours=1)
        coord.data.temp_recovery_start = 17.0
        coord.data.text_recovery_start = 5.0

        coord._check_temperature_thresholds()

        # La relance doit être terminée
        assert coord.data.rp_calc_mode is False


class TestNewFeatures:
    """Tests pour les nouvelles fonctionnalités ajoutées."""

    def test_data_has_error_tracking_fields(self):
        """Test que SmartHRTData a les champs pour les erreurs."""
        data = SmartHRTData()
        assert hasattr(data, "last_rcth_error")
        assert hasattr(data, "last_rpth_error")
        assert data.last_rcth_error == 0.0
        assert data.last_rpth_error == 0.0

    def test_get_time_to_recovery_hours(self, mock_coordinator_with_data):
        """Test du calcul du temps avant relance."""
        coord = mock_coordinator_with_data

        # Set recovery start hour to 2 hours from now
        future_time = dt_util.now() + timedelta(hours=2)
        coord.data.recovery_start_hour = future_time

        result = coord.get_time_to_recovery_hours()

        # Should be approximately 2 hours (with some tolerance for test execution time)
        assert result is not None
        assert 1.9 <= result <= 2.1

    def test_get_time_to_recovery_hours_none(self, mock_coordinator_with_data):
        """Test du temps avant relance quand non défini."""
        coord = mock_coordinator_with_data
        coord.data.recovery_start_hour = None

        result = coord.get_time_to_recovery_hours()

        assert result is None

    def test_get_time_to_recovery_hours_past(self, mock_coordinator_with_data):
        """Test du temps avant relance quand déjà passé."""
        coord = mock_coordinator_with_data

        # Set recovery start hour to 1 hour ago
        past_time = dt_util.now() - timedelta(hours=1)
        coord.data.recovery_start_hour = past_time

        result = coord.get_time_to_recovery_hours()

        # Should return 0 when time has passed
        assert result == 0

    @pytest.mark.asyncio
    async def test_reset_learning(self, mock_coordinator_with_data):
        """Test de la réinitialisation de l'apprentissage."""
        coord = mock_coordinator_with_data

        # Set non-default values
        coord.data.rcth = 75.0
        coord.data.rpth = 80.0
        coord.data.rcth_lw = 70.0
        coord.data.rcth_hw = 65.0
        coord.data.rpth_lw = 85.0
        coord.data.rpth_hw = 75.0
        coord.data.last_rcth_error = 5.0
        coord.data.last_rpth_error = -3.0

        await coord.reset_learning()

        # All should be reset to defaults
        assert coord.data.rcth == DEFAULT_RCTH
        assert coord.data.rpth == DEFAULT_RPTH
        assert coord.data.rcth_lw == DEFAULT_RCTH
        assert coord.data.rcth_hw == DEFAULT_RCTH
        assert coord.data.rpth_lw == DEFAULT_RPTH
        assert coord.data.rpth_hw == DEFAULT_RPTH
        assert coord.data.last_rcth_error == 0.0
        assert coord.data.last_rpth_error == 0.0

    def test_update_coefficients_stores_error(self, mock_coordinator_with_data):
        """Test que _update_coefficients stocke l'erreur."""
        coord = mock_coordinator_with_data
        coord.data.recovery_adaptive_mode = True
        coord.data.wind_speed = 5.0  # m/s
        coord.data.rcth_calculated = 60.0  # Different from interpolated

        coord._update_coefficients("rcth")

        # Error should be stored
        assert coord.data.last_rcth_error != 0.0
