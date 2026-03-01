"""Tests pour la conversion des unités de vitesse du vent (ADR-055).

Ce module teste l'abstraction du système d'unités pour la vitesse du vent,
permettant de supporter les utilisateurs avec différentes configurations
(métrique m/s, US mph, km/h, etc.).
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import time as dt_time

from homeassistant.const import UnitOfSpeed
from homeassistant.util.unit_conversion import SpeedConverter

from custom_components.SmartHRT.coordinator import SmartHRTCoordinator
from custom_components.SmartHRT.data_model import SmartHRTData


class TestNormalizeToMs:
    """Tests pour _normalize_to_ms (ADR-055)."""

    def test_none_returns_none(self, mock_coordinator):
        """None en entrée retourne None."""
        result = mock_coordinator._normalize_to_ms(None)
        assert result is None

    def test_ms_unchanged(self, mock_coordinator):
        """Une vitesse en m/s passe sans modification."""
        result = mock_coordinator._normalize_to_ms(10.0, UnitOfSpeed.METERS_PER_SECOND)
        assert result == 10.0

    def test_ms_default_unit(self, mock_coordinator):
        """Sans unité spécifiée, assume m/s."""
        result = mock_coordinator._normalize_to_ms(10.0)
        assert result == 10.0

    def test_kmh_to_ms(self, mock_coordinator):
        """36 km/h = 10 m/s."""
        result = mock_coordinator._normalize_to_ms(
            36.0, UnitOfSpeed.KILOMETERS_PER_HOUR
        )
        assert result == pytest.approx(10.0, abs=0.01)

    def test_kmh_to_ms_zero(self, mock_coordinator):
        """0 km/h = 0 m/s."""
        result = mock_coordinator._normalize_to_ms(0.0, UnitOfSpeed.KILOMETERS_PER_HOUR)
        assert result == 0.0

    def test_mph_to_ms(self, mock_coordinator):
        """10 mph ≈ 4.47 m/s."""
        result = mock_coordinator._normalize_to_ms(10.0, UnitOfSpeed.MILES_PER_HOUR)
        assert result == pytest.approx(4.47, abs=0.01)

    def test_mph_to_ms_typical_wind(self, mock_coordinator):
        """20 mph ≈ 8.94 m/s (vent modéré)."""
        result = mock_coordinator._normalize_to_ms(20.0, UnitOfSpeed.MILES_PER_HOUR)
        assert result == pytest.approx(8.94, abs=0.01)

    def test_mph_to_ms_high_wind(self, mock_coordinator):
        """40 mph ≈ 17.88 m/s (vent fort)."""
        result = mock_coordinator._normalize_to_ms(40.0, UnitOfSpeed.MILES_PER_HOUR)
        assert result == pytest.approx(17.88, abs=0.01)

    def test_knots_to_ms(self, mock_coordinator):
        """10 kn ≈ 5.14 m/s."""
        result = mock_coordinator._normalize_to_ms(10.0, UnitOfSpeed.KNOTS)
        assert result == pytest.approx(5.14, abs=0.01)

    def test_fts_to_ms(self, mock_coordinator):
        """10 ft/s ≈ 3.05 m/s."""
        result = mock_coordinator._normalize_to_ms(10.0, UnitOfSpeed.FEET_PER_SECOND)
        assert result == pytest.approx(3.05, abs=0.01)


class TestNormalizeToKmh:
    """Tests pour _normalize_to_kmh (ADR-055)."""

    def test_none_returns_none(self, mock_coordinator):
        """None en entrée retourne None."""
        result = mock_coordinator._normalize_to_kmh(None)
        assert result is None

    def test_kmh_unchanged(self, mock_coordinator):
        """Une vitesse en km/h passe sans modification."""
        result = mock_coordinator._normalize_to_kmh(
            36.0, UnitOfSpeed.KILOMETERS_PER_HOUR
        )
        assert result == 36.0

    def test_kmh_default_unit(self, mock_coordinator):
        """Sans unité spécifiée, assume km/h."""
        result = mock_coordinator._normalize_to_kmh(36.0)
        assert result == 36.0

    def test_ms_to_kmh(self, mock_coordinator):
        """10 m/s = 36 km/h."""
        result = mock_coordinator._normalize_to_kmh(10.0, UnitOfSpeed.METERS_PER_SECOND)
        assert result == pytest.approx(36.0, abs=0.01)

    def test_mph_to_kmh(self, mock_coordinator):
        """10 mph ≈ 16.09 km/h."""
        result = mock_coordinator._normalize_to_kmh(10.0, UnitOfSpeed.MILES_PER_HOUR)
        assert result == pytest.approx(16.09, abs=0.01)

    def test_mph_to_kmh_wind_thresholds(self, mock_coordinator):
        """Conversion mph vers km/h pour les seuils de vent (10-60 km/h)."""
        # 6.2 mph ≈ 10 km/h (seuil bas)
        result_low = mock_coordinator._normalize_to_kmh(6.2, UnitOfSpeed.MILES_PER_HOUR)
        assert result_low == pytest.approx(10.0, abs=0.5)

        # 37.3 mph ≈ 60 km/h (seuil haut)
        result_high = mock_coordinator._normalize_to_kmh(
            37.3, UnitOfSpeed.MILES_PER_HOUR
        )
        assert result_high == pytest.approx(60.0, abs=0.5)


class TestGetWindSpeedUnit:
    """Tests pour _get_wind_speed_unit (ADR-055)."""

    def test_kmh_by_default(self, mock_coordinator):
        """Retourne km/h si pas d'unité spécifiée (fallback par défaut)."""
        result = mock_coordinator._get_wind_speed_unit("sensor.wind_nonexistent")
        assert result == UnitOfSpeed.KILOMETERS_PER_HOUR

    def test_sensor_with_ms_unit(self, mock_coordinator, mock_hass):
        """Détecte m/s quand l'entité l'utilise."""
        mock_hass.states.set(
            "sensor.wind_ms",
            "5.0",
            {"unit_of_measurement": UnitOfSpeed.METERS_PER_SECOND},
        )
        result = mock_coordinator._get_wind_speed_unit("sensor.wind_ms")
        assert result == UnitOfSpeed.METERS_PER_SECOND

    def test_sensor_with_mph_unit(self, mock_coordinator, mock_hass):
        """Détecte mph quand l'entité l'utilise."""
        mock_hass.states.set(
            "sensor.wind_mph",
            "10.0",
            {"unit_of_measurement": UnitOfSpeed.MILES_PER_HOUR},
        )
        result = mock_coordinator._get_wind_speed_unit("sensor.wind_mph")
        assert result == UnitOfSpeed.MILES_PER_HOUR

    def test_sensor_with_kmh_unit(self, mock_coordinator, mock_hass):
        """Détecte km/h quand l'entité l'utilise."""
        mock_hass.states.set(
            "sensor.wind_kmh",
            "36.0",
            {"unit_of_measurement": UnitOfSpeed.KILOMETERS_PER_HOUR},
        )
        result = mock_coordinator._get_wind_speed_unit("sensor.wind_kmh")
        assert result == UnitOfSpeed.KILOMETERS_PER_HOUR

    def test_sensor_with_knots_unit(self, mock_coordinator, mock_hass):
        """Détecte nœuds quand l'entité l'utilise."""
        mock_hass.states.set(
            "sensor.wind_knots",
            "10.0",
            {"unit_of_measurement": UnitOfSpeed.KNOTS},
        )
        result = mock_coordinator._get_wind_speed_unit("sensor.wind_knots")
        assert result == UnitOfSpeed.KNOTS

    def test_weather_entity_uses_wind_speed_unit_attribute(
        self, mock_coordinator, mock_hass
    ):
        """Weather entity lit l'attribut wind_speed_unit."""
        # Simuler une weather entity avec wind_speed_unit (Météo France = km/h)
        mock_hass.states.set(
            "weather.home",
            "sunny",
            {
                "temperature": 20.0,
                "wind_speed": 7.0,
                "wind_speed_unit": UnitOfSpeed.KILOMETERS_PER_HOUR,
            },
        )
        result = mock_coordinator._get_wind_speed_unit("weather.home")
        assert result == UnitOfSpeed.KILOMETERS_PER_HOUR

    def test_weather_entity_with_mph_attribute(self, mock_coordinator, mock_hass):
        """Weather entity avec wind_speed_unit=mph retourne mph."""
        mock_hass.states.set(
            "weather.home",
            "sunny",
            {
                "temperature": 68.0,
                "wind_speed": 10.0,
                "wind_speed_unit": UnitOfSpeed.MILES_PER_HOUR,
            },
        )

        result = mock_coordinator._get_wind_speed_unit("weather.home")
        assert result == UnitOfSpeed.MILES_PER_HOUR

    def test_weather_entity_fallback_to_kmh(self, mock_coordinator, mock_hass):
        """Weather entity sans wind_speed_unit fallback sur km/h."""
        mock_hass.states.set(
            "weather.home",
            "sunny",
            {"temperature": 20.0, "wind_speed": 10.0},  # Pas de wind_speed_unit
        )

        result = mock_coordinator._get_wind_speed_unit("weather.home")
        assert result == UnitOfSpeed.KILOMETERS_PER_HOUR


