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
    DOMAIN,
    DATA_COORDINATOR,
    SERVICE_CALCULATE_RECOVERY_TIME,
    SERVICE_CALCULATE_RECOVERY_UPDATE_TIME,
    SERVICE_CALCULATE_RCTH_FAST,
    SERVICE_ON_HEATING_STOP,
    SERVICE_ON_RECOVERY_START,
    SERVICE_ON_RECOVERY_END,
    SERVICE_RESET_LEARNING,
    SERVICE_TRIGGER_CALCULATION,
)

_LOGGER = logging.getLogger(__name__)

# Clé pour stocker le flag d'enregistrement des services
DATA_SERVICES_REGISTERED = "services_registered"

# Liste des services disponibles
SERVICES = [
    SERVICE_CALCULATE_RECOVERY_TIME,
    SERVICE_CALCULATE_RECOVERY_UPDATE_TIME,
    SERVICE_CALCULATE_RCTH_FAST,
    SERVICE_ON_HEATING_STOP,
    SERVICE_ON_RECOVERY_START,
    SERVICE_ON_RECOVERY_END,
    SERVICE_RESET_LEARNING,
    SERVICE_TRIGGER_CALCULATION,
]


def _get_coordinator(hass: HomeAssistant, entry_id: str | None):
    """Récupère le coordinator depuis un appel de service.

    Args:
        hass: Instance Home Assistant
        entry_id: ID optionnel de l'entrée de configuration

    Returns:
        Le coordinateur SmartHRT ou None si non trouvé
    """
    if DOMAIN not in hass.data:
        return None

    if entry_id and entry_id in hass.data[DOMAIN]:
        data = hass.data[DOMAIN][entry_id]
        if isinstance(data, dict):
            return data.get(DATA_COORDINATOR)

    # Retourner le premier coordinateur trouvé
    for data in hass.data[DOMAIN].values():
        if isinstance(data, dict) and DATA_COORDINATOR in data:
            return data[DATA_COORDINATOR]
    return None


