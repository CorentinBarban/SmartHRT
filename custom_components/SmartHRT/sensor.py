"""Implements the SmartHRT sensors component.

ADR implémentées dans ce module:
- ADR-012: Exposition entités pour Lovelace (sensors comme entités HA)
- ADR-014: Format des dates en fuseau local (dt_util.as_local())
"""

import logging
from datetime import timedelta
from typing import Any

from homeassistant.const import UnitOfTemperature, UnitOfSpeed, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.helpers.device_registry import DeviceInfo, DeviceEntryType
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    DEVICE_MANUFACTURER,
    CONF_NAME,
    DATA_COORDINATOR,
)
from .coordinator import SmartHRTCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Configuration des entités sensor à partir de la configuration ConfigEntry"""

    _LOGGER.debug("Calling sensor async_setup_entry entry=%s", entry)

    coordinator: SmartHRTCoordinator = hass.data[DOMAIN][entry.entry_id][
        DATA_COORDINATOR
    ]

    entities = [
        SmartHRTInteriorTempSensor(coordinator, entry),
        SmartHRTExteriorTempSensor(coordinator, entry),
        SmartHRTWindSpeedSensor(coordinator, entry),
        SmartHRTWindchillSensor(coordinator, entry),
        SmartHRTRCthSensor(coordinator, entry),
        SmartHRTRPthSensor(coordinator, entry),
        SmartHRTRCthFastSensor(coordinator, entry),
        # Nouveaux sensors du YAML
        SmartHRTWindSpeedForecastSensor(coordinator, entry),
        SmartHRTTemperatureForecastSensor(coordinator, entry),
        SmartHRTWindSpeedAvgSensor(coordinator, entry),
        SmartHRTNightStateSensor(coordinator, entry),
        SmartHRTRecoveryCalcModeSensor(coordinator, entry),
        SmartHRTRPCalcModeSensor(coordinator, entry),
        SmartHRTStopLagDurationSensor(coordinator, entry),
        SmartHRTTimeToRecoverySensor(coordinator, entry),
        SmartHRTStateSensor(coordinator, entry),
        SmartHRTInstanceInfoSensor(coordinator, entry),
        # Sensors timestamp pour déclencheurs d'automatisations
        SmartHRTRecoveryStartTimestampSensor(coordinator, entry),
        SmartHRTTargetHourTimestampSensor(coordinator, entry),
        SmartHRTRecoveryCalcHourTimestampSensor(coordinator, entry),
    ]

    async_add_entities(entities, True)


class SmartHRTBaseSensor(SensorEntity):
    """Classe de base pour les sensors SmartHRT"""

    _attr_name: str | None = None
    _attr_icon: str | None = None
    _attr_device_class: SensorDeviceClass | None = None
    _attr_state_class: SensorStateClass | None = None
    _attr_native_unit_of_measurement: str | None = None

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        """Initialisation de base"""
        self._coordinator = coordinator
        self._config_entry = config_entry
        self._device_id = config_entry.entry_id
        self._device_name = config_entry.data.get(CONF_NAME, "SmartHRT")
        self._attr_has_entity_name = True

    @property
    def device_info(self) -> DeviceInfo:
        """Retourne les informations du device"""
        return DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, self._device_id)},
            name=self._device_name,
            manufacturer=DEVICE_MANUFACTURER,
            model="Smart Heating Regulator",
        )

    @property
    def should_poll(self) -> bool:
        """Pas de polling pour ces entités"""
        return False

    async def async_added_to_hass(self) -> None:
        """Callback appelé lorsque l'entité est ajoutée à HA"""
        await super().async_added_to_hass()
        self._coordinator.register_listener(self._on_coordinator_update)

    async def async_will_remove_from_hass(self) -> None:
        """Callback appelé lorsque l'entité est retirée de HA"""
        self._coordinator.unregister_listener(self._on_coordinator_update)
        await super().async_will_remove_from_hass()

    @callback
    def _on_coordinator_update(self) -> None:
        """Callback lors d'une mise à jour du coordinateur"""
        self.async_write_ha_state()


class SmartHRTTemperatureSensor(SmartHRTBaseSensor):
    """Classe de base pour les sensors de température"""

    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS


class SmartHRTWindSensor(SmartHRTBaseSensor):
    """Classe de base pour les sensors de vent"""

    _attr_device_class = SensorDeviceClass.WIND_SPEED
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:weather-windy"


class SmartHRTTimestampSensor(SmartHRTBaseSensor):
    """Classe de base pour les sensors timestamp"""

    _attr_device_class = SensorDeviceClass.TIMESTAMP


