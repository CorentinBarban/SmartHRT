""" Implements the SmartHRT number entities """
import logging

from homeassistant.const import UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.helpers.device_registry import DeviceInfo, DeviceEntryType

from .const import (
    DOMAIN,
    DEVICE_MANUFACTURER,
    CONF_NAME,
    DATA_COORDINATOR,
    DEFAULT_TSP_MIN,
    DEFAULT_TSP_MAX,
    DEFAULT_TSP_STEP,
    DEFAULT_RCTH_MIN,
    DEFAULT_RCTH_MAX,
    DEFAULT_RPTH_MIN,
    DEFAULT_RPTH_MAX,
)
from .coordinator import SmartHRTCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Configuration des entités number à partir de la configuration ConfigEntry"""

    _LOGGER.debug("Calling number async_setup_entry entry=%s", entry)

    coordinator: SmartHRTCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

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


class SmartHRTBaseNumber(NumberEntity):
    """Classe de base pour les number SmartHRT"""

    def __init__(self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry) -> None:
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

    @callback
    async def async_added_to_hass(self):
        """Callback appelé lorsque l'entité est ajoutée à HA"""
        self._coordinator.register_listener(self._on_coordinator_update)

    @callback
    async def async_will_remove_from_hass(self):
        """Callback appelé lorsque l'entité est retirée de HA"""
        self._coordinator.unregister_listener(self._on_coordinator_update)

    @callback
    def _on_coordinator_update(self):
        """Callback lors d'une mise à jour du coordinateur"""
        self.async_write_ha_state()


