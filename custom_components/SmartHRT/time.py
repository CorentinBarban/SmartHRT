""" Implements the SmartHRT time entities """
import logging
from datetime import time as dt_time

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.components.time import TimeEntity
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
    """Configuration des entités time à partir de la configuration ConfigEntry"""

    _LOGGER.debug("Calling time async_setup_entry entry=%s", entry)

    coordinator: SmartHRTCoordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    entities = [
        SmartHRTTargetHourTime(coordinator, entry),
    ]
    async_add_entities(entities, True)


class SmartHRTTargetHourTime(TimeEntity):
    """Entité time pour l'heure cible"""

    def __init__(self, coordinator: SmartHRTCoordinator, config_entry: ConfigEntry) -> None:
        """Initialisation de l'entité"""
        self._coordinator = coordinator
        self._config_entry = config_entry
        self._device_id = config_entry.entry_id
        self._device_name = config_entry.data.get(CONF_NAME, "SmartHRT")

        # Attributs de l'entité
        self._attr_has_entity_name = True
        self._attr_name = "Heure cible"
        self._attr_unique_id = f"{self._device_id}_target_hour"

    @property
    def native_value(self) -> dt_time:
        """Retourne l'heure cible depuis le coordinator"""
        return self._coordinator.data.target_hour

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
    def icon(self) -> str | None:
        return "mdi:clock-end"

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

    async def async_set_value(self, value: dt_time) -> None:
        """Mise à jour de l'heure cible"""
        _LOGGER.info("Target hour changed to: %s", value)
        self._coordinator.set_target_hour(value)
