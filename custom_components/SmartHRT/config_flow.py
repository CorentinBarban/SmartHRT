"""Le Config Flow pour SmartHRT"""

import logging
from typing import Any
import copy
from collections.abc import Mapping

from homeassistant.core import callback
from homeassistant.config_entries import ConfigFlow, OptionsFlow, ConfigEntry
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN

import voluptuous as vol

from .const import (
    DOMAIN,
    CONF_NAME,
    CONF_TARGET_HOUR,
    CONF_RECOVERYCALC_HOUR,
    CONF_SENSOR_INTERIOR_TEMP,
    CONF_PHONE_ALARM,
    CONF_TSP,
    DEFAULT_TSP,
    DEFAULT_TSP_MIN,
    DEFAULT_TSP_MAX,
    DEFAULT_TSP_STEP,
    DEFAULT_RECOVERYCALC_HOUR,
)

_LOGGER = logging.getLogger(__name__)


def add_suggested_values_to_schema(
    data_schema: vol.Schema, suggested_values: Mapping[str, Any]
) -> vol.Schema:
    """Make a copy of the schema, populated with suggested values.

    For each schema marker matching items in `suggested_values`,
    the `suggested_value` will be set. The existing `suggested_value` will
    be left untouched if there is no matching item.
    """
    schema = {}
    for key, val in data_schema.schema.items():
        new_key = key
        if key in suggested_values and isinstance(key, vol.Marker):
            # Copy the marker to not modify the flow schema
            new_key = copy.copy(key)
            new_key.description = {
                "suggested_value": suggested_values[key]
            }  # type: ignore
        schema[new_key] = val
    _LOGGER.debug("add_suggested_values_to_schema: schema=%s", schema)
    return vol.Schema(schema)


class SmartHRTConfigFlow(ConfigFlow, domain=DOMAIN):
    """La classe qui implémente le config flow pour SmartHRT.
    Elle doit dériver de ConfigFlow"""

    # La version de notre configFlow. Va permettre de migrer les entités
    # vers une version plus récente en cas de changement
    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        super().__init__()
        self._user_inputs: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        """Get options flow for this handler"""
        return SmartHRTOptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Gestion de l'étape 'user'. Point d'entrée du configFlow.
        Demande le nom de l'intégration.
        """
        user_form = vol.Schema(
            {
                vol.Required(CONF_NAME): str,
            }
        )

        if user_input is None:
            _LOGGER.debug(
                "config_flow step user (1). 1er appel : pas de user_input -> "
                "on affiche le form user_form"
            )
            return self.async_show_form(
                step_id="user",
                data_schema=add_suggested_values_to_schema(
                    data_schema=user_form, suggested_values=self._user_inputs
                ),
            )  # pyright: ignore[reportReturnType]

        # 2ème appel : il y a des user_input -> on stocke le résultat
        _LOGGER.debug(
            "config_flow step user (2). On a reçu les valeurs: %s", user_input
        )
        # On mémorise les user_input
        self._user_inputs.update(user_input)

        # Vérifier les entrées dupliquées basées sur le nom
        await self.async_set_unique_id(user_input[CONF_NAME])
        self._abort_if_unique_id_configured()

        # On appelle le step 2 (configuration des capteurs)
        return await self.async_step_sensors()

    async def async_step_sensors(self, user_input: dict | None = None) -> FlowResult:
        """Gestion de l'étape sensors. Configuration des capteurs et paramètres."""
        sensors_form = vol.Schema(
            {
                # Heure cible (Wake Up Time)
                vol.Required(CONF_TARGET_HOUR): selector.TimeSelector(),
                # Heure de coupure chauffage (soir)
                vol.Required(
                    CONF_RECOVERYCALC_HOUR, default="23:00:00"
                ): selector.TimeSelector(),
                # Capteur de température intérieure
                vol.Required(CONF_SENSOR_INTERIOR_TEMP): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=SENSOR_DOMAIN),
                ),
                # Capteur d'alarme du téléphone
                vol.Optional(CONF_PHONE_ALARM): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=SENSOR_DOMAIN),
                ),
                # Consigne de température (Set Point)
                vol.Required(CONF_TSP, default=DEFAULT_TSP): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=DEFAULT_TSP_MIN,
                        max=DEFAULT_TSP_MAX,
                        step=DEFAULT_TSP_STEP,
                        unit_of_measurement="°C",
                        mode=selector.NumberSelectorMode.BOX,
                    ),
                ),
            }
        )

        if user_input is None:
            _LOGGER.debug(
                "config_flow step sensors (1). 1er appel : pas de user_input -> "
                "on affiche le form sensors_form"
            )
            return self.async_show_form(
                step_id="sensors",
                data_schema=add_suggested_values_to_schema(
                    data_schema=sensors_form, suggested_values=self._user_inputs
                ),
            )  # pyright: ignore[reportReturnType]

        # 2ème appel : il y a des user_input -> on stocke le résultat
        _LOGGER.debug(
            "config_flow step sensors (2). On a reçu les valeurs: %s", user_input
        )

        # On mémorise les user_input
        self._user_inputs.update(user_input)
        _LOGGER.info(
            "config_flow step sensors (2). L'ensemble de la configuration est: %s",
            self._user_inputs,
        )

        return self.async_create_entry(
            title=self._user_inputs[CONF_NAME], data=self._user_inputs
        )  # pyright: ignore[reportReturnType]