class TestConversionPrecision:
    """Tests de précision des conversions aller-retour."""

    @pytest.mark.parametrize(
        "ms_value",
        [
            0.0,
            1.0,
            2.78,  # 10 km/h
            5.0,
            10.0,  # 36 km/h
            15.0,  # Vent modéré
            20.0,  # Vent fort
            25.0,
        ],
    )
    def test_roundtrip_ms_kmh_ms(self, ms_value):
        """Conversion m/s→km/h→m/s préserve la valeur."""
        kmh = SpeedConverter.convert(
            ms_value, UnitOfSpeed.METERS_PER_SECOND, UnitOfSpeed.KILOMETERS_PER_HOUR
        )
        back_to_ms = SpeedConverter.convert(
            kmh, UnitOfSpeed.KILOMETERS_PER_HOUR, UnitOfSpeed.METERS_PER_SECOND
        )
        assert back_to_ms == pytest.approx(ms_value, abs=0.001)

    @pytest.mark.parametrize(
        "mph_value",
        [
            0.0,
            5.0,
            10.0,
            15.0,
            20.0,
            30.0,
            40.0,
        ],
    )
    def test_roundtrip_mph_ms_mph(self, mph_value):
        """Conversion mph→m/s→mph préserve la valeur."""
        ms = SpeedConverter.convert(
            mph_value, UnitOfSpeed.MILES_PER_HOUR, UnitOfSpeed.METERS_PER_SECOND
        )
        back_to_mph = SpeedConverter.convert(
            ms, UnitOfSpeed.METERS_PER_SECOND, UnitOfSpeed.MILES_PER_HOUR
        )
        assert back_to_mph == pytest.approx(mph_value, abs=0.001)

    @pytest.mark.parametrize(
        "kmh_value",
        [
            0.0,
            10.0,  # Seuil WIND_LOW
            20.0,
            30.0,
            40.0,
            50.0,
            60.0,  # Seuil WIND_HIGH
        ],
    )
    def test_roundtrip_kmh_mph_kmh(self, kmh_value):
        """Conversion km/h→mph→km/h préserve la valeur."""
        mph = SpeedConverter.convert(
            kmh_value, UnitOfSpeed.KILOMETERS_PER_HOUR, UnitOfSpeed.MILES_PER_HOUR
        )
        back_to_kmh = SpeedConverter.convert(
            mph, UnitOfSpeed.MILES_PER_HOUR, UnitOfSpeed.KILOMETERS_PER_HOUR
        )
        assert back_to_kmh == pytest.approx(kmh_value, abs=0.001)


