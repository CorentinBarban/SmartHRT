"""Tests pour la conversion Celsius/Fahrenheit (ADR-054).

Ce module teste l'abstraction du système d'unités implémentée
dans le coordinator pour supporter les utilisateurs en Fahrenheit.
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import time as dt_time

from homeassistant.const import UnitOfTemperature
from homeassistant.util.unit_conversion import TemperatureConverter

from custom_components.SmartHRT.coordinator import SmartHRTCoordinator
from custom_components.SmartHRT.data_model import SmartHRTData


class TestNormalizeToCelsius:
    """Tests pour _normalize_to_celsius (ADR-054)."""

    def test_none_returns_none(self, mock_coordinator):
        """None en entrée retourne None."""
        result = mock_coordinator._normalize_to_celsius(None)
        assert result is None

    def test_celsius_unchanged(self, mock_coordinator):
        """Une température en Celsius passe sans modification."""
        result = mock_coordinator._normalize_to_celsius(20.0, UnitOfTemperature.CELSIUS)
        assert result == 20.0

    def test_celsius_default_unit(self, mock_coordinator):
        """Sans unité spécifiée, assume Celsius."""
        result = mock_coordinator._normalize_to_celsius(20.0)
        assert result == 20.0

    def test_fahrenheit_to_celsius_freezing(self, mock_coordinator):
        """32°F = 0°C (point de congélation)."""
        result = mock_coordinator._normalize_to_celsius(
            32.0, UnitOfTemperature.FAHRENHEIT
        )
        assert result == pytest.approx(0.0, abs=0.01)

    def test_fahrenheit_to_celsius_boiling(self, mock_coordinator):
        """212°F = 100°C (point d'ébullition)."""
        result = mock_coordinator._normalize_to_celsius(
            212.0, UnitOfTemperature.FAHRENHEIT
        )
        assert result == pytest.approx(100.0, abs=0.01)

    def test_fahrenheit_to_celsius_room_temp(self, mock_coordinator):
        """68°F = 20°C (température ambiante)."""
        result = mock_coordinator._normalize_to_celsius(
            68.0, UnitOfTemperature.FAHRENHEIT
        )
        assert result == pytest.approx(20.0, abs=0.01)

    def test_fahrenheit_to_celsius_negative(self, mock_coordinator):
        """-4°F = -20°C (grand froid)."""
        result = mock_coordinator._normalize_to_celsius(
            -4.0, UnitOfTemperature.FAHRENHEIT
        )
        assert result == pytest.approx(-20.0, abs=0.01)

    def test_fahrenheit_to_celsius_typical_heating(self, mock_coordinator):
        """65°F ≈ 18.3°C (début de besoin de chauffage)."""
        result = mock_coordinator._normalize_to_celsius(
            65.0, UnitOfTemperature.FAHRENHEIT
        )
        assert result == pytest.approx(18.333, abs=0.01)


class TestGetSensorUnit:
    """Tests pour _get_sensor_unit (ADR-054)."""

    def test_celsius_by_default(self, mock_coordinator, mock_hass):
        """Retourne Celsius si pas d'unité spécifiée."""
        mock_hass.states.set("sensor.temp", "20.0", {})
        result = mock_coordinator._get_sensor_unit("sensor.temp")
        assert result == UnitOfTemperature.CELSIUS

    def test_celsius_when_explicit(self, mock_coordinator, mock_hass):
        """Retourne Celsius quand explicitement défini."""
        mock_hass.states.set(
            "sensor.temp",
            "20.0",
            {"unit_of_measurement": UnitOfTemperature.CELSIUS},
        )
        result = mock_coordinator._get_sensor_unit("sensor.temp")
        assert result == UnitOfTemperature.CELSIUS

    def test_fahrenheit_detected(self, mock_coordinator, mock_hass):
        """Détecte Fahrenheit quand l'entité l'utilise."""
        mock_hass.states.set(
            "sensor.temp_f",
            "68.0",
            {"unit_of_measurement": UnitOfTemperature.FAHRENHEIT},
        )
        result = mock_coordinator._get_sensor_unit("sensor.temp_f")
        assert result == UnitOfTemperature.FAHRENHEIT

    def test_missing_entity_returns_celsius(self, mock_coordinator):
        """Entité non trouvée retourne Celsius par défaut."""
        result = mock_coordinator._get_sensor_unit("sensor.nonexistent")
        assert result == UnitOfTemperature.CELSIUS

    def test_entity_without_attributes(self, mock_coordinator, mock_hass):
        """Entité sans attributs retourne Celsius."""
        # Créer un state sans attributs
        mock_hass.states._states["sensor.no_attrs"] = MagicMock(
            state="20.0", attributes=None
        )
        result = mock_coordinator._get_sensor_unit("sensor.no_attrs")
        assert result == UnitOfTemperature.CELSIUS


class TestConversionPrecision:
    """Tests de précision des conversions aller-retour."""

    @pytest.mark.parametrize(
        "celsius",
        [
            -40.0,  # Point où C et F sont égaux
            -20.0,
            0.0,
            10.0,
            18.5,  # Température intérieure typique
            21.0,  # Consigne standard
            25.0,
            37.0,  # Température corporelle
            100.0,
        ],
    )
    def test_roundtrip_precision(self, celsius):
        """Conversion C→F→C préserve la valeur."""
        fahrenheit = TemperatureConverter.convert(
            celsius, UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT
        )
        back_to_celsius = TemperatureConverter.convert(
            fahrenheit, UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.CELSIUS
        )
        assert back_to_celsius == pytest.approx(celsius, abs=0.001)

    @pytest.mark.parametrize(
        "fahrenheit",
        [
            -40.0,  # Point où C et F sont égaux
            0.0,
            32.0,  # Point de congélation
            50.0,
            65.0,  # Début chauffage US
            70.0,  # Consigne typique US
            98.6,  # Température corporelle
            212.0,  # Point d'ébullition
        ],
    )
    def test_roundtrip_precision_fahrenheit(self, fahrenheit):
        """Conversion F→C→F préserve la valeur."""
        celsius = TemperatureConverter.convert(
            fahrenheit, UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.CELSIUS
        )
        back_to_fahrenheit = TemperatureConverter.convert(
            celsius, UnitOfTemperature.CELSIUS, UnitOfTemperature.FAHRENHEIT
        )
        assert back_to_fahrenheit == pytest.approx(fahrenheit, abs=0.001)


class TestSensorStateConversion:
    """Tests d'intégration pour la conversion lors de la lecture des capteurs."""

    def test_interior_temp_converted_from_fahrenheit(self, mock_coordinator, mock_hass):
        """La température intérieure en Fahrenheit est convertie en Celsius."""
        # Simuler un capteur en Fahrenheit (68°F = 20°C)
        mock_hass.states.set(
            "sensor.interior_temp",
            "68.0",
            {"unit_of_measurement": UnitOfTemperature.FAHRENHEIT},
        )

        # Vérifier que _get_sensor_unit détecte Fahrenheit
        unit = mock_coordinator._get_sensor_unit("sensor.interior_temp")
        assert unit == UnitOfTemperature.FAHRENHEIT

        # Vérifier la conversion
        raw_temp = 68.0
        converted = mock_coordinator._normalize_to_celsius(raw_temp, unit)
        assert converted == pytest.approx(20.0, abs=0.01)

    def test_interior_temp_celsius_unchanged(self, mock_coordinator, mock_hass):
        """La température intérieure en Celsius n'est pas modifiée."""
        mock_hass.states.set(
            "sensor.interior_temp",
            "20.0",
            {"unit_of_measurement": UnitOfTemperature.CELSIUS},
        )

        unit = mock_coordinator._get_sensor_unit("sensor.interior_temp")
        raw_temp = 20.0
        converted = mock_coordinator._normalize_to_celsius(raw_temp, unit)
        assert converted == 20.0


class TestWeatherConversion:
    """Tests de conversion pour les données météo.

    ADR-054: Les weather entities exposent un attribut temperature_unit
    qui indique l'unité des températures. Le code doit lire cet attribut,
    pas l'unité système de HA.
    """

    def test_weather_uses_entity_temperature_unit_fahrenheit(
        self, mock_coordinator, mock_hass
    ):
        """Weather entity utilise son attribut temperature_unit (Fahrenheit)."""
        # Weather entity US avec temperature_unit en °F
        mock_hass.states.set(
            "weather.us_weather",
            "sunny",
            {
                "temperature": 41.0,  # 41°F
                "temperature_unit": UnitOfTemperature.FAHRENHEIT,
            },
        )

        # Doit détecter Fahrenheit via l'attribut de l'entité
        unit = mock_coordinator._get_sensor_unit("weather.us_weather")
        assert unit == UnitOfTemperature.FAHRENHEIT

        # Conversion vers Celsius
        converted = mock_coordinator._normalize_to_celsius(41.0, unit)
        assert converted == pytest.approx(5.0, abs=0.01)

    def test_weather_uses_entity_temperature_unit_celsius(
        self, mock_coordinator, mock_hass
    ):
        """Weather entity utilise son attribut temperature_unit (Celsius)."""
        # Weather entity (ex: Météo France) avec temperature_unit en °C
        mock_hass.states.set(
            "weather.meteo_france",
            "sunny",
            {
                "temperature": 5.0,  # 5°C
                "temperature_unit": UnitOfTemperature.CELSIUS,
            },
        )

        unit = mock_coordinator._get_sensor_unit("weather.meteo_france")
        assert unit == UnitOfTemperature.CELSIUS

        # Pas de conversion nécessaire
        converted = mock_coordinator._normalize_to_celsius(5.0, unit)
        assert converted == 5.0

    def test_weather_fallback_to_celsius_when_no_attribute(
        self, mock_coordinator, mock_hass
    ):
        """Weather entity sans temperature_unit → défaut Celsius."""
        mock_hass.states.set(
            "weather.home",
            "sunny",
            {"temperature": 15.0},  # Pas d'attribut temperature_unit
        )

        unit = mock_coordinator._get_sensor_unit("weather.home")
        # Défaut: Celsius (la plupart des intégrations européennes)
        assert unit == UnitOfTemperature.CELSIUS

    def test_weather_no_double_conversion(self, mock_coordinator, mock_hass):
        """Vérifie qu'il n'y a pas de double conversion pour weather.

        Scénario Météo France:
        - Météo France expose temperature_unit: °C
        - Temperature: 20°C
        - Le coordinator doit stocker 20°C (pas de conversion)

        Bug fix: Avant, le code lisait hass.config.units.temperature_unit
        Si HA était en °F, il convertissait 20 comme si c'était °F → ~-6.7°C (FAUX)
        """
        # Même si HA est configuré en Fahrenheit...
        mock_hass.config.units.temperature_unit = UnitOfTemperature.FAHRENHEIT

        # ...Météo France expose ses données en Celsius
        mock_hass.states.set(
            "weather.meteo_france",
            "sunny",
            {
                "temperature": 20.0,  # 20°C (pas °F !)
                "temperature_unit": UnitOfTemperature.CELSIUS,
            },
        )

        # Doit lire l'attribut de l'entité, pas l'unité système HA
        unit = mock_coordinator._get_sensor_unit("weather.meteo_france")
        assert unit == UnitOfTemperature.CELSIUS  # PAS Fahrenheit !

        converted = mock_coordinator._normalize_to_celsius(20.0, unit)

        # Doit être 20°C (pas de conversion car source=Celsius)
        assert converted == pytest.approx(20.0, abs=0.01)


class TestEdgeCases:
    """Tests des cas limites."""

    def test_zero_celsius(self, mock_coordinator):
        """0°C est correctement géré."""
        result = mock_coordinator._normalize_to_celsius(0.0, UnitOfTemperature.CELSIUS)
        assert result == 0.0

    def test_zero_fahrenheit(self, mock_coordinator):
        """0°F est correctement converti (-17.78°C)."""
        result = mock_coordinator._normalize_to_celsius(
            0.0, UnitOfTemperature.FAHRENHEIT
        )
        assert result == pytest.approx(-17.78, abs=0.01)

    def test_minus_40_equal(self, mock_coordinator):
        """-40°C = -40°F (point d'intersection)."""
        result_c = mock_coordinator._normalize_to_celsius(
            -40.0, UnitOfTemperature.CELSIUS
        )
        result_f = mock_coordinator._normalize_to_celsius(
            -40.0, UnitOfTemperature.FAHRENHEIT
        )
        assert result_c == pytest.approx(result_f, abs=0.01)

    def test_very_high_temp(self, mock_coordinator):
        """Températures très élevées (ex: 300°F = 148.89°C)."""
        result = mock_coordinator._normalize_to_celsius(
            300.0, UnitOfTemperature.FAHRENHEIT
        )
        assert result == pytest.approx(148.89, abs=0.01)

    def test_very_low_temp(self, mock_coordinator):
        """Températures très basses (ex: -100°F = -73.33°C)."""
        result = mock_coordinator._normalize_to_celsius(
            -100.0, UnitOfTemperature.FAHRENHEIT
        )
        assert result == pytest.approx(-73.33, abs=0.01)


class TestThermalSolverReceivesCelsius:
    """Vérifie que le ThermalSolver reçoit toujours des valeurs en Celsius."""

    def test_data_model_stores_celsius(self, mock_coordinator, mock_hass):
        """SmartHRTData stocke les températures en Celsius après conversion."""
        # Simuler un capteur Fahrenheit
        mock_hass.states.set(
            "sensor.interior_temp",
            "68.0",  # 68°F = 20°C
            {"unit_of_measurement": UnitOfTemperature.FAHRENHEIT},
        )

        # Simuler la lecture et conversion
        raw_temp = 68.0
        source_unit = mock_coordinator._get_sensor_unit("sensor.interior_temp")
        converted = mock_coordinator._normalize_to_celsius(raw_temp, source_unit)

        # Mettre à jour les données
        mock_coordinator.data.interior_temp = converted

        # Vérifier que la valeur stockée est en Celsius
        assert mock_coordinator.data.interior_temp == pytest.approx(20.0, abs=0.01)


class TestPersistenceInCelsius:
    """Tests de persistance - les données sont toujours stockées en Celsius (ADR-054)."""

    def test_save_restore_preserves_celsius(self):
        """Les températures persistées sont sauvegardées et restaurées en Celsius.

        Note: interior_temp et exterior_temp ne sont pas persistés (données volatiles).
        Les données persistées incluent temp_recovery_calc, temperature_forecast_avg, etc.
        """
        data = SmartHRTData(
            name="Test",
            tsp=21.0,
            target_hour=dt_time(6, 0),
            recoverycalc_hour=dt_time(23, 0),
            temp_recovery_calc=17.0,  # °C - persisté
            text_recovery_calc=3.0,  # °C (extérieur) - persisté
            temperature_forecast_avg=4.5,  # °C - persisté
        )

        # Simuler save/restore (sérialisation Pydantic)
        serialized = data.as_dict()
        restored = SmartHRTData.from_dict(serialized, defaults=data)

        # Vérifier que les températures persistées sont préservées
        assert restored.temp_recovery_calc == 17.0
        assert restored.text_recovery_calc == 3.0
        assert restored.temperature_forecast_avg == 4.5

    def test_serialized_temperatures_are_raw_floats(self):
        """Les températures sérialisées sont des floats bruts (pas de métadonnées d'unité).

        Note: interior_temp et exterior_temp ne sont pas persistés car lus des capteurs.
        Les champs persistés sont temp_recovery_calc, temperature_forecast_avg, etc.
        """
        data = SmartHRTData(
            name="Test",
            tsp=21.0,
            target_hour=dt_time(6, 0),
            recoverycalc_hour=dt_time(23, 0),
            temp_recovery_calc=17.5,  # Persisté
            text_recovery_calc=5.0,  # Persisté
            temperature_forecast_avg=4.5,  # Persisté
        )

        serialized = data.as_dict()

        # Vérifier que les températures persistées sont des floats simples
        assert serialized["temp_recovery_calc"] == 17.5
        assert isinstance(serialized["temp_recovery_calc"], float)
        assert serialized["text_recovery_calc"] == 5.0
        assert isinstance(serialized["text_recovery_calc"], float)
        assert serialized["temperature_forecast_avg"] == 4.5
        assert isinstance(serialized["temperature_forecast_avg"], float)

        # Pas de métadonnées d'unité
        assert "temp_recovery_calc_unit" not in serialized
        assert "temperature_unit" not in serialized

    def test_restore_does_not_convert_temperatures(self):
        """La restauration ne modifie pas les températures (déjà en Celsius)."""
        # Simuler des données stockées (comme si sauvegardées précédemment)
        stored_data = {
            "current_state": "heating_on",
            "target_hour": "06:00:00",
            "recoverycalc_hour": "23:00:00",
            "temp_recovery_calc": 17.0,  # Stocké en °C
            "text_recovery_calc": 3.0,  # Stocké en °C
            "temperature_forecast_avg": 4.5,  # Stocké en °C
            "rcth": 50.0,
            "rpth": 1.5,
        }

        defaults = SmartHRTData(
            name="Test",
            tsp=21.0,
            target_hour=dt_time(6, 0),
            recoverycalc_hour=dt_time(23, 0),
        )
        restored = SmartHRTData.from_dict(stored_data, defaults=defaults)

        # Les valeurs sont identiques à ce qui était stocké
        assert restored.temp_recovery_calc == 17.0
        assert restored.text_recovery_calc == 3.0
        assert restored.temperature_forecast_avg == 4.5

    def test_negative_celsius_preserved(self):
        """Les températures négatives en Celsius sont correctement persistées."""
        data = SmartHRTData(
            name="Test",
            tsp=21.0,
            target_hour=dt_time(6, 0),
            recoverycalc_hour=dt_time(23, 0),
            text_recovery_calc=-15.0,  # Grand froid (persisté)
            temperature_forecast_avg=-10.0,  # Persisté
        )

        serialized = data.as_dict()
        restored = SmartHRTData.from_dict(serialized, defaults=data)

        assert restored.text_recovery_calc == -15.0
        assert restored.temperature_forecast_avg == -10.0

    def test_none_temperatures_preserved(self):
        """Les données volatiles (interior_temp, etc.) ne sont pas persistées.

        Ces données sont relues des capteurs à chaque démarrage.
        Seules les données de session (temp_recovery_calc, etc.) sont persistées.
        """
        data = SmartHRTData(
            name="Test",
            tsp=21.0,
            target_hour=dt_time(6, 0),
            recoverycalc_hour=dt_time(23, 0),
            interior_temp=None,  # Non persisté
            exterior_temp=None,  # Non persisté
            windchill=None,  # Non persisté
        )

        serialized = data.as_dict()

        # Ces champs ne sont pas dans la sérialisation
        assert "interior_temp" not in serialized
        assert "exterior_temp" not in serialized
        assert "windchill" not in serialized

    def test_restart_with_different_system_unit(self, mock_coordinator, mock_hass):
        """Après redémarrage avec unité système différente, les données restent cohérentes.

        Scénario: Utilisateur était en Celsius, les données sont sauvegardées.
        Puis l'utilisateur change son HA en Fahrenheit et redémarre.
        Les données persistées (en Celsius) doivent rester en Celsius.
        C'est UNIQUEMENT la lecture des capteurs qui convertit.

        Note: interior_temp et exterior_temp ne sont pas persistés,
        ils sont relus des capteurs au démarrage.
        """
        # 1. Données sauvegardées (en Celsius) - seulement les champs persistés
        stored_celsius = {
            "current_state": "monitoring",
            "target_hour": "06:00:00",
            "recoverycalc_hour": "23:00:00",
            "temp_recovery_calc": 17.0,  # Stocké en °C
            "text_recovery_calc": 3.0,  # Stocké en °C
            "temperature_forecast_avg": 4.5,  # Stocké en °C
            "rcth": 50.0,
            "rpth": 1.5,
        }

        # 2. Restauration (les données restent en Celsius)
        defaults = SmartHRTData(
            name="Test",
            tsp=21.0,
            target_hour=dt_time(6, 0),
            recoverycalc_hour=dt_time(23, 0),
        )
        mock_coordinator.data = SmartHRTData.from_dict(
            stored_celsius, defaults=defaults
        )

        # 3. Les données persistées sont toujours en Celsius
        assert mock_coordinator.data.temp_recovery_calc == 17.0  # °C, pas converti
        assert mock_coordinator.data.text_recovery_calc == 3.0  # °C, pas converti
        assert mock_coordinator.data.temperature_forecast_avg == 4.5  # °C

        # 4. Nouvelle lecture du capteur (maintenant en Fahrenheit)
        mock_hass.states.set(
            "sensor.interior_temp",
            "70.0",  # 70°F = 21.1°C
            {"unit_of_measurement": UnitOfTemperature.FAHRENHEIT},
        )

        # 5. La conversion se fait à la lecture, pas à la restauration
        raw_temp = 70.0
        source_unit = mock_coordinator._get_sensor_unit("sensor.interior_temp")
        converted = mock_coordinator._normalize_to_celsius(raw_temp, source_unit)
        mock_coordinator.data.interior_temp = converted

        # La nouvelle valeur est convertie en Celsius
        assert mock_coordinator.data.interior_temp == pytest.approx(21.11, abs=0.01)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures spécifiques à ce module de tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_hass():
    """Mock simplifié de Home Assistant pour les tests de conversion."""
    from tests.conftest import MockHass

    return MockHass()


@pytest.fixture
def mock_coordinator(mock_hass):
    """Fixture pour créer un coordinateur mock avec les méthodes de conversion."""
    from tests.conftest import MockConfigEntry, MockStore

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
        coordinator._get_sensor_unit = (
            lambda entity_id: SmartHRTCoordinator._get_sensor_unit(
                coordinator, entity_id
            )
        )
        coordinator._normalize_to_celsius = lambda temp, unit=UnitOfTemperature.CELSIUS: SmartHRTCoordinator._normalize_to_celsius(
            coordinator, temp, unit
        )
        return coordinator