class SmartHRTOptionsFlow(OptionsFlow):
    """La classe qui implémente le option flow pour SmartHRT.
    Elle doit dériver de OptionsFlow"""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialisation de l'option flow. On a le ConfigEntry existant en entrée"""
        super().__init__()
        self._config_entry = config_entry
        # On initialise les user_inputs avec les données du configEntry
        self._user_inputs: dict[str, Any] = dict(config_entry.data)

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        """Gestion de l'étape 'init'. Point d'entrée du optionsFlow."""
        option_form = vol.Schema(
            {
                vol.Required(CONF_NAME): str,
                # Heure cible (Wake Up Time)
                vol.Required(CONF_TARGET_HOUR): selector.TimeSelector(),
                # Heure de coupure chauffage (soir)
                vol.Required(
                    CONF_RECOVERYCALC_HOUR, default="23:00:00"
                ): selector.TimeSelector(),
                # Capteur de température intérieure
                vol.Required(CONF_SENSOR_INTERIOR_TEMP): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
                ),
                # Capteur d'alarme du téléphone
                vol.Optional(CONF_PHONE_ALARM): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
                ),
                # Consigne de température (Set Point)
                vol.Required(CONF_TSP, default=DEFAULT_TSP): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=DEFAULT_TSP_MIN,
                        max=DEFAULT_TSP_MAX,
                        step=DEFAULT_TSP_STEP,
                        unit_of_measurement="°C",
                        mode=selector.NumberSelectorMode.BOX,
                    ),
                ),
            }
        )

        if user_input is None:
            _LOGGER.debug(
                "option_flow step user (1). 1er appel : pas de user_input -> "
                "on affiche le form user_form"
            )
            return self.async_show_form(
                step_id="init",
                data_schema=add_suggested_values_to_schema(
                    data_schema=option_form, suggested_values=self._user_inputs
                ),
            )  # pyright: ignore[reportReturnType]

        # 2ème appel : il y a des user_input -> on stocke le résultat
        _LOGGER.debug(
            "option_flow step user (2). On a reçu les valeurs: %s", user_input
        )
        # On mémorise les user_input
        self._user_inputs.update(user_input)

        # On appelle le step de fin pour enregistrer les modifications
        return await self.async_end()  # pyright: ignore[reportReturnType]

    async def async_end(self) -> FlowResult:
        """Finalization of the ConfigEntry creation"""
        _LOGGER.info(
            "Recreation de l'entry %s. La nouvelle config est maintenant : %s",
            self._config_entry.entry_id,
            self._user_inputs,
        )
        # Modification des data de la configEntry
        # (et non pas ajout d'un objet options dans la configEntry)
        self.hass.config_entries.async_update_entry(
            self._config_entry, data=self._user_inputs
        )
        # Retourne un entry vide pour finaliser le flow
        return self.async_create_entry(title="", data={})
