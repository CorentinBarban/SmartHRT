"""Config flow et options flow de SmartHRT."""

import copy
import logging
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_NAME,
    CONF_RECOVERYCALC_HOUR,
    CONF_SENSOR_INTERIOR_TEMP,
    CONF_TARGET_HOUR,
    CONF_TSP,
    CONF_WEATHER_ENTITY,
    DEFAULT_TSP,
    DEFAULT_TSP_MAX,
    DEFAULT_TSP_MIN,
    DEFAULT_TSP_STEP,
    DOMAIN,
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
            new_key.description = {"suggested_value": suggested_values[key]}  # type: ignore
        schema[new_key] = val
    _LOGGER.debug("add_suggested_values_to_schema: schema=%s", schema)
    return vol.Schema(schema)


class SmartHRTConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow SmartHRT : nom, puis capteurs et réglages."""

    # Version du schéma, utilisée pour migrer les entrées existantes
    VERSION = 1

    def __init__(self) -> None:
        """Initialise le config flow."""
        super().__init__()
        self._user_inputs: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        """Retourne l'options flow."""
        return SmartHRTOptionsFlow(config_entry)

    async def async_step_user(self, user_input: dict | None = None) -> FlowResult:
        """Étape user : demande le nom de l'intégration."""
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

        _LOGGER.debug(
            "config_flow step user (2). On a reçu les valeurs: %s", user_input
        )
        self._user_inputs.update(user_input)

        # Vérifier les entrées dupliquées basées sur le nom
        await self.async_set_unique_id(user_input[CONF_NAME])
        self._abort_if_unique_id_configured()

        return await self.async_step_sensors()

    async def async_step_sensors(self, user_input: dict | None = None) -> FlowResult:
        """Étape sensors : capteurs, heures et consigne."""
        errors: dict[str, str] = {}

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
                # Entité météo choisie explicitement (pas d'auto-détection)
                vol.Required(CONF_WEATHER_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="weather"),
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

        _LOGGER.debug(
            "config_flow step sensors (2). On a reçu les valeurs: %s", user_input
        )

        # Validation de l'entité météo
        weather_entity_id = user_input.get(CONF_WEATHER_ENTITY)
        if weather_entity_id:
            weather_state = self.hass.states.get(weather_entity_id)
            if weather_state is None:
                errors[CONF_WEATHER_ENTITY] = "weather_not_found"
            elif not self._is_valid_weather_entity(weather_state):
                errors[CONF_WEATHER_ENTITY] = "weather_incompatible"

        # Validation du capteur de température
        temp_sensor_id = user_input.get(CONF_SENSOR_INTERIOR_TEMP)
        if temp_sensor_id:
            temp_state = self.hass.states.get(temp_sensor_id)
            if temp_state is None:
                errors[CONF_SENSOR_INTERIOR_TEMP] = "sensor_not_found"

        # Validation de la consigne dans les limites
        tsp = user_input.get(CONF_TSP, DEFAULT_TSP)
        if not (DEFAULT_TSP_MIN <= tsp <= DEFAULT_TSP_MAX):
            errors[CONF_TSP] = "tsp_out_of_range"

        # Validation de la séquence des horaires
        target_hour = user_input.get(CONF_TARGET_HOUR)
        recoverycalc_hour = user_input.get(CONF_RECOVERYCALC_HOUR)
        if target_hour and recoverycalc_hour:
            if not self._validate_time_sequence(recoverycalc_hour, target_hour):
                errors["base"] = "invalid_time_sequence"

        if errors:
            _LOGGER.debug("Erreurs de validation config_flow: %s", errors)
            return self.async_show_form(
                step_id="sensors",
                data_schema=add_suggested_values_to_schema(
                    data_schema=sensors_form, suggested_values=user_input
                ),
                errors=errors,
            )  # pyright: ignore[reportReturnType]

        self._user_inputs.update(user_input)
        _LOGGER.info(
            "config_flow step sensors (2). L'ensemble de la configuration est: %s",
            self._user_inputs,
        )

        return self.async_create_entry(
            title=self._user_inputs[CONF_NAME], data=self._user_inputs
        )  # pyright: ignore[reportReturnType]

    def _is_valid_weather_entity(self, state) -> bool:
        """Vérifie que l'entité est du domaine weather."""
        if state is None:
            return False
        # Le domaine est vérifié par le selector, mais on vérifie quand même
        return state.domain == "weather"

    def _validate_time_sequence(self, recoverycalc: str, target: str) -> bool:
        """Vérifie que recoverycalc_hour précède target_hour (passage à minuit admis).

        Une séquence recoverycalc < target n'est invalide que si target est
        l'après-midi (probable erreur de saisie). Heures au format HH:MM:SS.
        """
        try:
            rc_parts = recoverycalc.split(":")
            tg_parts = target.split(":")
            rc_minutes = int(rc_parts[0]) * 60 + int(
                rc_parts[1] if len(rc_parts) > 1 else 0
            )
            tg_minutes = int(tg_parts[0]) * 60 + int(
                tg_parts[1] if len(tg_parts) > 1 else 0
            )

            # Cas valides:
            # 1. recoverycalc (23:00) > target (06:00) - passage à minuit implicite
            # 2. target est tôt le matin (avant midi) - toujours OK
            if rc_minutes > tg_minutes:
                return True  # Passage à minuit
            if tg_minutes < 12 * 60:
                return True  # Target le matin

            # Cas invalide: recoverycalc et target dans l'après-midi, rc < tg
            return False
        except (ValueError, IndexError):
            return True  # En cas d'erreur de parsing, on laisse passer


