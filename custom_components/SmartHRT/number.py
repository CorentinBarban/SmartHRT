"""Entités number SmartHRT (consigne, coefficients thermiques, relaxation)."""

import logging

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_NAME,
    DATA_COORDINATOR,
    DEFAULT_RCTH_MAX,
    DEFAULT_RCTH_MIN,
    DEFAULT_RPTH_MAX,
    DEFAULT_RPTH_MIN,
    DEFAULT_TSP_MAX,
    DEFAULT_TSP_MIN,
    DEFAULT_TSP_STEP,
    DEVICE_MANUFACTURER,
    DOMAIN,
)
from .coordinator import SmartHRTCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Configuration des entités number à partir de la configuration ConfigEntry"""

    _LOGGER.debug("Calling number async_setup_entry entry=%s", entry)

    coordinator: SmartHRTCoordinator = hass.data[DOMAIN][entry.entry_id][
        DATA_COORDINATOR
    ]

    entities = [
        SmartHRTSetPointNumber(coordinator, entry),
        SmartHRTRCthNumber(coordinator, entry),
        SmartHRTRPthNumber(coordinator, entry),
        SmartHRTRCthLWNumber(coordinator, entry),
        SmartHRTRCthHWNumber(coordinator, entry),
        SmartHRTRPthLWNumber(coordinator, entry),
        SmartHRTRPthHWNumber(coordinator, entry),
        SmartHRTRelaxationNumber(coordinator, entry),
    ]
    async_add_entities(entities, True)


class SmartHRTBaseNumber(CoordinatorEntity[SmartHRTCoordinator], NumberEntity):
    """Classe de base des number SmartHRT."""

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        """Initialisation de base"""
        super().__init__(coordinator)
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


class SmartHRTSetPointNumber(SmartHRTBaseNumber):
    """Entité number pour la consigne de température (Set Point).

    Valeur interne en °C ; device_class=TEMPERATURE laisse HA convertir
    en Fahrenheit selon la configuration utilisateur.
    """

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_translation_key = "setpoint"
        self._attr_unique_id = f"{self._device_id}_setpoint"
        self._attr_native_min_value = DEFAULT_TSP_MIN
        self._attr_native_max_value = DEFAULT_TSP_MAX
        self._attr_native_step = DEFAULT_TSP_STEP
        # device_class TEMPERATURE : HA convertit automatiquement Celsius/Fahrenheit
        self._attr_device_class = NumberDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float:
        return self.coordinator.data.tsp

    @property
    def icon(self) -> str | None:
        return "mdi:thermometer"

    async def async_set_native_value(self, value: float) -> None:
        """Mise à jour de la valeur de consigne"""
        _LOGGER.info("Set point changed to: %s", value)
        self.coordinator.set_tsp(value)


class SmartHRTRCthNumber(SmartHRTBaseNumber):
    """Entité number pour RCth"""

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_translation_key = "rcth"
        self._attr_unique_id = f"{self._device_id}_rcth"
        self._attr_native_min_value = DEFAULT_RCTH_MIN
        self._attr_native_max_value = DEFAULT_RCTH_MAX
        self._attr_native_step = 0.5
        self._attr_native_unit_of_measurement = UnitOfTime.HOURS
        self._attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float:
        return round(self.coordinator.data.rcth, 2)

    @property
    def icon(self) -> str | None:
        return "mdi:home-battery-outline"

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.info("RCth changed to: %s", value)
        self.coordinator.set_rcth(value)


class SmartHRTRPthNumber(SmartHRTBaseNumber):
    """Entité number pour RPth (coefficient de puissance thermique).

    Valeur interne en °C ; device_class=TEMPERATURE laisse HA convertir
    en Fahrenheit selon la configuration utilisateur.
    """

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_translation_key = "rpth"
        self._attr_unique_id = f"{self._device_id}_rpth"
        self._attr_native_min_value = DEFAULT_RPTH_MIN
        self._attr_native_max_value = DEFAULT_RPTH_MAX
        self._attr_native_step = 0.5
        # device_class TEMPERATURE : HA convertit automatiquement Celsius/Fahrenheit
        self._attr_device_class = NumberDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float:
        return round(self.coordinator.data.rpth, 2)

    @property
    def icon(self) -> str | None:
        return "mdi:home-lightning-bolt-outline"

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.info("RPth changed to: %s", value)
        self.coordinator.set_rpth(value)


class SmartHRTRCthLWNumber(SmartHRTBaseNumber):
    """Entité number pour RCth low wind.

    Coefficient de refroidissement par vent faible.
    Utilisé pour l'interpolation linéaire selon la vitesse du vent.
    """

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_translation_key = "rcth_lw"
        self._attr_unique_id = f"{self._device_id}_rcth_lw"
        self._attr_native_min_value = DEFAULT_RCTH_MIN
        self._attr_native_max_value = DEFAULT_RCTH_MAX
        self._attr_native_step = 0.5
        self._attr_native_unit_of_measurement = UnitOfTime.HOURS
        self._attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float:
        return round(self.coordinator.data.rcth_lw, 2)

    @property
    def icon(self) -> str | None:
        return "mdi:home-battery-outline"

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.info("RCth LW changed to: %s", value)
        self.coordinator.set_rcth_lw(value)


class SmartHRTRCthHWNumber(SmartHRTBaseNumber):
    """Entité number pour RCth high wind"""

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_translation_key = "rcth_hw"
        self._attr_unique_id = f"{self._device_id}_rcth_hw"
        self._attr_native_min_value = DEFAULT_RCTH_MIN
        self._attr_native_max_value = DEFAULT_RCTH_MAX
        self._attr_native_step = 0.5
        self._attr_native_unit_of_measurement = UnitOfTime.HOURS
        self._attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float:
        return round(self.coordinator.data.rcth_hw, 2)

    @property
    def icon(self) -> str | None:
        return "mdi:home-battery-outline"

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.info("RCth HW changed to: %s", value)
        self.coordinator.set_rcth_hw(value)


class SmartHRTRPthLWNumber(SmartHRTBaseNumber):
    """Entité number pour RPth low wind.

    Coefficient de puissance par vent faible (conversion °C/°F par HA).
    """

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_translation_key = "rpth_lw"
        self._attr_unique_id = f"{self._device_id}_rpth_lw"
        self._attr_native_min_value = DEFAULT_RPTH_MIN
        self._attr_native_max_value = DEFAULT_RPTH_MAX
        self._attr_native_step = 0.5
        # device_class TEMPERATURE : HA convertit automatiquement Celsius/Fahrenheit
        self._attr_device_class = NumberDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float:
        return round(self.coordinator.data.rpth_lw, 2)

    @property
    def icon(self) -> str | None:
        return "mdi:home-lightning-bolt-outline"

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.info("RPth LW changed to: %s", value)
        self.coordinator.set_rpth_lw(value)


class SmartHRTRPthHWNumber(SmartHRTBaseNumber):
    """Entité number pour RPth high wind.

    Coefficient de puissance par vent fort (conversion °C/°F par HA).
    """

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_translation_key = "rpth_hw"
        self._attr_unique_id = f"{self._device_id}_rpth_hw"
        self._attr_native_min_value = DEFAULT_RPTH_MIN
        self._attr_native_max_value = DEFAULT_RPTH_MAX
        self._attr_native_step = 0.5
        # device_class TEMPERATURE : HA convertit automatiquement Celsius/Fahrenheit
        self._attr_device_class = NumberDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float:
        return round(self.coordinator.data.rpth_hw, 2)

    @property
    def icon(self) -> str | None:
        return "mdi:home-lightning-bolt-outline"

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.info("RPth HW changed to: %s", value)
        self.coordinator.set_rpth_hw(value)


class SmartHRTRelaxationNumber(SmartHRTBaseNumber):
    """Entité number pour le facteur de relaxation.

    Contrôle la vitesse de convergence.
    Plus la valeur est élevée, plus l'apprentissage est lent mais stable.
    """

    def __init__(
        self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_translation_key = "relaxation"
        self._attr_unique_id = f"{self._device_id}_relaxation"
        self._attr_native_min_value = 0.0
        self._attr_native_max_value = 15.0
        self._attr_native_step = 0.05
        self._attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float:
        return self.coordinator.data.relaxation_factor

    @property
    def icon(self) -> str | None:
        return "mdi:brain"

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.info("Relaxation factor changed to: %s", value)
        self.coordinator.set_relaxation_factor(value)