class SmartHRTInteriorTempSensor(SmartHRTTemperatureSensor):
    """Sensor de température intérieure"""

    _attr_name = "Température intérieure"
    _attr_icon = "mdi:home-thermometer"

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{self._device_id}_interior_temp"

    @property
    def native_value(self) -> float | None:
        return self._coordinator.data.interior_temp


class SmartHRTExteriorTempSensor(SmartHRTTemperatureSensor):
    """Sensor de température extérieure"""

    _attr_name = "Température extérieure"
    _attr_icon = "mdi:thermometer"

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{self._device_id}_exterior_temp"

    @property
    def native_value(self) -> float | None:
        return self._coordinator.data.exterior_temp


class SmartHRTWindSpeedSensor(SmartHRTWindSensor):
    """Sensor de vitesse du vent"""

    _attr_name = "Vitesse du vent"
    _attr_native_unit_of_measurement = UnitOfSpeed.METERS_PER_SECOND

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{self._device_id}_wind_speed"

    @property
    def native_value(self) -> float | None:
        return (
            round(self._coordinator.data.wind_speed, 1)
            if self._coordinator.data.wind_speed
            else None
        )


class SmartHRTWindchillSensor(SmartHRTTemperatureSensor):
    """Sensor de température ressentie (windchill)"""

    _attr_name = "Température ressentie"
    _attr_icon = "mdi:snowflake-thermometer"

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{self._device_id}_windchill"

    @property
    def native_value(self) -> float | None:
        return self._coordinator.data.windchill


class SmartHRTRCthSensor(SmartHRTBaseSensor):
    """Sensor du coefficient RCth"""

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "RCth"
        self._attr_unique_id = f"{self._device_id}_rcth_sensor"

    @property
    def native_value(self) -> float | None:
        return round(self._coordinator.data.rcth, 2)

    @property
    def icon(self) -> str | None:
        return "mdi:home-battery-outline"

    @property
    def state_class(self) -> SensorStateClass | None:
        return SensorStateClass.MEASUREMENT

    @property
    def native_unit_of_measurement(self) -> str | None:
        return UnitOfTime.HOURS

    @property
    def extra_state_attributes(self) -> dict:
        """Attributs supplémentaires avec les valeurs par vent"""
        return {
            "rcth_lw": round(self._coordinator.data.rcth_lw, 2),
            "rcth_hw": round(self._coordinator.data.rcth_hw, 2),
            "rcth_calculated": round(self._coordinator.data.rcth_calculated, 2),
            "last_error": self._coordinator.data.last_rcth_error,
        }


class SmartHRTRPthSensor(SmartHRTBaseSensor):
    """Sensor du coefficient RPth"""

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "RPth"
        self._attr_unique_id = f"{self._device_id}_rpth_sensor"

    @property
    def native_value(self) -> float | None:
        return round(self._coordinator.data.rpth, 2)

    @property
    def icon(self) -> str | None:
        return "mdi:home-lightning-bolt-outline"

    @property
    def state_class(self) -> SensorStateClass | None:
        return SensorStateClass.MEASUREMENT

    @property
    def native_unit_of_measurement(self) -> str | None:
        return UnitOfTemperature.CELSIUS

    @property
    def extra_state_attributes(self) -> dict:
        """Attributs supplémentaires avec les valeurs par vent"""
        return {
            "rpth_lw": round(self._coordinator.data.rpth_lw, 2),
            "rpth_hw": round(self._coordinator.data.rpth_hw, 2),
            "rpth_calculated": round(self._coordinator.data.rpth_calculated, 2),
            "last_error": self._coordinator.data.last_rpth_error,
        }


class SmartHRTRCthFastSensor(SmartHRTBaseSensor):
    """Sensor du coefficient RCth dynamique"""

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "RCth dynamique"
        self._attr_unique_id = f"{self._device_id}_rcth_fast"

    @property
    def native_value(self) -> float | None:
        return round(self._coordinator.data.rcth_fast, 2)

    @property
    def icon(self) -> str | None:
        return "mdi:home-battery-outline"

    @property
    def state_class(self) -> SensorStateClass | None:
        return SensorStateClass.MEASUREMENT

    @property
    def native_unit_of_measurement(self) -> str | None:
        return UnitOfTime.HOURS


class SmartHRTWindSpeedForecastSensor(SmartHRTWindSensor):
    """Sensor de prévision de vitesse du vent (moyenne sur 3h)"""

    _attr_name = "Prévision vent"
    _attr_native_unit_of_measurement = "km/h"

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{self._device_id}_wind_forecast"

    @property
    def native_value(self) -> float | None:
        return round(self._coordinator.data.wind_speed_forecast_avg, 1)


