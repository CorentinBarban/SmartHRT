"""Gestion centralisée des services SmartHRT.

Ce module gère l'enregistrement et le désenregistrement des services
au niveau du domaine, évitant les race conditions lorsque plusieurs
instances de l'intégration sont configurées.
"""

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse

from .const import (
    DATA_COORDINATOR,
    DOMAIN,
    SERVICE_END_RECOVERY,
    SERVICE_FORCE_MONITORING,
    SERVICE_GET_STATE,
    SERVICE_RESET_LEARNING,
    SERVICE_START_HEATING_CYCLE,
    SERVICE_START_RECOVERY,
    SERVICE_STOP_HEATING,
    SERVICE_TRIGGER_CALCULATION,
)

_LOGGER = logging.getLogger(__name__)

# Flag dans hass.data[DOMAIN] : services déjà enregistrés (partagés entre instances)
DATA_SERVICES_REGISTERED = "services_registered"

SERVICES = [
    SERVICE_START_HEATING_CYCLE,
    SERVICE_STOP_HEATING,
    SERVICE_START_RECOVERY,
    SERVICE_END_RECOVERY,
    SERVICE_GET_STATE,
    SERVICE_FORCE_MONITORING,
    # Services utilitaires
    SERVICE_RESET_LEARNING,
    SERVICE_TRIGGER_CALCULATION,
]


def _get_coordinator(hass: HomeAssistant, entry_id: str | None):
    """Retourne le coordinateur ciblé par entry_id (ou le premier), None si introuvable."""
    if DOMAIN not in hass.data:
        _LOGGER.error("Aucune instance SmartHRT configurée")
        return None

    available_coordinators = {
        key: data[DATA_COORDINATOR]
        for key, data in hass.data[DOMAIN].items()
        if isinstance(data, dict) and DATA_COORDINATOR in data
    }

    if not available_coordinators:
        _LOGGER.error("Aucun coordinateur SmartHRT trouvé")
        return None

    if entry_id:
        if entry_id in available_coordinators:
            _LOGGER.debug("Utilisation du coordinateur pour entry_id: %s", entry_id)
            return available_coordinators[entry_id]
        else:
            _LOGGER.error(
                "Entry ID '%s' non trouvé. Instances disponibles: %s",
                entry_id,
                list(available_coordinators.keys()),
            )
            return None

    # Sans entry_id et avec plusieurs instances : premier coordinateur, avec avertissement
    if len(available_coordinators) > 1:
        _LOGGER.warning(
            "Plusieurs instances SmartHRT détectées (%d) mais aucun entry_id fourni. "
            "Utilisation de la première instance. Instances disponibles: %s. "
            "Veuillez spécifier 'entry_id' pour cibler une instance spécifique.",
            len(available_coordinators),
            list(available_coordinators.keys()),
        )

    first_entry_id = next(iter(available_coordinators))
    _LOGGER.debug("Utilisation de l'instance par défaut: %s", first_entry_id)
    return available_coordinators[first_entry_id]


