"""Implements the SmartHRT sensors component.

ADR implémentées dans ce module:
- ADR-012: Exposition entités pour Lovelace (sensors comme entités HA)
- ADR-014: Format des dates en fuseau local (dt_util.as_local())
- ADR-027: Utilisation de CoordinatorEntity pour synchronisation automatique
- ADR-030: Simplification avec SensorEntityDescription
- ADR-052: Internationalisation native (translation_key au lieu de name)
- ADR-054: Abstraction unités (pas de native_unit_of_measurement pour températures)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Callable

from homeassistant.const import (
    UnitOfTemperature,
    UnitOfSpeed,
    UnitOfTime,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.helpers.device_registry import DeviceInfo, DeviceEntryType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    DEVICE_MANUFACTURER,
    CONF_NAME,
    DATA_COORDINATOR,
)
from .coordinator import SmartHRTCoordinator
from .data_model import SmartHRTData  # ADR-047: Import depuis data_model

_LOGGER = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# ADR-030: SensorEntityDescription étendue
# ─────────────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, kw_only=True)
class SmartHRTSensorDescription(SensorEntityDescription):
    """Description étendue pour les sensors SmartHRT (ADR-030)."""

    value_fn: Callable[[SmartHRTData], Any]
    extra_attrs_fn: Callable[[SmartHRTData], dict[str, Any]] | None = None
    round_digits: int | None = 2


# ─────────────────────────────────────────────────────────────────────────────
# Définition de tous les sensors via descriptions
# ─────────────────────────────────────────────────────────────────────────────

SENSOR_DESCRIPTIONS: tuple[SmartHRTSensorDescription, ...] = (
    # Températures
    # ADR-054: native_unit_of_measurement omis pour les températures
    # device_class=TEMPERATURE permet à HA de gérer l'unité automatiquement
    SmartHRTSensorDescription(
        key="interior_temp",
        translation_key="interior_temp",
        icon="mdi:home-thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        # ADR-054: Pas de native_unit - HA utilise l'unité système
        value_fn=lambda data: data.interior_temp,
        round_digits=None,
    ),
    SmartHRTSensorDescription(
        key="exterior_temp",
        translation_key="exterior_temp",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        # ADR-054: Pas de native_unit - HA utilise l'unité système
        value_fn=lambda data: data.exterior_temp,
        round_digits=None,
    ),
    SmartHRTSensorDescription(
        key="windchill",
        translation_key="windchill",
        icon="mdi:snowflake-thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        # ADR-054: Pas de native_unit - HA utilise l'unité système
        value_fn=lambda data: data.windchill,
        round_digits=None,
    ),
    SmartHRTSensorDescription(
        key="temp_forecast",
        translation_key="temp_forecast",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        # ADR-054: Pas de native_unit - HA utilise l'unité système
        value_fn=lambda data: data.temperature_forecast_avg,
        round_digits=1,
    ),
    # Vent
    SmartHRTSensorDescription(
        key="wind_speed",
        translation_key="wind_speed",
        icon="mdi:weather-windy",
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        value_fn=lambda data: data.wind_speed,
        round_digits=1,
    ),
    SmartHRTSensorDescription(
        key="wind_forecast",
        translation_key="wind_forecast",
        icon="mdi:weather-windy",
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="km/h",
        value_fn=lambda data: data.wind_speed_forecast_avg,
        round_digits=1,
    ),
    SmartHRTSensorDescription(
        key="wind_avg",
        translation_key="wind_avg",
        icon="mdi:weather-windy",
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.METERS_PER_SECOND,
        value_fn=lambda data: data.wind_speed_avg,
        round_digits=2,
    ),
    # Coefficients thermiques
    SmartHRTSensorDescription(
        key="rcth_sensor",
        translation_key="rcth_sensor",
        icon="mdi:home-battery-outline",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.HOURS,
        value_fn=lambda data: data.rcth,
        extra_attrs_fn=lambda data: {
            "rcth_lw": round(data.rcth_lw, 2),
            "rcth_hw": round(data.rcth_hw, 2),
            "rcth_calculated": round(data.rcth_calculated, 2),
            "last_error": data.last_rcth_error,
        },
    ),
    SmartHRTSensorDescription(
        key="rpth_sensor",
        translation_key="rpth_sensor",
        icon="mdi:home-lightning-bolt-outline",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda data: data.rpth,
        extra_attrs_fn=lambda data: {
            "rpth_lw": round(data.rpth_lw, 2),
            "rpth_hw": round(data.rpth_hw, 2),
            "rpth_calculated": round(data.rpth_calculated, 2),
            "last_error": data.last_rpth_error,
        },
    ),
    SmartHRTSensorDescription(
        key="rcth_fast",
        translation_key="rcth_fast",
        icon="mdi:home-battery-outline",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.HOURS,
        value_fn=lambda data: data.rcth_fast,
    ),
    # Modes et flags
    SmartHRTSensorDescription(
        key="recovery_calc_mode",
        translation_key="recovery_calc_mode",
        icon="mdi:clock-end",
        value_fn=lambda data: "on" if data.recovery_calc_mode else "off",
        round_digits=None,
    ),
    SmartHRTSensorDescription(
        key="rp_calc_mode",
        translation_key="rp_calc_mode",
        icon="mdi:home-lightning-bolt-outline",
        value_fn=lambda data: "on" if data.rp_calc_mode else "off",
        round_digits=None,
    ),
    # Durées
    SmartHRTSensorDescription(
        key="stop_lag_duration",
        translation_key="stop_lag_duration",
        icon="mdi:timer-outline",
        native_unit_of_measurement="s",
        value_fn=lambda data: data.stop_lag_duration,
        round_digits=0,
    ),
)


# ─────────────────────────────────────────────────────────────────────────────
# Classe générique pour les sensors basés sur description
# ─────────────────────────────────────────────────────────────────────────────


class SmartHRTSensor(CoordinatorEntity[SmartHRTCoordinator], SensorEntity):
    """Sensor générique SmartHRT basé sur description (ADR-030)."""

    entity_description: SmartHRTSensorDescription

    def __init__(
        self,
        coordinator: SmartHRTCoordinator,
        config_entry: ConfigEntry,
        description: SmartHRTSensorDescription,
    ) -> None:
        """Initialise le sensor avec sa description."""
        super().__init__(coordinator)
        self.entity_description = description
        self._config_entry = config_entry
        self._device_id = config_entry.entry_id
        self._device_name = config_entry.data.get(CONF_NAME, "SmartHRT")
        self._attr_unique_id = f"{self._device_id}_{description.key}"
        self._attr_has_entity_name = True

    @property
    def device_info(self) -> DeviceInfo:
        """Retourne les informations du device."""
        return DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, self._device_id)},
            name=self._device_name,
            manufacturer=DEVICE_MANUFACTURER,
            model="Smart Heating Regulator",
        )

    @property
    def native_value(self) -> Any:
        """Retourne la valeur calculée via value_fn."""
        value = self.entity_description.value_fn(self.coordinator.data)
        if value is not None and self.entity_description.round_digits is not None:
            return round(value, self.entity_description.round_digits)
        return value

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Retourne les attributs supplémentaires via extra_attrs_fn."""
        if self.entity_description.extra_attrs_fn:
            return self.entity_description.extra_attrs_fn(self.coordinator.data)
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Sensors avec logique spéciale (non-factorisables)
# ─────────────────────────────────────────────────────────────────────────────


