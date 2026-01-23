"""Initialisation du package de l'intégration SmartHRT"""

import logging

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from .const import DOMAIN, PLATFORMS, DATA_COORDINATOR
from .coordinator import SmartHRTCoordinator

_LOGGER = logging.getLogger(__name__)

# Version du schéma de configuration
CONFIG_ENTRY_VERSION = 1


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old entry to current version.

    Cette fonction est appelée par Home Assistant si la version
    de l'entrée de configuration est différente de CONFIG_ENTRY_VERSION.
    """
    _LOGGER.debug(
        "Migrating SmartHRT config entry from version %s to %s",
        entry.version,
        CONFIG_ENTRY_VERSION,
    )

    if entry.version > CONFIG_ENTRY_VERSION:
        # Downgrade non supporté
        _LOGGER.error(
            "Cannot downgrade SmartHRT config entry from version %s to %s",
            entry.version,
            CONFIG_ENTRY_VERSION,
        )
        return False

    # Exemple de migration future:
    # if entry.version == 1:
    #     new_data = {**entry.data, "new_field": "default_value"}
    #     hass.config_entries.async_update_entry(entry, data=new_data, version=2)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Creation des entités à partir d'une configEntry"""

    _LOGGER.debug(
        "Appel de async_setup_entry entry: entry_id='%s', data='%s'",
        entry.entry_id,
        entry.data,
    )

    hass.data.setdefault(DOMAIN, {})

    # Création du coordinateur
    coordinator = SmartHRTCoordinator(hass, entry)
    await coordinator.async_setup()

    # Stockage du coordinateur
    hass.data[DOMAIN][entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
    }

    # Enregistrement de l'écouteur de changement 'update_listener'
    entry.async_on_unload(entry.add_update_listener(update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Déchargement d'une configEntry"""

    # Déchargement du coordinateur
    if entry.entry_id in hass.data[DOMAIN]:
        coordinator = hass.data[DOMAIN][entry.entry_id].get(DATA_COORDINATOR)
        if coordinator:
            await coordinator.async_unload()
        del hass.data[DOMAIN][entry.entry_id]

    # Déchargement des plateformes
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Applique les changements d'options sans recharger l'intégration.

    Les options dynamiques (target_hour, recoverycalc_hour, tsp) peuvent
    être appliquées à chaud via le coordinateur, évitant un rechargement
    complet qui réinitialiserait l'état de la machine à états.
    """
    from .const import CONF_TARGET_HOUR, CONF_RECOVERYCALC_HOUR, CONF_TSP

    coordinator = hass.data[DOMAIN][entry.entry_id].get(DATA_COORDINATOR)
    if not coordinator:
        _LOGGER.warning("Coordinator not found for entry %s", entry.entry_id)
        return

    options = entry.options
    _LOGGER.debug("Applying options update: %s", options)

    # Appliquer les changements d'options au coordinateur
    if CONF_TSP in options:
        coordinator.set_tsp(options[CONF_TSP])

    if CONF_TARGET_HOUR in options:
        target_time = coordinator._parse_time(options[CONF_TARGET_HOUR])
        coordinator.set_target_hour(target_time)

    if CONF_RECOVERYCALC_HOUR in options:
        recoverycalc_time = coordinator._parse_time(options[CONF_RECOVERYCALC_HOUR])
        coordinator.set_recoverycalc_hour(recoverycalc_time)