class SmartHRTTemperatureForecastSensor(SmartHRTTemperatureSensor):
    """Sensor de prévision de température (moyenne sur 3h)"""

    _attr_name = "Prévision température"
    _attr_icon = "mdi:thermometer"

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{self._device_id}_temp_forecast"

    @property
    def native_value(self) -> float | None:
        return round(self._coordinator.data.temperature_forecast_avg, 1)


class SmartHRTWindSpeedAvgSensor(SmartHRTWindSensor):
    """Sensor de vitesse du vent moyenne sur 4h"""

    _attr_name = "Vent moyen (4h)"
    _attr_native_unit_of_measurement = UnitOfSpeed.METERS_PER_SECOND

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{self._device_id}_wind_avg"

    @property
    def native_value(self) -> float | None:
        return (
            round(self._coordinator.data.wind_speed_avg, 2)
            if self._coordinator.data.wind_speed_avg
            else None
        )


class SmartHRTNightStateSensor(SmartHRTBaseSensor):
    """Sensor indiquant si c'est la nuit (soleil sous l'horizon)"""

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "État nuit"
        self._attr_unique_id = f"{self._device_id}_night_state"

    @property
    def native_value(self) -> int:
        # Vérifier l'état du soleil
        sun_state = self._coordinator._hass.states.get("sun.sun")
        if sun_state and sun_state.state == "below_horizon":
            return 1
        return 0

    @property
    def icon(self) -> str | None:
        return (
            "mdi:weather-night" if self.native_value == 1 else "mdi:white-balance-sunny"
        )


class SmartHRTRecoveryCalcModeSensor(SmartHRTBaseSensor):
    """Sensor indiquant le mode calcul de relance"""

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "Mode calcul relance"
        self._attr_unique_id = f"{self._device_id}_recovery_calc_mode"

    @property
    def native_value(self) -> str:
        return "on" if self._coordinator.data.recovery_calc_mode else "off"

    @property
    def icon(self) -> str | None:
        return "mdi:clock-end"


class SmartHRTRPCalcModeSensor(SmartHRTBaseSensor):
    """Sensor indiquant le mode calcul RPth"""

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "Mode calcul RP"
        self._attr_unique_id = f"{self._device_id}_rp_calc_mode"

    @property
    def native_value(self) -> str:
        return "on" if self._coordinator.data.rp_calc_mode else "off"

    @property
    def icon(self) -> str | None:
        return "mdi:home-lightning-bolt-outline"


class SmartHRTStopLagDurationSensor(SmartHRTBaseSensor):
    """Sensor de la durée de lag avant baisse de température"""

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "Durée lag arrêt"
        self._attr_unique_id = f"{self._device_id}_stop_lag_duration"

    @property
    def native_value(self) -> float | None:
        return round(self._coordinator.data.stop_lag_duration, 0)

    @property
    def icon(self) -> str | None:
        return "mdi:timer-outline"

    @property
    def native_unit_of_measurement(self) -> str | None:
        return "s"


class SmartHRTTimeToRecoverySensor(SmartHRTBaseSensor):
    """Sensor de la durée restante avant la relance (time_to_recovery).

    Ce sensor indique le temps restant en heures avant que le chauffage
    ne doive démarrer selon le calcul de relance.
    """

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "Temps avant relance"
        self._attr_unique_id = f"{self._device_id}_time_to_recovery"

    @property
    def native_value(self) -> float | None:
        return self._coordinator.get_time_to_recovery_hours()

    @property
    def icon(self) -> str | None:
        return "mdi:clock-start"

    @property
    def state_class(self) -> SensorStateClass | None:
        return SensorStateClass.MEASUREMENT

    @property
    def native_unit_of_measurement(self) -> str | None:
        return UnitOfTime.HOURS

    @property
    def extra_state_attributes(self) -> dict:
        """Attributs supplémentaires avec les erreurs du dernier cycle"""
        recovery_start = self._coordinator.data.recovery_start_hour
        return {
            "last_rcth_error": self._coordinator.data.last_rcth_error,
            "last_rpth_error": self._coordinator.data.last_rpth_error,
            # ADR-014: Conversion en heure locale pour l'affichage
            "recovery_start_hour": (
                dt_util.as_local(recovery_start).isoformat() if recovery_start else None
            ),
        }