class SmartHRTBaseSensor(CoordinatorEntity[SmartHRTCoordinator], SensorEntity):
    """Classe de base pour les sensors spéciaux non-factorisables."""

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        """Initialisation de base."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._device_id = config_entry.entry_id
        self._device_name = config_entry.data.get(CONF_NAME, "SmartHRT")
        self._attr_has_entity_name = True

    @property
    def device_info(self) -> DeviceInfo:
        """Retourne les informations du device."""
        return DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN, self._device_id)},
            name=self._device_name,
            manufacturer=DEVICE_MANUFACTURER,
            model="Smart Heating Regulator",
        )


class SmartHRTNightStateSensor(SmartHRTBaseSensor):
    """Sensor indiquant si c'est la nuit (soleil sous l'horizon).

    Ce sensor accède à l'entité externe sun.sun, donc non-factorisable.
    """

    _attr_translation_key = "night_state"

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{self._device_id}_night_state"

    @property
    def native_value(self) -> int:
        """Vérifie l'état du soleil via hass.states."""
        sun_state = self.coordinator.hass.states.get("sun.sun")
        if sun_state and sun_state.state == "below_horizon":
            return 1
        return 0

    @property
    def icon(self) -> str | None:
        return (
            "mdi:weather-night" if self.native_value == 1 else "mdi:white-balance-sunny"
        )


class SmartHRTStateSensor(SmartHRTBaseSensor):
    """Sensor exposant l'état courant de la machine à états SmartHRT.

    Ce sensor a une logique d'icône dynamique.
    Les labels d'état sont gérés via translation_key (ADR-052 i18n).
    """

    STATE_ICONS = {
        "heating_on": "mdi:radiator",
        "detecting_lag": "mdi:thermometer-minus",
        "monitoring": "mdi:eye",
        "recovery": "mdi:clock-fast",
        "heating_process": "mdi:fire",
        "initializing": "mdi:loading",
    }

    _attr_translation_key = "state"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [
        "initializing",
        "heating_on",
        "detecting_lag",
        "monitoring",
        "recovery",
        "heating_process",
        "unknown",
    ]

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{self._device_id}_state"

    @property
    def native_value(self) -> str:
        return self.coordinator.data.current_state

    @property
    def icon(self) -> str | None:
        state = self.coordinator.data.current_state
        return self.STATE_ICONS.get(state, "mdi:state-machine")