async def async_setup_services(hass: HomeAssistant) -> None:
    """Enregistre les services SmartHRT, partagés par toutes les instances (une seule fois)."""
    if hass.data.get(DOMAIN, {}).get(DATA_SERVICES_REGISTERED):
        _LOGGER.debug("Services SmartHRT déjà enregistrés")
        return

    schema = vol.Schema({vol.Optional("entry_id"): str})

    async def handle_reset_learning(call: ServiceCall) -> dict[str, Any]:
        """Remet les coefficients thermiques appris à leurs valeurs par défaut."""
        entry_id = call.data.get("entry_id")
        coord = _get_coordinator(hass, entry_id)
        if not coord:
            error_msg = (
                f"Coordinateur non trouvé pour entry_id={entry_id}"
                if entry_id
                else "Aucun coordinateur SmartHRT disponible"
            )
            _LOGGER.error(error_msg)
            return {"success": False, "error": error_msg}

        await coord.reset_learning()
        return {
            "rcth": coord.data.rcth,
            "rpth": coord.data.rpth,
            "rcth_lw": coord.data.rcth_lw,
            "rcth_hw": coord.data.rcth_hw,
            "rpth_lw": coord.data.rpth_lw,
            "rpth_hw": coord.data.rpth_hw,
            "success": True,
            "message": "Learning reset to defaults",
        }

    async def handle_trigger_calculation(call: ServiceCall) -> dict[str, Any]:
        """Déclenche manuellement le calcul de l'heure de relance."""
        entry_id = call.data.get("entry_id")
        coord = _get_coordinator(hass, entry_id)
        if not coord:
            error_msg = (
                f"Coordinateur non trouvé pour entry_id={entry_id}"
                if entry_id
                else "Aucun coordinateur SmartHRT disponible"
            )
            _LOGGER.error(error_msg)
            return {"success": False, "error": error_msg}

        return await coord.async_trigger_calculation()

    async def handle_start_heating_cycle(call: ServiceCall) -> dict[str, Any]:
        """Démarre un nouveau cycle de chauffage (HEATING_ON)."""
        entry_id = call.data.get("entry_id")
        coord = _get_coordinator(hass, entry_id)
        if not coord:
            error_msg = (
                f"Coordinateur non trouvé pour entry_id={entry_id}"
                if entry_id
                else "Aucun coordinateur SmartHRT disponible"
            )
            _LOGGER.error(error_msg)
            return {"success": False, "error": error_msg}

        return await coord.async_manual_stop_heating()

    async def handle_stop_heating(call: ServiceCall) -> dict[str, Any]:
        """Arrête le chauffage et démarre la surveillance (DETECTING_LAG → MONITORING)."""
        entry_id = call.data.get("entry_id")
        coord = _get_coordinator(hass, entry_id)
        if not coord:
            error_msg = (
                f"Coordinateur non trouvé pour entry_id={entry_id}"
                if entry_id
                else "Aucun coordinateur SmartHRT disponible"
            )
            _LOGGER.error(error_msg)
            return {"success": False, "error": error_msg}

        return await coord.async_start_heating_cycle()

    async def handle_start_recovery(call: ServiceCall) -> dict[str, Any]:
        """Démarre la relance de chauffage (RECOVERY → HEATING_PROCESS)."""
        entry_id = call.data.get("entry_id")
        coord = _get_coordinator(hass, entry_id)
        if not coord:
            error_msg = (
                f"Coordinateur non trouvé pour entry_id={entry_id}"
                if entry_id
                else "Aucun coordinateur SmartHRT disponible"
            )
            _LOGGER.error(error_msg)
            return {"success": False, "error": error_msg}

        return await coord.async_manual_start_recovery()

    async def handle_end_recovery(call: ServiceCall) -> dict[str, Any]:
        """Termine la relance de chauffage (HEATING_PROCESS → HEATING_ON)."""
        entry_id = call.data.get("entry_id")
        coord = _get_coordinator(hass, entry_id)
        if not coord:
            error_msg = (
                f"Coordinateur non trouvé pour entry_id={entry_id}"
                if entry_id
                else "Aucun coordinateur SmartHRT disponible"
            )
            _LOGGER.error(error_msg)
            return {"success": False, "error": error_msg}

        return await coord.async_manual_end_recovery()

    async def handle_get_state(call: ServiceCall) -> dict[str, Any]:
        """Retourne l'état actuel de la machine à états avec détails."""
        entry_id = call.data.get("entry_id")
        coord = _get_coordinator(hass, entry_id)
        if not coord:
            error_msg = (
                f"Coordinateur non trouvé pour entry_id={entry_id}"
                if entry_id
                else "Aucun coordinateur SmartHRT disponible"
            )
            _LOGGER.error(error_msg)
            return {"success": False, "error": error_msg}

        return coord.get_state_dict()

    async def handle_force_monitoring(call: ServiceCall) -> dict[str, Any]:
        """Force la sortie de l'état DETECTING_LAG vers MONITORING.

        Utilisé quand la baisse de température (0.2°C) n'est pas détectée
        (pièces très isolées ou temps doux). Désactive l'apprentissage RCth
        pour ce cycle pour protéger le modèle thermique.
        """
        entry_id = call.data.get("entry_id")
        coord = _get_coordinator(hass, entry_id)
        if not coord:
            error_msg = (
                f"Coordinateur non trouvé pour entry_id={entry_id}"
                if entry_id
                else "Aucun coordinateur SmartHRT disponible"
            )
            _LOGGER.error(error_msg)
            return {"success": False, "error": error_msg}

        return await coord.async_force_monitoring()

    handlers = {
        SERVICE_START_HEATING_CYCLE: handle_start_heating_cycle,
        SERVICE_STOP_HEATING: handle_stop_heating,
        SERVICE_START_RECOVERY: handle_start_recovery,
        SERVICE_END_RECOVERY: handle_end_recovery,
        SERVICE_GET_STATE: handle_get_state,
        SERVICE_FORCE_MONITORING: handle_force_monitoring,
        # Services utilitaires
        SERVICE_RESET_LEARNING: handle_reset_learning,
        SERVICE_TRIGGER_CALCULATION: handle_trigger_calculation,
    }

    for service_name, handler in handlers.items():
        hass.services.async_register(
            DOMAIN,
            service_name,
            handler,
            schema=schema,
            supports_response=SupportsResponse.OPTIONAL,
        )
        _LOGGER.debug("Service enregistré: %s.%s", DOMAIN, service_name)

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][DATA_SERVICES_REGISTERED] = True
    _LOGGER.info("Services SmartHRT enregistrés avec succès")


async def async_unload_services(hass: HomeAssistant) -> None:
    """Désenregistre les services SmartHRT quand la dernière instance est déchargée."""
    if DOMAIN not in hass.data:
        return

    # Coordinateurs restants (hors clés spéciales comme le flag d'enregistrement)
    remaining_coordinators = sum(
        1
        for key, data in hass.data[DOMAIN].items()
        if isinstance(data, dict) and DATA_COORDINATOR in data
    )

    if remaining_coordinators > 0:
        _LOGGER.debug(
            "Services SmartHRT conservés (%d instance(s) restante(s))",
            remaining_coordinators,
        )
        return

    for service_name in SERVICES:
        if hass.services.has_service(DOMAIN, service_name):
            hass.services.async_remove(DOMAIN, service_name)

    if DATA_SERVICES_REGISTERED in hass.data.get(DOMAIN, {}):
        del hass.data[DOMAIN][DATA_SERVICES_REGISTERED]

    _LOGGER.info("Services SmartHRT désenregistrés")
