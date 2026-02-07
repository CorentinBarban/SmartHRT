"""Initialisation du package de l'intégration SmartHRT.

ADR implémentées dans ce module:
- ADR-001: Architecture globale (setup/async_unload_entry)
- ADR-012: Exposition entités pour Lovelace (forward_entry_setups)
- ADR-016: Nettoyage des entités time obsolètes
- ADR-045: Validation Pydantic au runtime pour la configuration
"""

import logging

from pydantic import ValidationError

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    PLATFORMS,
    DATA_COORDINATOR,
    CONF_TARGET_HOUR,
    CONF_RECOVERYCALC_HOUR,
    CONF_TSP,
    CONF_NAME,
    CONF_SENSOR_INTERIOR_TEMP,
    CONF_WEATHER_ENTITY,
    DEFAULT_TSP,
)
from .coordinator import SmartHRTCoordinator
from .services import async_setup_services, async_unload_services
from .data_model import ConfigFlowDataModel

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


async def _remove_obsolete_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Supprime les entités obsolètes du registre (ADR-016).

    Les entités time en lecture seule (recoverystart_hour, recoveryupdate_hour)
    ont été supprimées et remplacées par des sensors timestamp.
    Le sensor recovery_start_sensor (texte) a été supprimé car redondant.
    Les sensors timestamp target_hour et recoverycalc_hour ont été renommés
    pour éviter les conflits d'unique_id avec les entités time.
    Cette fonction nettoie le registre des anciennes entités.
    """
    entity_reg = er.async_get(hass)

    # Liste des entités obsolètes à supprimer (unique_id, platform)
    obsolete_entities = [
        (f"{entry.entry_id}_recoverystart_hour", "time"),  # time.recoverystart_hour
        (f"{entry.entry_id}_recoveryupdate_hour", "time"),  # time.recoveryupdate_hour
        (
            f"{entry.entry_id}_recovery_start_sensor",
            "sensor",
        ),  # sensor avec label (texte)
        # Migration v1.1: sensors timestamp renommés pour éviter conflit avec time entities
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
    """Creation des entités à partir d'une configEntry.

    ADR-001: Point d'entrée principal de l'intégration.
    ADR-012: Configure les plateformes (sensor, number, time, switch) pour Lovelace.
    """

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

    # Nettoyer les entités obsolètes (ADR-016)
    await _remove_obsolete_entities(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Enregistrer les services (une seule fois pour toutes les instances)
    await async_setup_services(hass)

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
    result = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Désenregistrer les services si c'est la dernière instance
    await async_unload_services(hass)

    return result


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Applique les changements d'options sans recharger l'intégration.

    ADR-045: Utilise la validation Pydantic avant d'appliquer les options.

    Les options dynamiques (target_hour, recoverycalc_hour, tsp) peuvent
    être appliquées à chaud via le coordinateur, évitant un rechargement
    complet qui réinitialiserait l'état de la machine à états.
    """
    coordinator = hass.data[DOMAIN][entry.entry_id].get(DATA_COORDINATOR)
    if not coordinator:
        _LOGGER.warning("Coordinator not found for entry %s", entry.entry_id)
        return

    options = entry.options
    _LOGGER.debug("Applying options update: %s", options)

    # ADR-045: Validation Pydantic avant application
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
        _LOGGER.error("ADR-045: Configuration invalide: %s", e)
        # Notifier l'utilisateur via persistent_notification
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

    # Appliquer uniquement si la validation a réussi
    if CONF_TSP in options:
        coordinator.set_tsp(validated.tsp)

    if CONF_TARGET_HOUR in options:
        coordinator.set_target_hour(validated.target_hour_as_time)

    if CONF_RECOVERYCALC_HOUR in options:
        coordinator.set_recoverycalc_hour(validated.recoverycalc_hour_as_time)

    _LOGGER.info(
        "ADR-045: Configuration validée et appliquée (tsp=%.1f, target=%s, recovery=%s)",
        validated.tsp,
        validated.target_hour,
        validated.recoverycalc_hour,
    )