class SmartHRTSetPointNumber(SmartHRTBaseNumber):
    """Entité number pour la consigne de température (Set Point)"""

    def __init__(self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "Consigne"
        self._attr_unique_id = f"{self._device_id}_setpoint"
        self._attr_native_min_value = DEFAULT_TSP_MIN
        self._attr_native_max_value = DEFAULT_TSP_MAX
        self._attr_native_step = DEFAULT_TSP_STEP
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float:
        return self._coordinator.data.tsp

    @property
    def icon(self) -> str | None:
        return "mdi:thermometer"

    async def async_set_native_value(self, value: float) -> None:
        """Mise à jour de la valeur de consigne"""
        _LOGGER.info("Set point changed to: %s", value)
        self._coordinator.set_tsp(value)


class SmartHRTRCthNumber(SmartHRTBaseNumber):
    """Entité number pour RCth"""

    def __init__(self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "RCth"
        self._attr_unique_id = f"{self._device_id}_rcth"
        self._attr_native_min_value = DEFAULT_RCTH_MIN
        self._attr_native_max_value = DEFAULT_RCTH_MAX
        self._attr_native_step = 0.5
        self._attr_native_unit_of_measurement = UnitOfTime.HOURS
        self._attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float:
        return round(self._coordinator.data.rcth, 2)

    @property
    def icon(self) -> str | None:
        return "mdi:home-battery-outline"

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.info("RCth changed to: %s", value)
        self._coordinator.set_rcth(value)


class SmartHRTRPthNumber(SmartHRTBaseNumber):
    """Entité number pour RPth"""

    def __init__(self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "RPth"
        self._attr_unique_id = f"{self._device_id}_rpth"
        self._attr_native_min_value = DEFAULT_RPTH_MIN
        self._attr_native_max_value = DEFAULT_RPTH_MAX
        self._attr_native_step = 0.5
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float:
        return round(self._coordinator.data.rpth, 2)

    @property
    def icon(self) -> str | None:
        return "mdi:home-lightning-bolt-outline"

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.info("RPth changed to: %s", value)
        self._coordinator.set_rpth(value)


class SmartHRTRCthLWNumber(SmartHRTBaseNumber):
    """Entité number pour RCth low wind"""

    def __init__(self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "RCth (vent faible)"
        self._attr_unique_id = f"{self._device_id}_rcth_lw"
        self._attr_native_min_value = DEFAULT_RCTH_MIN
        self._attr_native_max_value = DEFAULT_RCTH_MAX
        self._attr_native_step = 0.5
        self._attr_native_unit_of_measurement = UnitOfTime.HOURS
        self._attr_mode = NumberMode.BOX
        self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> float:
        return round(self._coordinator.data.rcth_lw, 2)

    @property
    def icon(self) -> str | None:
        return "mdi:home-battery-outline"

    async def async_set_native_value(self, value: float) -> None:
        self._coordinator.data.rcth_lw = value
        self._coordinator._notify_listeners()


class SmartHRTRCthHWNumber(SmartHRTBaseNumber):
    """Entité number pour RCth high wind"""

    def __init__(self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "RCth (vent fort)"
        self._attr_unique_id = f"{self._device_id}_rcth_hw"
        self._attr_native_min_value = DEFAULT_RCTH_MIN
        self._attr_native_max_value = DEFAULT_RCTH_MAX
        self._attr_native_step = 0.5
        self._attr_native_unit_of_measurement = UnitOfTime.HOURS
        self._attr_mode = NumberMode.BOX
        self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> float:
        return round(self._coordinator.data.rcth_hw, 2)

    @property
    def icon(self) -> str | None:
        return "mdi:home-battery-outline"

    async def async_set_native_value(self, value: float) -> None:
        self._coordinator.data.rcth_hw = value
        self._coordinator._notify_listeners()


class SmartHRTRPthLWNumber(SmartHRTBaseNumber):
    """Entité number pour RPth low wind"""

    def __init__(self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "RPth (vent faible)"
        self._attr_unique_id = f"{self._device_id}_rpth_lw"
        self._attr_native_min_value = DEFAULT_RPTH_MIN
        self._attr_native_max_value = DEFAULT_RPTH_MAX
        self._attr_native_step = 0.5
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_mode = NumberMode.BOX
        self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> float:
        return round(self._coordinator.data.rpth_lw, 2)

    @property
    def icon(self) -> str | None:
        return "mdi:home-lightning-bolt-outline"

    async def async_set_native_value(self, value: float) -> None:
        self._coordinator.data.rpth_lw = value
        self._coordinator._notify_listeners()


class SmartHRTRPthHWNumber(SmartHRTBaseNumber):
    """Entité number pour RPth high wind"""

    def __init__(self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "RPth (vent fort)"
        self._attr_unique_id = f"{self._device_id}_rpth_hw"
        self._attr_native_min_value = DEFAULT_RPTH_MIN
        self._attr_native_max_value = DEFAULT_RPTH_MAX
        self._attr_native_step = 0.5
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_mode = NumberMode.BOX
        self._attr_entity_registry_enabled_default = False

    @property
    def native_value(self) -> float:
        return round(self._coordinator.data.rpth_hw, 2)

    @property
    def icon(self) -> str | None:
        return "mdi:home-lightning-bolt-outline"

    async def async_set_native_value(self, value: float) -> None:
        self._coordinator.data.rpth_hw = value
        self._coordinator._notify_listeners()


class SmartHRTRelaxationNumber(SmartHRTBaseNumber):
    """Entité number pour le facteur de relaxation"""

    def __init__(self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "Facteur de relaxation"
        self._attr_unique_id = f"{self._device_id}_relaxation"
        self._attr_native_min_value = 0.0
        self._attr_native_max_value = 15.0
        self._attr_native_step = 0.05
        self._attr_mode = NumberMode.BOX

    @property
    def native_value(self) -> float:
        return self._coordinator.data.relaxation_factor

    @property
    def icon(self) -> str | None:
        return "mdi:brain"

    async def async_set_native_value(self, value: float) -> None:
        _LOGGER.info("Relaxation factor changed to: %s", value)
        self._coordinator.set_relaxation_factor(value)