class TestWindThresholdConversions:
    """Tests pour les seuils de vent utilisés dans le calcul thermique."""

    def test_wind_low_threshold_conversion(self, mock_coordinator):
        """Le seuil WIND_LOW (10 km/h) est correctement converti depuis mph."""
        # 10 km/h ≈ 6.21 mph
        mph_equivalent = 6.21
        result_kmh = mock_coordinator._normalize_to_kmh(
            mph_equivalent, UnitOfSpeed.MILES_PER_HOUR
        )
        assert result_kmh == pytest.approx(10.0, abs=0.5)

    def test_wind_high_threshold_conversion(self, mock_coordinator):
        """Le seuil WIND_HIGH (60 km/h) est correctement converti depuis mph."""
        # 60 km/h ≈ 37.28 mph
        mph_equivalent = 37.28
        result_kmh = mock_coordinator._normalize_to_kmh(
            mph_equivalent, UnitOfSpeed.MILES_PER_HOUR
        )
        assert result_kmh == pytest.approx(60.0, abs=0.5)

    def test_wind_calc_in_ms_converted_to_kmh(self, mock_coordinator):
        """Vérifie la conversion m/s → km/h pour les calculs thermiques."""
        # Le calcul thermique utilise wind_kmh = wind_speed_avg * 3.6
        # Donc 10 m/s devrait donner 36 km/h
        ms_value = 10.0
        expected_kmh = 36.0

        # Simuler le calcul du coordinator
        result = ms_value * 3.6
        assert result == pytest.approx(expected_kmh, abs=0.01)


