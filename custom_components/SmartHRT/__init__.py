"""Initialisation de l'intégration SmartHRT (setup, unload, migration, options à chaud)."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pydantic import ValidationError

from .const import (
    CONF_NAME,
    CONF_RECOVERYCALC_HOUR,
    CONF_SENSOR_INTERIOR_TEMP,
    CONF_TARGET_HOUR,
    CONF_TSP,
    CONF_WEATHER_ENTITY,
    DATA_COORDINATOR,
    DEFAULT_TSP,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import SmartHRTCoordinator
from .models import ConfigFlowDataModel
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)

# Version du schéma de configuration
CONFIG_ENTRY_VERSION = 1


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migre une entrée de configuration vers la version courante."""
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


async def _remove_obsolete_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Supprime du registre les entités d'anciennes versions (unique_id obsolètes)."""
    entity_reg = er.async_get(hass)

    # (unique_id, platform)
    obsolete_entities = [
        (f"{entry.entry_id}_recoverystart_hour", "time"),  # time.recoverystart_hour
        (f"{entry.entry_id}_recoveryupdate_hour", "time"),  # time.recoveryupdate_hour
        (
            f"{entry.entry_id}_recovery_start_sensor",
            "sensor",
        ),  # sensor avec label (texte)
        # Sensors timestamp renommés (_timestamp) pour éviter un conflit d'unique_id avec les entités time
        (
            f"{entry.entry_id}_target_hour",
            "sensor",
        ),  # ancien sensor timestamp -> _target_hour_timestamp
        (
            f"{entry.entry_id}_recoverycalc_hour",
            "sensor",
        ),  # ancien sensor timestamp -> _recoverycalc_hour_timestamp
    ]

    for unique_id, platform in obsolete_entities:
        entity_id = entity_reg.async_get_entity_id(platform, DOMAIN, unique_id)
        if entity_id:
            _LOGGER.info(
                "Suppression de l'entité obsolète: %s (unique_id: %s, platform: %s)",
                entity_id,
                unique_id,
                platform,
            )
            entity_reg.async_remove(entity_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Crée le coordinateur, les plateformes et les services à partir d'une configEntry."""

    _LOGGER.debug(
        "Appel de async_setup_entry entry: entry_id='%s', data='%s'",
        entry.entry_id,
        entry.data,
    )

    hass.data.setdefault(DOMAIN, {})

    coordinator = SmartHRTCoordinator(hass, entry)
    await coordinator.async_setup()

    hass.data[DOMAIN][entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
    }

    entry.async_on_unload(entry.add_update_listener(update_listener))

    await _remove_obsolete_entities(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Enregistrer les services (une seule fois pour toutes les instances)
    await async_setup_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Décharge une configEntry."""

    if entry.entry_id in hass.data[DOMAIN]:
        coordinator = hass.data[DOMAIN][entry.entry_id].get(DATA_COORDINATOR)
        if coordinator:
            await coordinator.async_unload()
        del hass.data[DOMAIN][entry.entry_id]

    result = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Désenregistrer les services si c'est la dernière instance
    await async_unload_services(hass)

    return result


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Applique les options validées à chaud, sans recharger l'intégration.

    Un rechargement réinitialiserait l'état de la machine à états.
    """
    coordinator = hass.data[DOMAIN][entry.entry_id].get(DATA_COORDINATOR)
    if not coordinator:
        _LOGGER.warning("Coordinator not found for entry %s", entry.entry_id)
        return

    options = entry.options
    _LOGGER.debug("Applying options update: %s", options)

    # Validation avant application
    try:
        validated = ConfigFlowDataModel(
            name=entry.data.get(CONF_NAME, "SmartHRT"),
            target_hour=options.get(
                CONF_TARGET_HOUR,
                entry.data.get(CONF_TARGET_HOUR, "06:00:00"),
            ),
            recoverycalc_hour=options.get(
                CONF_RECOVERYCALC_HOUR,
                entry.data.get(CONF_RECOVERYCALC_HOUR, "23:00:00"),
            ),
            tsp=options.get(CONF_TSP, entry.data.get(CONF_TSP, DEFAULT_TSP)),
            sensor_interior_temperature=entry.data.get(
                CONF_SENSOR_INTERIOR_TEMP, "sensor.temperature"
            ),
            weather_entity=entry.data.get(CONF_WEATHER_ENTITY, "weather.home"),
        )
    except ValidationError as e:
        _LOGGER.error("Configuration invalide: %s", e)
        await hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "title": "SmartHRT - Configuration invalide",
                "message": f"Erreur de validation: {e}",
                "notification_id": "smarthrt_config_error",
            },
        )
        return  # Ne pas appliquer la configuration invalide

    if CONF_TSP in options:
        coordinator.set_tsp(validated.tsp)

    if CONF_TARGET_HOUR in options:
        coordinator.set_target_hour(validated.target_hour_as_time)

    if CONF_RECOVERYCALC_HOUR in options:
        coordinator.set_recoverycalc_hour(validated.recoverycalc_hour_as_time)

    _LOGGER.info(
        "Configuration validée et appliquée (tsp=%.1f, target=%s, recovery=%s)",
        validated.tsp,
        validated.target_hour,
        validated.recoverycalc_hour,
    )
