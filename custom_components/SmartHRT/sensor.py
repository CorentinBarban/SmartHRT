"""Implements the SmartHRT sensors component"""

import logging

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
        SmartHRTRecoveryStartSensor(coordinator, entry),
        SmartHRTRCthSensor(coordinator, entry),
        SmartHRTRPthSensor(coordinator, entry),
        SmartHRTRCthFastSensor(coordinator, entry),
        # Nouveaux sensors du YAML
        SmartHRTWindSpeedForecastSensor(coordinator, entry),
        SmartHRTTemperatureForecastSensor(coordinator, entry),
        SmartHRTWindSpeedAvgSensor(coordinator, entry),
        SmartHRTNightStateSensor(coordinator, entry),
        SmartHRTPhoneAlarmSensor(coordinator, entry),
        SmartHRTRecoveryCalcModeSensor(coordinator, entry),
        SmartHRTRPCalcModeSensor(coordinator, entry),
        SmartHRTStopLagDurationSensor(coordinator, entry),
        SmartHRTTimeToRecoverySensor(coordinator, entry),
        SmartHRTStateSensor(coordinator, entry),
    ]

    async_add_entities(entities, True)


class SmartHRTBaseSensor(SensorEntity):
    """Classe de base pour les sensors SmartHRT"""

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


class SmartHRTInteriorTempSensor(SmartHRTBaseSensor):
    """Sensor de température intérieure"""

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "Température intérieure"
        self._attr_unique_id = f"{self._device_id}_interior_temp"

    @property
    def native_value(self) -> float | None:
        return self._coordinator.data.interior_temp

    @property
    def icon(self) -> str | None:
        return "mdi:home-thermometer"

    @property
    def device_class(self) -> SensorDeviceClass | None:
        return SensorDeviceClass.TEMPERATURE

    @property
    def state_class(self) -> SensorStateClass | None:
        return SensorStateClass.MEASUREMENT

    @property
    def native_unit_of_measurement(self) -> str | None:
        return UnitOfTemperature.CELSIUS


class SmartHRTExteriorTempSensor(SmartHRTBaseSensor):
    """Sensor de température extérieure"""

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "Température extérieure"
        self._attr_unique_id = f"{self._device_id}_exterior_temp"

    @property
    def native_value(self) -> float | None:
        return self._coordinator.data.exterior_temp

    @property
    def icon(self) -> str | None:
        return "mdi:thermometer"

    @property
    def device_class(self) -> SensorDeviceClass | None:
        return SensorDeviceClass.TEMPERATURE

    @property
    def state_class(self) -> SensorStateClass | None:
        return SensorStateClass.MEASUREMENT

    @property
    def native_unit_of_measurement(self) -> str | None:
        return UnitOfTemperature.CELSIUS


class SmartHRTWindSpeedSensor(SmartHRTBaseSensor):
    """Sensor de vitesse du vent"""

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "Vitesse du vent"
        self._attr_unique_id = f"{self._device_id}_wind_speed"

    @property
    def native_value(self) -> float | None:
        return (
            round(self._coordinator.data.wind_speed, 1)
            if self._coordinator.data.wind_speed
            else None
        )

    @property
    def icon(self) -> str | None:
        return "mdi:weather-windy"

    @property
    def device_class(self) -> SensorDeviceClass | None:
        return SensorDeviceClass.WIND_SPEED

    @property
    def state_class(self) -> SensorStateClass | None:
        return SensorStateClass.MEASUREMENT

    @property
    def native_unit_of_measurement(self) -> str | None:
        return UnitOfSpeed.METERS_PER_SECOND


class SmartHRTWindchillSensor(SmartHRTBaseSensor):
    """Sensor de température ressentie (windchill)"""

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "Température ressentie"
        self._attr_unique_id = f"{self._device_id}_windchill"

    @property
    def native_value(self) -> float | None:
        return self._coordinator.data.windchill

    @property
    def icon(self) -> str | None:
        return "mdi:snowflake-thermometer"

    @property
    def device_class(self) -> SensorDeviceClass | None:
        return SensorDeviceClass.TEMPERATURE

    @property
    def native_unit_of_measurement(self) -> str | None:
        return UnitOfTemperature.CELSIUS