# 'data' : configuration statique (un changement déclenche un rechargement)
STATIC_KEYS = {
    CONF_NAME,
    CONF_SENSOR_INTERIOR_TEMP,
    CONF_WEATHER_ENTITY,
}
# 'options' : réglages dynamiques, appliqués à chaud ; prioritaires sur 'data'
DYNAMIC_KEYS = {CONF_TARGET_HOUR, CONF_RECOVERYCALC_HOUR, CONF_TSP}


class SmartHRTOptionsFlow(OptionsFlow):
    """Options flow SmartHRT : modifie la configuration statique et les réglages dynamiques."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        """Initialise l'options flow à partir de la ConfigEntry existante."""
        super().__init__()
        self._config_entry = config_entry
        # Fusion data + options ; options prioritaire
        self._user_inputs: dict[str, Any] = {
            **config_entry.data,
            **config_entry.options,
        }

    async def async_step_init(self, user_input: dict | None = None) -> FlowResult:
        """Étape init de l'options flow."""
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
                # Entité météo choisie explicitement
                vol.Required(CONF_WEATHER_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="weather")
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

        _LOGGER.debug(
            "option_flow step user (2). On a reçu les valeurs: %s", user_input
        )
        self._user_inputs.update(user_input)

        return await self.async_end()  # pyright: ignore[reportReturnType]

    async def async_end(self) -> FlowResult:
        """Sépare data (statique : capteurs, nom, météo) et options (dynamique : heures, consigne)."""
        new_data = {
            key: self._user_inputs[key]
            for key in STATIC_KEYS
            if key in self._user_inputs
        }

        new_options = {
            key: self._user_inputs[key]
            for key in DYNAMIC_KEYS
            if key in self._user_inputs
        }

        _LOGGER.info(
            "Mise à jour de l'entry %s. Nouvelles data: %s, Nouvelles options: %s",
            self._config_entry.entry_id,
            new_data,
            new_options,
        )

        # Changer data déclenche un rechargement
        if new_data != dict(self._config_entry.data):
            self.hass.config_entries.async_update_entry(
                self._config_entry,
                data=new_data,
            )
            _LOGGER.info("Données statiques mises à jour, rechargement nécessaire")

        # HA stocke ces options dans config_entry.options et déclenche update_listener
        return self.async_create_entry(title="", data=new_options)
