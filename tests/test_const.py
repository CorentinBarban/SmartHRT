"""Tests pour les constantes SmartHRT."""

import pytest

from homeassistant.const import Platform

from custom_components.SmartHRT.const import (
    DOMAIN,
    PLATFORMS,
    CONF_NAME,
    CONF_TARGET_HOUR,
    CONF_RECOVERYCALC_HOUR,
    CONF_SENSOR_INTERIOR_TEMP,
    CONF_PHONE_ALARM,
    CONF_TSP,
    DEFAULT_TSP,
    DEFAULT_TSP_MIN,
    DEFAULT_TSP_MAX,
    DEFAULT_TSP_STEP,
    DEFAULT_RCTH,
    DEFAULT_RPTH,
    DEFAULT_RCTH_MIN,
    DEFAULT_RCTH_MAX,
    DEFAULT_RELAXATION_FACTOR,
    WIND_HIGH,
    WIND_LOW,
    DEVICE_MANUFACTURER,
    DATA_COORDINATOR,
    SERVICE_CALCULATE_RECOVERY_TIME,
    SERVICE_ON_HEATING_STOP,
    SERVICE_ON_RECOVERY_START,
    SERVICE_ON_RECOVERY_END,
    FORECAST_HOURS,
    TEMP_DECREASE_THRESHOLD,
    DEFAULT_RECOVERYCALC_HOUR,
)


class TestDomainAndPlatforms:
    """Tests pour le domaine et les plateformes."""

    def test_domain_value(self):
        """Test de la valeur du domaine."""
        assert DOMAIN == "smarthrt"

    def test_platforms_include_expected(self):
        """Test que les plateformes attendues sont présentes."""
        assert Platform.SENSOR in PLATFORMS
        assert Platform.NUMBER in PLATFORMS
        assert Platform.TIME in PLATFORMS
        assert Platform.SWITCH in PLATFORMS

    def test_platforms_count(self):
        """Test du nombre de plateformes."""
        assert len(PLATFORMS) == 4


class TestConfigurationKeys:
    """Tests pour les clés de configuration."""

    def test_conf_keys_values(self):
        """Test des valeurs des clés de configuration."""
        assert CONF_NAME == "name"
        assert CONF_TARGET_HOUR == "target_hour"
        assert CONF_RECOVERYCALC_HOUR == "recoverycalc_hour"
        assert CONF_SENSOR_INTERIOR_TEMP == "sensor_interior_temperature"
        assert CONF_PHONE_ALARM == "phone_alarm_selector"
        assert CONF_TSP == "tsp"


class TestDefaultValues:
    """Tests pour les valeurs par défaut."""

    def test_tsp_defaults(self):
        """Test des valeurs par défaut de TSP."""
        assert DEFAULT_TSP == 19.0
        assert DEFAULT_TSP_MIN == 13.0
        assert DEFAULT_TSP_MAX == 26.0
        assert DEFAULT_TSP_STEP == 0.1

    def test_thermal_coefficients_defaults(self):
        """Test des valeurs par défaut des coefficients thermiques."""
        assert DEFAULT_RCTH == 50.0
        assert DEFAULT_RPTH == 50.0
        assert DEFAULT_RCTH_MIN == 0.0
        assert DEFAULT_RCTH_MAX == 19999.0
        assert DEFAULT_RELAXATION_FACTOR == 2.0

    def test_wind_thresholds(self):
        """Test des seuils de vent."""
        assert WIND_HIGH == 60.0
        assert WIND_LOW == 10.0

    def test_recoverycalc_hour_default(self):
        """Test de l'heure de coupure par défaut."""
        assert DEFAULT_RECOVERYCALC_HOUR == "23:00:00"


class TestDeviceInfo:
    """Tests pour les informations du device."""

    def test_device_manufacturer(self):
        """Test du fabricant."""
        assert DEVICE_MANUFACTURER == "SmartHRT"

    def test_data_coordinator_key(self):
        """Test de la clé du coordinateur."""
        assert DATA_COORDINATOR == "coordinator"


class TestServiceNames:
    """Tests pour les noms des services."""

    def test_service_names(self):
        """Test des noms des services."""
        assert SERVICE_CALCULATE_RECOVERY_TIME == "calculate_recovery_time"
        assert SERVICE_ON_HEATING_STOP == "on_heating_stop"
        assert SERVICE_ON_RECOVERY_START == "on_recovery_start"
        assert SERVICE_ON_RECOVERY_END == "on_recovery_end"


class TestOtherConstants:
    """Tests pour les autres constantes."""

    def test_forecast_hours(self):
        """Test des heures de prévision."""
        assert FORECAST_HOURS == 3

    def test_temp_decrease_threshold(self):
        """Test du seuil de baisse de température."""
        assert TEMP_DECREASE_THRESHOLD == 0.2