class SmartHRTTimeToRecoverySensor(SmartHRTBaseSensor):
    """Sensor de la durée restante avant la relance.

    Appelle une méthode du coordinator, non-factorisable directement.
    """

    _attr_translation_key = "time_to_recovery"
    _attr_icon = "mdi:clock-start"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTime.HOURS

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{self._device_id}_time_to_recovery"

    @property
    def native_value(self) -> float | None:
        return self.coordinator.get_time_to_recovery_hours()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        recovery_start = self.coordinator.data.recovery_start_hour
        return {
            "last_rcth_error": self.coordinator.data.last_rcth_error,
            "last_rpth_error": self.coordinator.data.last_rpth_error,
            "recovery_start_hour": (
                dt_util.as_local(recovery_start).isoformat() if recovery_start else None
            ),
        }


class SmartHRTInstanceInfoSensor(SmartHRTBaseSensor):
    """Sensor de diagnostic exposant l'entry_id de l'instance."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "instance_info"
    _attr_icon = "mdi:identifier"

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{self._device_id}_instance_info"

    @property
    def native_value(self) -> str:
        return self._config_entry.entry_id

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "entry_id": self._config_entry.entry_id,
            "instance_name": self._device_name,
            "config_title": self._config_entry.title,
            "usage_example": f'service: smarthrt.trigger_calculation\ndata:\n  entry_id: "{self._config_entry.entry_id}"',
        }


# ─────────────────────────────────────────────────────────────────────────────
# Sensors Timestamp (calcul dynamique de dates)
# ─────────────────────────────────────────────────────────────────────────────


class SmartHRTTimestampSensor(SmartHRTBaseSensor):
    """Classe de base pour les sensors timestamp."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP


class SmartHRTRecoveryStartTimestampSensor(SmartHRTTimestampSensor):
    """Sensor timestamp pour l'heure de relance."""

    _attr_translation_key = "recovery_start_timestamp"
    _attr_icon = "mdi:clock-start"

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{self._device_id}_recovery_start_timestamp"

    @property
    def native_value(self):
        if self.coordinator.data.recovery_start_hour:
            return dt_util.as_local(self.coordinator.data.recovery_start_hour)
        return None


class SmartHRTTargetHourTimestampSensor(SmartHRTTimestampSensor):
    """Sensor timestamp pour l'heure cible/réveil."""

    _attr_translation_key = "target_hour_timestamp"
    _attr_icon = "mdi:clock-end"

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{self._device_id}_target_hour_timestamp"

    @property
    def native_value(self):
        if self.coordinator.data.target_hour:
            now = dt_util.now()
            target_dt = now.replace(
                hour=self.coordinator.data.target_hour.hour,
                minute=self.coordinator.data.target_hour.minute,
                second=0,
                microsecond=0,
            )
            if target_dt <= now:
                target_dt = target_dt + timedelta(days=1)
            return target_dt
        return None


class SmartHRTRecoveryCalcHourTimestampSensor(SmartHRTTimestampSensor):
    """Sensor timestamp pour l'heure de coupure chauffage."""

    _attr_translation_key = "recoverycalc_hour_timestamp"
    _attr_icon = "mdi:clock-in"

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_unique_id = f"{self._device_id}_recoverycalc_hour_timestamp"

    @property
    def native_value(self):
        if self.coordinator.data.recoverycalc_hour:
            now = dt_util.now()
            calc_dt = now.replace(
                hour=self.coordinator.data.recoverycalc_hour.hour,
                minute=self.coordinator.data.recoverycalc_hour.minute,
                second=0,
                microsecond=0,
            )
            if calc_dt <= now:
                calc_dt = calc_dt + timedelta(days=1)
            return calc_dt
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Setup
# ─────────────────────────────────────────────────────────────────────────────


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Configuration des entités sensor à partir de la configuration ConfigEntry."""

    _LOGGER.debug("Calling sensor async_setup_entry entry=%s", entry)

    coordinator: SmartHRTCoordinator = hass.data[DOMAIN][entry.entry_id][
        DATA_COORDINATOR
    ]

    # Sensors génériques via descriptions (ADR-030)
    entities: list[SensorEntity] = [
        SmartHRTSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    ]

    # Sensors spéciaux avec logique non-factorisable
    entities.extend(
        [
            SmartHRTNightStateSensor(coordinator, entry),
            SmartHRTStateSensor(coordinator, entry),
            SmartHRTTimeToRecoverySensor(coordinator, entry),
            SmartHRTInstanceInfoSensor(coordinator, entry),
            # Sensors timestamp
            SmartHRTRecoveryStartTimestampSensor(coordinator, entry),
            SmartHRTTargetHourTimestampSensor(coordinator, entry),
            SmartHRTRecoveryCalcHourTimestampSensor(coordinator, entry),
        ]
    )

    async_add_entities(entities, True)