class SmartHRTStateSensor(SmartHRTBaseSensor):
    """Sensor exposant l'état courant de la machine à états SmartHRT.

    États possibles:
    - heating_on: Journée, chauffage actif (État 1)
    - detecting_lag: Attente baisse de température (État 2)
    - monitoring: Surveillance nocturne (État 3)
    - recovery: Moment de la relance (État 4)
    - heating_process: Montée en température (État 5)
    """

    STATE_ICONS = {
        "heating_on": "mdi:radiator",
        "detecting_lag": "mdi:thermometer-minus",
        "monitoring": "mdi:eye",
        "recovery": "mdi:clock-fast",
        "heating_process": "mdi:fire",
    }

    STATE_LABELS = {
        "heating_on": "Chauffage actif",
        "detecting_lag": "Détection lag",
        "monitoring": "Surveillance",
        "recovery": "Relance",
        "heating_process": "Montée en température",
    }

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "État machine"
        self._attr_unique_id = f"{self._device_id}_state"

    @property
    def native_value(self) -> str:
        return self._coordinator.data.current_state

    @property
    def icon(self) -> str | None:
        state = self._coordinator.data.current_state
        return self.STATE_ICONS.get(state, "mdi:state-machine")

    @property
    def extra_state_attributes(self) -> dict:
        """Attributs supplémentaires avec le label lisible de l'état"""
        state = self._coordinator.data.current_state
        return {
            "state_label": self.STATE_LABELS.get(state, state),
            "recovery_calc_mode": self._coordinator.data.recovery_calc_mode,
            "rp_calc_mode": self._coordinator.data.rp_calc_mode,
            "temp_lag_detection_active": self._coordinator.data.temp_lag_detection_active,
        }


class SmartHRTInstanceInfoSensor(SmartHRTBaseSensor):
    """Sensor de diagnostic exposant l'entry_id de l'instance SmartHRT.

    Utile pour identifier l'instance dans les appels de services,
    particulièrement quand plusieurs instances sont configurées.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "ID Instance"
        self._attr_icon = "mdi:identifier"
        self._attr_unique_id = f"{self._device_id}_instance_info"

    @property
    def native_value(self) -> str:
        """Retourne l'entry_id de l'instance."""
        return self._config_entry.entry_id

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Attributs supplémentaires avec les informations d'instance."""
        return {
            "entry_id": self._config_entry.entry_id,
            "instance_name": self._device_name,
            "config_title": self._config_entry.title,
            "usage_example": f'service: smarthrt.trigger_calculation\ndata:\n  entry_id: "{self._config_entry.entry_id}"',
        }


class SmartHRTRecoveryStartTimestampSensor(SmartHRTTimestampSensor):
    """Sensor timestamp pour l'heure de relance (utilisable dans les automatisations)."""

    _attr_name = "Heure de relance"
    _attr_icon = "mdi:clock-start"

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{self._device_id}_recovery_start_timestamp"

    @property
    def native_value(self):
        """Retourne le datetime de relance (timezone-aware)."""
        if self._coordinator.data.recovery_start_hour:
            return dt_util.as_local(self._coordinator.data.recovery_start_hour)
        return None


class SmartHRTTargetHourTimestampSensor(SmartHRTTimestampSensor):
    """Sensor timestamp pour l'heure cible/réveil (utilisable dans les automatisations)."""

    _attr_name = "Heure cible"
    _attr_icon = "mdi:clock-end"

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{self._device_id}_target_hour"

    @property
    def native_value(self):
        """Retourne le datetime de l'heure cible (timezone-aware)."""
        if self._coordinator.data.target_hour:
            # Créer un datetime pour aujourd'hui ou demain
            now = dt_util.now()
            target_dt = now.replace(
                hour=self._coordinator.data.target_hour.hour,
                minute=self._coordinator.data.target_hour.minute,
                second=0,
                microsecond=0,
            )
            # Si l'heure est déjà passée, prendre demain
            if target_dt <= now:
                target_dt = target_dt + timedelta(days=1)
            return target_dt
        return None


class SmartHRTRecoveryCalcHourTimestampSensor(SmartHRTTimestampSensor):
    """Sensor timestamp pour l'heure de calcul/coupure chauffage (utilisable dans les automatisations)."""

    _attr_name = "Heure coupure chauffage"
    _attr_icon = "mdi:clock-in"

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{self._device_id}_recoverycalc_hour"

    @property
    def native_value(self):
        """Retourne le datetime de l'heure de coupure chauffage (timezone-aware)."""
        if self._coordinator.data.recoverycalc_hour:
            # Créer un datetime pour aujourd'hui ou demain
            now = dt_util.now()
            calc_dt = now.replace(
                hour=self._coordinator.data.recoverycalc_hour.hour,
                minute=self._coordinator.data.recoverycalc_hour.minute,
                second=0,
                microsecond=0,
            )
            # Si l'heure est déjà passée, prendre demain
            if calc_dt <= now:
                calc_dt = calc_dt + timedelta(days=1)
            return calc_dt
        return None