async def async_setup_services(hass: HomeAssistant) -> None:
    """Enregistre les services SmartHRT.

    Cette fonction est appelée une seule fois lors du setup de la
    première instance de l'intégration. Les services sont partagés
    entre toutes les instances.
    """
    # Vérifier si les services sont déjà enregistrés
    if hass.data.get(DOMAIN, {}).get(DATA_SERVICES_REGISTERED):
        _LOGGER.debug("Services SmartHRT déjà enregistrés")
        return

    schema = vol.Schema({vol.Optional("entry_id"): str})

    async def handle_calculate_recovery_time(call: ServiceCall) -> dict[str, Any]:
        coord = _get_coordinator(hass, call.data.get("entry_id"))
        if not coord:
            return {"success": False, "error": "Coordinator not found"}
        coord.calculate_recovery_time()
        return {
            "recovery_start_hour": (
                coord.data.recovery_start_hour.isoformat()
                if coord.data.recovery_start_hour
                else None
            ),
            "success": True,
        }

    async def handle_calculate_recovery_update_time(
        call: ServiceCall,
    ) -> dict[str, Any]:
        coord = _get_coordinator(hass, call.data.get("entry_id"))
        if not coord:
            return {"success": False, "error": "Coordinator not found"}
        result = coord.calculate_recovery_update_time()
        if result:
            coord.data.recovery_update_hour = result
            coord._schedule_recovery_update(result)
            coord._notify_listeners()
        return {
            "recovery_update_hour": result.isoformat() if result else None,
            "success": True,
        }

    async def handle_calculate_rcth_fast(call: ServiceCall) -> dict[str, Any]:
        coord = _get_coordinator(hass, call.data.get("entry_id"))
        if not coord:
            return {"success": False, "error": "Coordinator not found"}
        coord.calculate_rcth_fast()
        return {"rcth_fast": coord.data.rcth_fast, "success": True}

    async def handle_on_heating_stop(call: ServiceCall) -> dict[str, Any]:
        coord = _get_coordinator(hass, call.data.get("entry_id"))
        if not coord:
            return {"success": False, "error": "Coordinator not found"}
        coord.on_heating_stop()
        return {
            "time_recovery_calc": (
                coord.data.time_recovery_calc.isoformat()
                if coord.data.time_recovery_calc
                else None
            ),
            "success": True,
        }

    async def handle_on_recovery_start(call: ServiceCall) -> dict[str, Any]:
        coord = _get_coordinator(hass, call.data.get("entry_id"))
        if not coord:
            return {"success": False, "error": "Coordinator not found"}
        coord.on_recovery_start()
        return {
            "time_recovery_start": (
                coord.data.time_recovery_start.isoformat()
                if coord.data.time_recovery_start
                else None
            ),
            "rcth_calculated": coord.data.rcth_calculated,
            "success": True,
        }

    async def handle_on_recovery_end(call: ServiceCall) -> dict[str, Any]:
        coord = _get_coordinator(hass, call.data.get("entry_id"))
        if not coord:
            return {"success": False, "error": "Coordinator not found"}
        coord.on_recovery_end()
        return {
            "time_recovery_end": (
                coord.data.time_recovery_end.isoformat()
                if coord.data.time_recovery_end
                else None
            ),
            "rpth_calculated": coord.data.rpth_calculated,
            "success": True,
        }

    async def handle_reset_learning(call: ServiceCall) -> dict[str, Any]:
        """Reset all learned thermal coefficients to defaults."""
        coord = _get_coordinator(hass, call.data.get("entry_id"))
        if not coord:
            return {"success": False, "error": "Coordinator not found"}

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
        """Manually trigger a recovery time calculation."""
        coord = _get_coordinator(hass, call.data.get("entry_id"))
        if not coord:
            return {"success": False, "error": "Coordinator not found"}

        await hass.async_add_executor_job(coord.calculate_recovery_time)
        coord._notify_listeners()

        return {
            "recovery_start_hour": (
                coord.data.recovery_start_hour.isoformat()
                if coord.data.recovery_start_hour
                else None
            ),
            "time_to_recovery_hours": coord.get_time_to_recovery_hours(),
            "success": True,
        }

    # Mapping des services vers leurs handlers
    handlers = {
        SERVICE_CALCULATE_RECOVERY_TIME: handle_calculate_recovery_time,
        SERVICE_CALCULATE_RECOVERY_UPDATE_TIME: handle_calculate_recovery_update_time,
        SERVICE_CALCULATE_RCTH_FAST: handle_calculate_rcth_fast,
        SERVICE_ON_HEATING_STOP: handle_on_heating_stop,
        SERVICE_ON_RECOVERY_START: handle_on_recovery_start,
        SERVICE_ON_RECOVERY_END: handle_on_recovery_end,
        SERVICE_RESET_LEARNING: handle_reset_learning,
        SERVICE_TRIGGER_CALCULATION: handle_trigger_calculation,
    }

    # Enregistrer les services
    for service_name, handler in handlers.items():
        hass.services.async_register(
            DOMAIN,
            service_name,
            handler,
            schema=schema,
            supports_response=SupportsResponse.OPTIONAL,
        )
        _LOGGER.debug("Service enregistré: %s.%s", DOMAIN, service_name)

    # Marquer les services comme enregistrés
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][DATA_SERVICES_REGISTERED] = True
    _LOGGER.info("Services SmartHRT enregistrés avec succès")


async def async_unload_services(hass: HomeAssistant) -> None:
    """Désenregistre les services SmartHRT.

    Cette fonction est appelée uniquement lorsque la dernière instance
    de l'intégration est déchargée.
    """
    if DOMAIN not in hass.data:
        return

    # Compter les coordinateurs restants (exclure les clés spéciales)
    remaining_coordinators = sum(
        1
        for key, data in hass.data[DOMAIN].items()
        if isinstance(data, dict) and DATA_COORDINATOR in data
    )

    # Ne désenregistrer que si c'est la dernière instance
    if remaining_coordinators > 0:
        _LOGGER.debug(
            "Services SmartHRT conservés (%d instance(s) restante(s))",
            remaining_coordinators,
        )
        return

    # Désenregistrer les services
    for service_name in SERVICES:
        if hass.services.has_service(DOMAIN, service_name):
            hass.services.async_remove(DOMAIN, service_name)

    # Supprimer le flag
    if DATA_SERVICES_REGISTERED in hass.data.get(DOMAIN, {}):
        del hass.data[DOMAIN][DATA_SERVICES_REGISTERED]

    _LOGGER.info("Services SmartHRT désenregistrés")