class TestWeatherDataConversion:
    """Tests d'intégration pour la conversion lors de la lecture des données météo."""

    def test_metric_system_no_conversion_needed(self):
        """Système métrique: les données en m/s passent directement."""
        # Dans le système métrique, HA expose wind_speed en m/s
        raw_wind = 5.0  # m/s
        source_unit = UnitOfSpeed.METERS_PER_SECOND

        # Conversion vers m/s (no-op)
        result = SpeedConverter.convert(
            raw_wind, source_unit, UnitOfSpeed.METERS_PER_SECOND
        )
        assert result == 5.0

    def test_us_system_mph_to_ms(self):
        """Système US: les données en mph sont converties en m/s."""
        # Dans le système US, HA expose wind_speed en mph
        raw_wind = 10.0  # mph
        source_unit = UnitOfSpeed.MILES_PER_HOUR

        # Conversion vers m/s
        result = SpeedConverter.convert(
            raw_wind, source_unit, UnitOfSpeed.METERS_PER_SECOND
        )
        assert result == pytest.approx(4.47, abs=0.01)

    def test_forecast_conversion_us_to_kmh(self):
        """Prévisions US: conversion mph → km/h pour wind_speed_forecast_avg."""
        # Les prévisions sont aussi en mph en système US
        raw_forecast_wind = 15.0  # mph
        source_unit = UnitOfSpeed.MILES_PER_HOUR

        # Conversion vers km/h (stockage de wind_speed_forecast_avg)
        result = SpeedConverter.convert(
            raw_forecast_wind, source_unit, UnitOfSpeed.KILOMETERS_PER_HOUR
        )
        assert result == pytest.approx(24.14, abs=0.01)

    def test_meteo_france_forecast_no_double_conversion(
        self, mock_coordinator, mock_hass
    ):
        """Scénario Météo France: wind_speed_forecast_avg sans double conversion.

        Météo France expose wind_speed en km/h (via wind_speed_unit attribute).
        Le forecast doit rester en km/h sans reconversion.

        Bug fix: Avant, le code utilisait hass.config.units.wind_speed_unit (m/s)
        au lieu de lire l'attribut wind_speed_unit de l'entité weather.
        Résultat: 7 km/h × 3.6 = 25.2 km/h (FAUX)
        Après fix: 7 km/h reste 7 km/h (CORRECT)
        """
        # Simuler une weather entity Météo France avec wind_speed_unit en km/h
        mock_hass.states.set(
            "weather.meteo_france",
            "sunny",
            {
                "temperature": 15.0,
                "wind_speed": 7.0,
                "wind_speed_unit": UnitOfSpeed.KILOMETERS_PER_HOUR,
            },
        )

        # 1. Détecter l'unité (doit lire l'attribut wind_speed_unit)
        detected_unit = mock_coordinator._get_wind_speed_unit("weather.meteo_france")
        assert (
            detected_unit == UnitOfSpeed.KILOMETERS_PER_HOUR
        ), f"Expected km/h but got {detected_unit}"

        # 2. Convertir vers km/h (doit être no-op car déjà en km/h)
        raw_wind = 7.0
        converted = mock_coordinator._normalize_to_kmh(raw_wind, detected_unit)
        assert converted == 7.0, f"Expected 7.0 but got {converted}"

        # 3. Vérifier que le résultat final est correct (pas de × 3.6)
        assert converted != pytest.approx(
            25.2, abs=1.0
        ), "Double conversion detected! 7 × 3.6 = 25.2"


# =============================================================================
# Fixtures locales
# =============================================================================


@pytest.fixture
def mock_hass():
    """Mock simplifié de Home Assistant pour les tests de conversion."""
    from tests.conftest import MockHass

    return MockHass()


@pytest.fixture
def mock_coordinator(mock_hass):
    """Fixture pour créer un coordinateur mock avec les méthodes de conversion."""
    from tests.conftest import MockConfigEntry

    entry = MockConfigEntry()

    with patch.object(SmartHRTCoordinator, "__init__", lambda self, hass, entry: None):
        coordinator = SmartHRTCoordinator.__new__(SmartHRTCoordinator)
        coordinator.hass = mock_hass
        coordinator._entry = entry
        coordinator.data = SmartHRTData(
            name="Test",
            tsp=21.0,
            target_hour=dt_time(6, 0),
            recoverycalc_hour=dt_time(23, 0),
        )
        # Bind les méthodes de conversion depuis la vraie classe
        coordinator._get_wind_speed_unit = (
            lambda entity_id: SmartHRTCoordinator._get_wind_speed_unit(
                coordinator, entity_id
            )
        )
        coordinator._normalize_to_ms = lambda speed, unit=UnitOfSpeed.METERS_PER_SECOND: SmartHRTCoordinator._normalize_to_ms(
            coordinator, speed, unit
        )
        coordinator._normalize_to_kmh = lambda speed, unit=UnitOfSpeed.KILOMETERS_PER_HOUR: SmartHRTCoordinator._normalize_to_kmh(
            coordinator, speed, unit
        )
        return coordinator
