""" Implements the SmartHRT switch entities """
import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.switch import SwitchEntity
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
    """Configuration des entités switch à partir de la configuration ConfigEntry"""

    _LOGGER.debug("Calling switch async_setup_entry entry=%s", entry)

    coordinator: SmartHRTCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    entities = [
        SmartHRTSmartHeatingSwitch(coordinator, entry),
        SmartHRTAdaptiveSwitch(coordinator, entry),
    ]
    async_add_entities(entities, True)


class SmartHRTBaseSwitch(SwitchEntity):
    """Classe de base pour les switch SmartHRT"""

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


class SmartHRTSmartHeatingSwitch(SmartHRTBaseSwitch):
    """Switch pour activer/désactiver le mode chauffage intelligent"""

    def __init__(self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "Mode chauffage intelligent"
        self._attr_unique_id = f"{self._device_id}_smartheating_mode"

    @property
    def is_on(self) -> bool:
        return self._coordinator.data.smartheating_mode

    @property
    def icon(self) -> str | None:
        return "mdi:home-thermometer" if self.is_on else "mdi:home-thermometer-outline"

    async def async_turn_on(self, **kwargs) -> None:
        """Activer le mode chauffage intelligent"""
        _LOGGER.info("SmartHeating mode enabled")
        self._coordinator.set_smartheating_mode(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Désactiver le mode chauffage intelligent"""
        _LOGGER.info("SmartHeating mode disabled")
        self._coordinator.set_smartheating_mode(False)


class SmartHRTAdaptiveSwitch(SmartHRTBaseSwitch):
    """Switch pour activer/désactiver le mode adaptatif (auto-calibration)"""

    def __init__(self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry) -> None:
        super().__init__(coordinator, config_entry)
        self._attr_name = "Mode adaptatif"
        self._attr_unique_id = f"{self._device_id}_adaptive_mode"

    @property
    def is_on(self) -> bool:
        return self._coordinator.data.recovery_adaptive_mode

    @property
    def icon(self) -> str | None:
        return "mdi:brain" if self.is_on else "mdi:brain-off-outline"

    async def async_turn_on(self, **kwargs) -> None:
        """Activer le mode adaptatif"""
        _LOGGER.info("Adaptive mode enabled")
        self._coordinator.set_adaptive_mode(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Désactiver le mode adaptatif"""
        _LOGGER.info("Adaptive mode disabled")
        self._coordinator.set_adaptive_mode(False)