class SmartHRTRecoveryStartSensor(SmartHRTBaseSensor):
    """Sensor de l'heure de démarrage de la relance"""

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "Heure de relance"
        self._attr_unique_id = f"{self._device_id}_recovery_start"

    @property
    def native_value(self) -> str | None:
        if self._coordinator.data.recovery_start_hour:
            return self._coordinator.data.recovery_start_hour.strftime("%H:%M")
        return None

    @property
    def icon(self) -> str | None:
        return "mdi:radiator"

    @property
    def extra_state_attributes(self) -> dict:
        """Attributs supplémentaires"""
        recovery = self._coordinator.data.recovery_start_hour
        if recovery:
            return {
                "datetime": recovery.isoformat(),
                "target_hour": self._coordinator.data.target_hour.strftime("%H:%M"),
            }
        return {}


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


class SmartHRTWindSpeedForecastSensor(SmartHRTBaseSensor):
    """Sensor de prévision de vitesse du vent (moyenne sur 3h)"""

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "Prévision vent"
        self._attr_unique_id = f"{self._device_id}_wind_forecast"

    @property
    def native_value(self) -> float | None:
        return round(self._coordinator.data.wind_speed_forecast_avg, 1)

    @property
    def icon(self) -> str | None:
        return "mdi:weather-windy"

    @property
    def device_class(self) -> SensorDeviceClass | None:
        return SensorDeviceClass.WIND_SPEED

    @property
    def state_class(self) -> SensorStateClass | None:
        return SensorStateClass.MEASUREMENT

    @property
    def native_unit_of_measurement(self) -> str | None:
        return "km/h"


class SmartHRTTemperatureForecastSensor(SmartHRTBaseSensor):
    """Sensor de prévision de température (moyenne sur 3h)"""

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "Prévision température"
        self._attr_unique_id = f"{self._device_id}_temp_forecast"

    @property
    def native_value(self) -> float | None:
        return round(self._coordinator.data.temperature_forecast_avg, 1)

    @property
    def icon(self) -> str | None:
        return "mdi:thermometer"

    @property
    def device_class(self) -> SensorDeviceClass | None:
        return SensorDeviceClass.TEMPERATURE

    @property
    def state_class(self) -> SensorStateClass | None:
        return SensorStateClass.MEASUREMENT

    @property
    def native_unit_of_measurement(self) -> str | None:
        return UnitOfTemperature.CELSIUS


class SmartHRTWindSpeedAvgSensor(SmartHRTBaseSensor):
    """Sensor de vitesse du vent moyenne sur 4h"""

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "Vent moyen (4h)"
        self._attr_unique_id = f"{self._device_id}_wind_avg"

    @property
    def native_value(self) -> float | None:
        return (
            round(self._coordinator.data.wind_speed_avg, 2)
            if self._coordinator.data.wind_speed_avg
            else None
        )

    @property
    def icon(self) -> str | None:
        return "mdi:weather-windy"

    @property
    def device_class(self) -> SensorDeviceClass | None:
        return SensorDeviceClass.WIND_SPEED

    @property
    def state_class(self) -> SensorStateClass | None:
        return SensorStateClass.MEASUREMENT

    @property
    def native_unit_of_measurement(self) -> str | None:
        return UnitOfSpeed.METERS_PER_SECOND


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


class SmartHRTPhoneAlarmSensor(SmartHRTBaseSensor):
    """Sensor de l'alarme du téléphone"""

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "Alarme téléphone"
        self._attr_unique_id = f"{self._device_id}_phone_alarm"

    @property
    def native_value(self) -> str | None:
        return self._coordinator.data.phone_alarm

    @property
    def icon(self) -> str | None:
        return "mdi:alarm"


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
        return {
            "last_rcth_error": self._coordinator.data.last_rcth_error,
            "last_rpth_error": self._coordinator.data.last_rpth_error,
            "recovery_start_hour": (
                self._coordinator.data.recovery_start_hour.isoformat()
                if self._coordinator.data.recovery_start_hour
                else None
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
