"""Coordinator pour SmartHRT - Gère la logique de chauffage intelligent"""

import logging
import math
from datetime import datetime, timedelta, time as dt_time
from dataclasses import dataclass, field
from typing import Callable, Any
from collections import deque

import voluptuous as vol

from homeassistant.core import HomeAssistant, callback, ServiceCall, SupportsResponse
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import (
    async_track_time_interval,
    async_track_state_change_event,
    async_track_point_in_time,
)
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_NAME,
    CONF_TARGET_HOUR,
    CONF_RECOVERYCALC_HOUR,
    CONF_SENSOR_INTERIOR_TEMP,
    CONF_PHONE_ALARM,
    CONF_TSP,
    DEFAULT_TSP,
    DEFAULT_RCTH,
    DEFAULT_RPTH,
    DEFAULT_RELAXATION_FACTOR,
    WIND_HIGH,
    WIND_LOW,
    SERVICE_CALCULATE_RECOVERY_TIME,
    SERVICE_CALCULATE_RECOVERY_UPDATE_TIME,
    SERVICE_CALCULATE_RCTH_FAST,
    SERVICE_ON_HEATING_STOP,
    SERVICE_ON_RECOVERY_START,
    SERVICE_ON_RECOVERY_END,
    DATA_COORDINATOR,
    FORECAST_HOURS,
    TEMP_DECREASE_THRESHOLD,
    DEFAULT_RECOVERYCALC_HOUR,
)

_LOGGER = logging.getLogger(__name__)

# Liste des services disponibles
SERVICES = [
    SERVICE_CALCULATE_RECOVERY_TIME,
    SERVICE_CALCULATE_RECOVERY_UPDATE_TIME,
    SERVICE_CALCULATE_RCTH_FAST,
    SERVICE_ON_HEATING_STOP,
    SERVICE_ON_RECOVERY_START,
    SERVICE_ON_RECOVERY_END,
]


@dataclass
class SmartHRTData:
    """Données du système SmartHRT"""

    # Configuration
    name: str = "SmartHRT"
    tsp: float = DEFAULT_TSP
    target_hour: dt_time = field(default_factory=lambda: dt_time(6, 0, 0))
    recoverycalc_hour: dt_time = field(default_factory=lambda: dt_time(23, 0, 0))

    # Modes
    smartheating_mode: bool = True
    recovery_adaptive_mode: bool = True
    recovery_calc_mode: bool = False
    rp_calc_mode: bool = False
    temp_lag_detection_active: bool = False

    # Coefficients thermiques
    rcth: float = DEFAULT_RCTH
    rpth: float = DEFAULT_RPTH
    rcth_lw: float = DEFAULT_RCTH
    rcth_hw: float = DEFAULT_RCTH
    rpth_lw: float = DEFAULT_RPTH
    rpth_hw: float = DEFAULT_RPTH
    rcth_fast: float = 0.0
    rcth_calculated: float = 0.0
    rpth_calculated: float = 0.0
    relaxation_factor: float = DEFAULT_RELAXATION_FACTOR

    # Températures actuelles
    interior_temp: float | None = None
    exterior_temp: float | None = None
    wind_speed: float = 0.0  # m/s
    windchill: float | None = None

    # Prévisions météo
    wind_speed_forecast_avg: float = 0.0  # km/h
    temperature_forecast_avg: float = 0.0  # °C
    wind_speed_avg: float = 0.0  # m/s - moyenne sur 4h

    # Températures de référence
    temp_recovery_calc: float = 17.0
    temp_recovery_start: float = 17.0
    temp_recovery_end: float = 17.0
    text_recovery_calc: float = 0.0
    text_recovery_start: float = 0.0
    text_recovery_end: float = 0.0

    # Timestamps
    time_recovery_calc: datetime | None = None
    time_recovery_start: datetime | None = None
    time_recovery_end: datetime | None = None
    recovery_start_hour: datetime | None = None
    recovery_update_hour: datetime | None = None

    # Délai de lag avant baisse température
    stop_lag_duration: float = 0.0  # secondes

    # Alarme téléphone
    phone_alarm: str | None = None

    # Historique pour calcul de moyenne de vent
    wind_speed_history: deque = field(
        default_factory=lambda: deque(maxlen=240)
    )  # 4h à 1 sample/min


class SmartHRTCoordinator:
    """Coordinateur central pour SmartHRT"""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._listeners: list[Callable[[], None]] = []
        self._unsub_listeners: list = []
        self._unsub_time_triggers: list = []

        self.data = SmartHRTData(
            name=entry.data.get(CONF_NAME, "SmartHRT"),
            tsp=entry.data.get(CONF_TSP, DEFAULT_TSP),
            target_hour=self._parse_time(entry.data.get(CONF_TARGET_HOUR, "06:00:00")),
            recoverycalc_hour=self._parse_time(
                entry.data.get(CONF_RECOVERYCALC_HOUR, DEFAULT_RECOVERYCALC_HOUR)
            ),
        )

        self._interior_temp_sensor_id = entry.data.get(CONF_SENSOR_INTERIOR_TEMP)
        self._phone_alarm_sensor_id = entry.data.get(CONF_PHONE_ALARM)

    @staticmethod
    def _parse_time(time_str: str) -> dt_time:
        """Parse une chaîne de temps en objet time"""
        try:
            parts = time_str.split(":")
            return dt_time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
        except (ValueError, IndexError):
            return dt_time(6, 0, 0)

    # ─────────────────────────────────────────────────────────────────────────
    # Setup / Unload
    # ─────────────────────────────────────────────────────────────────────────

    async def async_setup(self) -> None:
        """Configuration asynchrone du coordinateur"""
        _LOGGER.debug(
            "Configuration SmartHRT '%s' - TSP=%.1f°C, target_hour=%s, recoverycalc_hour=%s",
            self.data.name,
            self.data.tsp,
            self.data.target_hour,
            self.data.recoverycalc_hour,
        )

        await self._update_initial_states()
        self._setup_listeners()
        self._setup_time_triggers()
        await self._register_services()
        await self._update_weather_forecasts()
        self.calculate_recovery_time()

    def _setup_listeners(self) -> None:
        """Configure les listeners pour les capteurs"""
        sensors = [
            s for s in [self._interior_temp_sensor_id, self._phone_alarm_sensor_id] if s
        ]

        if sensors:
            self._unsub_listeners.append(
                async_track_state_change_event(
                    self._hass, sensors, self._on_sensor_state_change
                )
            )

        self._unsub_listeners.append(
            async_track_time_interval(
                self._hass, self._periodic_update, timedelta(minutes=1)
            )
        )

        # Update weather forecasts every hour
        self._unsub_listeners.append(
            async_track_time_interval(
                self._hass, self._hourly_forecast_update, timedelta(hours=1)
            )
        )

    def _setup_time_triggers(self) -> None:
        """Configure les déclencheurs horaires selon le YAML"""
        self._cancel_time_triggers()

        now = dt_util.now()

        # Trigger pour recoverycalc_hour (arrêt chauffage le soir)
        recoverycalc_dt = now.replace(
            hour=self.data.recoverycalc_hour.hour,
            minute=self.data.recoverycalc_hour.minute,
            second=0,
            microsecond=0,
        )
        if recoverycalc_dt <= now:
            recoverycalc_dt += timedelta(days=1)

        self._unsub_time_triggers.append(
            async_track_point_in_time(
                self._hass, self._on_recoverycalc_hour, recoverycalc_dt
            )
        )

        # Trigger pour target_hour (fin de relance / réveil)
        target_dt = now.replace(
            hour=self.data.target_hour.hour,
            minute=self.data.target_hour.minute,
            second=0,
            microsecond=0,
        )
        if target_dt <= now:
            target_dt += timedelta(days=1)

        self._unsub_time_triggers.append(
            async_track_point_in_time(self._hass, self._on_target_hour, target_dt)
        )

        # Trigger pour recovery_start_hour (démarrage relance)
        if self.data.recovery_start_hour:
            recovery_start = self.data.recovery_start_hour
            if recovery_start.tzinfo is None:
                recovery_start = dt_util.as_local(recovery_start)
            if recovery_start > now:
                self._unsub_time_triggers.append(
                    async_track_point_in_time(
                        self._hass,
                        self._on_recovery_start_hour,
                        recovery_start,
                    )
                )

        # Trigger pour recovery_update_hour (mise à jour calcul)
        if self.data.recovery_update_hour:
            recovery_update = self.data.recovery_update_hour
            if recovery_update.tzinfo is None:
                recovery_update = dt_util.as_local(recovery_update)
            if recovery_update > now:
                self._unsub_time_triggers.append(
                    async_track_point_in_time(
                        self._hass,
                        self._on_recovery_update_hour,
                        recovery_update,
                    )
                )

    def _cancel_time_triggers(self) -> None:
        """Annule les déclencheurs horaires"""
        for unsub in self._unsub_time_triggers:
            unsub()
        self._unsub_time_triggers.clear()

    async def async_unload(self) -> None:
        """Déchargement du coordinateur"""
        await self._unregister_services()
        self._cancel_time_triggers()
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()

    # ─────────────────────────────────────────────────────────────────────────
    # Services
    # ─────────────────────────────────────────────────────────────────────────

    async def _register_services(self) -> None:
        """Enregistre les services Home Assistant"""
        if self._hass.services.has_service(DOMAIN, SERVICE_CALCULATE_RECOVERY_TIME):
            _LOGGER.debug("Services déjà enregistrés")
            return

        schema = vol.Schema({vol.Optional("entry_id"): str})

        handlers = {
            SERVICE_CALCULATE_RECOVERY_TIME: self._handle_calculate_recovery_time,
            SERVICE_CALCULATE_RECOVERY_UPDATE_TIME: self._handle_calculate_recovery_update_time,
            SERVICE_CALCULATE_RCTH_FAST: self._handle_calculate_rcth_fast,
            SERVICE_ON_HEATING_STOP: self._handle_on_heating_stop,
            SERVICE_ON_RECOVERY_START: self._handle_on_recovery_start,
            SERVICE_ON_RECOVERY_END: self._handle_on_recovery_end,
        }

        for service_name, handler in handlers.items():
            self._hass.services.async_register(
                DOMAIN,
                service_name,
                handler,
                schema=schema,
                supports_response=SupportsResponse.OPTIONAL,
            )
            _LOGGER.debug("Service enregistré: %s.%s", DOMAIN, service_name)

    async def _unregister_services(self) -> None:
        """Désenregistre les services si dernière instance"""
        if DOMAIN not in self._hass.data:
            return

        remaining = sum(
            1
            for data in self._hass.data[DOMAIN].values()
            if isinstance(data, dict) and DATA_COORDINATOR in data
        )

        if remaining <= 1:
            for service_name in SERVICES:
                if self._hass.services.has_service(DOMAIN, service_name):
                    self._hass.services.async_remove(DOMAIN, service_name)
            _LOGGER.debug("Services SmartHRT désenregistrés")

    def _get_coordinator(self, entry_id: str | None) -> "SmartHRTCoordinator | None":
        """Récupère le coordinator depuis un appel de service"""
        if DOMAIN not in self._hass.data:
            return None

        if entry_id and entry_id in self._hass.data[DOMAIN]:
            return self._hass.data[DOMAIN][entry_id].get(DATA_COORDINATOR)

        for data in self._hass.data[DOMAIN].values():
            if isinstance(data, dict) and DATA_COORDINATOR in data:
                return data[DATA_COORDINATOR]
        return None

    async def _handle_calculate_recovery_time(
        self, call: ServiceCall
    ) -> dict[str, Any]:
        coord = self._get_coordinator(call.data.get("entry_id"))
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

    async def _handle_calculate_recovery_update_time(
        self, call: ServiceCall
    ) -> dict[str, Any]:
        coord = self._get_coordinator(call.data.get("entry_id"))
        if not coord:
            return {"success": False, "error": "Coordinator not found"}
        result = coord.calculate_recovery_update_time()
        return {
            "recovery_update_hour": result.isoformat() if result else None,
            "success": True,
        }

    async def _handle_calculate_rcth_fast(self, call: ServiceCall) -> dict[str, Any]:
        coord = self._get_coordinator(call.data.get("entry_id"))
        if not coord:
            return {"success": False, "error": "Coordinator not found"}
        coord.calculate_rcth_fast()
        return {"rcth_fast": coord.data.rcth_fast, "success": True}

    async def _handle_on_heating_stop(self, call: ServiceCall) -> dict[str, Any]:
        coord = self._get_coordinator(call.data.get("entry_id"))
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

    async def _handle_on_recovery_start(self, call: ServiceCall) -> dict[str, Any]:
        coord = self._get_coordinator(call.data.get("entry_id"))
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

    async def _handle_on_recovery_end(self, call: ServiceCall) -> dict[str, Any]:
        coord = self._get_coordinator(call.data.get("entry_id"))
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

    # ─────────────────────────────────────────────────────────────────────────
    # État initial et callbacks
    # ─────────────────────────────────────────────────────────────────────────

    async def _update_initial_states(self) -> None:
        """Récupération des états initiaux"""
        if self._interior_temp_sensor_id:
            state = self._hass.states.get(self._interior_temp_sensor_id)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    self.data.interior_temp = float(state.state)
                except ValueError:
                    pass

        if self._phone_alarm_sensor_id:
            state = self._hass.states.get(self._phone_alarm_sensor_id)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                self.data.phone_alarm = state.state
                self._update_target_from_alarm()

        self._update_weather_data()

    @callback
    def _on_sensor_state_change(self, event) -> None:
        """Callback lors d'un changement d'état"""
        new_state = event.data.get("new_state")
        if not new_state or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        entity_id = new_state.entity_id

        if entity_id == self._interior_temp_sensor_id:
            try:
                self.data.interior_temp = float(new_state.state)
                self._check_temperature_thresholds()
            except ValueError:
                pass
        elif entity_id == self._phone_alarm_sensor_id:
            self.data.phone_alarm = new_state.state
            self._update_target_from_alarm()

        self._notify_listeners()

    @callback
    def _periodic_update(self, _now) -> None:
        """Mise à jour périodique (chaque minute)"""
        self._update_weather_data()
        self._update_wind_speed_average()

        if self.data.smartheating_mode and self.data.recovery_calc_mode:
            self.calculate_rcth_fast()
            self.calculate_recovery_time()

        self._notify_listeners()

    @callback
    def _hourly_forecast_update(self, _now) -> None:
        """Mise à jour des prévisions météo (chaque heure)"""
        self._hass.async_create_task(self._update_weather_forecasts())

    # ─────────────────────────────────────────────────────────────────────────
    # Déclencheurs horaires (équivalent des automations YAML)
    # ─────────────────────────────────────────────────────────────────────────

    @callback
    def _on_recoverycalc_hour(self, _now) -> None:
        """Appelé à l'heure de coupure du chauffage (recoverycalc_hour)
        Équivalent de l'automation 'heatingstopTIME' du YAML
        """
        _LOGGER.info("SmartHRT: Heure de coupure chauffage atteinte")

        if not self.data.smartheating_mode:
            self._reschedule_recoverycalc_hour()
            return

        # Initialisation des constantes si première exécution
        if self.data.rcth_lw <= 0:
            self.data.rcth_lw = 50.0
            self.data.rcth_hw = 50.0
            self.data.rpth_lw = 50.0
            self.data.rpth_hw = 50.0
            _LOGGER.info("SmartHRT: Initialisation des constantes à 50")

        # Enregistre les valeurs courantes
        self.data.time_recovery_calc = dt_util.now()
        self.data.temp_recovery_calc = self.data.interior_temp or 17.0
        self.data.text_recovery_calc = self.data.exterior_temp or 0.0

        # Active la détection du lag de température
        self.data.temp_lag_detection_active = True

        self._reschedule_recoverycalc_hour()
        self._notify_listeners()

    @callback
    def _on_recovery_start_hour(self, _now) -> None:
        """Appelé à l'heure calculée de démarrage de la relance (recoverystart_hour)
        Équivalent de l'automation 'boostTIME' du YAML
        """
        _LOGGER.info("SmartHRT: Heure de démarrage relance atteinte")

        if not self.data.smartheating_mode:
            return

        self.on_recovery_start()

    @callback
    def _on_target_hour(self, _now) -> None:
        """Appelé à l'heure cible (target_hour / réveil)
        Équivalent de l'automation 'recoveryendTIME' du YAML
        """
        _LOGGER.info("SmartHRT: Heure cible atteinte")

        if self.data.smartheating_mode and self.data.rp_calc_mode:
            self.on_recovery_end()

        self._reschedule_target_hour()

    @callback
    def _on_recovery_update_hour(self, _now) -> None:
        """Appelé pour mettre à jour le calcul de l'heure de relance
        Équivalent de l'automation 'Nth_RECOVERY_calc' du YAML
        """
        if not self.data.smartheating_mode or not self.data.recovery_calc_mode:
            return

        _LOGGER.debug("SmartHRT: Mise à jour du calcul de relance")
        self.calculate_rcth_fast()
        self.calculate_recovery_time()
        update_time = self.calculate_recovery_update_time()

        if update_time:
            self.data.recovery_update_hour = update_time
            self._schedule_recovery_update(update_time)

    def _reschedule_recoverycalc_hour(self) -> None:
        """Reprogramme le déclencheur recoverycalc_hour pour le lendemain"""
        now = dt_util.now()
        next_trigger = now.replace(
            hour=self.data.recoverycalc_hour.hour,
            minute=self.data.recoverycalc_hour.minute,
            second=0,
            microsecond=0,
        ) + timedelta(days=1)

        self._unsub_time_triggers.append(
            async_track_point_in_time(
                self._hass, self._on_recoverycalc_hour, next_trigger
            )
        )

    def _reschedule_target_hour(self) -> None:
        """Reprogramme le déclencheur target_hour pour le lendemain"""
        now = dt_util.now()
        next_trigger = now.replace(
            hour=self.data.target_hour.hour,
            minute=self.data.target_hour.minute,
            second=0,
            microsecond=0,
        ) + timedelta(days=1)

        self._unsub_time_triggers.append(
            async_track_point_in_time(self._hass, self._on_target_hour, next_trigger)
        )

    def _schedule_recovery_start(self, trigger_time: datetime) -> None:
        """Programme le déclencheur de démarrage de relance"""
        self._unsub_time_triggers.append(
            async_track_point_in_time(
                self._hass, self._on_recovery_start_hour, trigger_time
            )
        )

    def _schedule_recovery_update(self, trigger_time: datetime) -> None:
        """Programme le déclencheur de mise à jour du calcul"""
        self._unsub_time_triggers.append(
            async_track_point_in_time(
                self._hass, self._on_recovery_update_hour, trigger_time
            )
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Données météo
    # ─────────────────────────────────────────────────────────────────────────

    def _update_weather_data(self) -> None:
        """Mise à jour des données météo actuelles"""
        weather_entities = [
            s
            for s in self._hass.states.async_all("weather")
            if s.attributes.get("temperature") is not None
        ]

        if not weather_entities:
            return

        weather = weather_entities[0]

        if (temp := weather.attributes.get("temperature")) is not None:
            self.data.exterior_temp = float(temp)

        if (wind := weather.attributes.get("wind_speed")) is not None:
            self.data.wind_speed = float(wind) / 3.6  # km/h -> m/s
            # Ajouter à l'historique pour la moyenne
            self.data.wind_speed_history.append(self.data.wind_speed)

        self._calculate_windchill()

    def _update_wind_speed_average(self) -> None:
        """Calcule la moyenne de vitesse du vent sur 4h"""
        if self.data.wind_speed_history:
            self.data.wind_speed_avg = sum(self.data.wind_speed_history) / len(
                self.data.wind_speed_history
            )

    async def _update_weather_forecasts(self) -> None:
        """Mise à jour des prévisions météo (température et vent)
        Équivalent des sensors wind_speed_forecast_avg et temperature_forecast_avg du YAML
        """
        weather_entities = [
            s
            for s in self._hass.states.async_all("weather")
            if s.attributes.get("temperature") is not None
        ]

        if not weather_entities:
            return

        entity_id = weather_entities[0].entity_id

        try:
            # Appeler le service weather.get_forecasts
            forecast_response = await self._hass.services.async_call(
                "weather",
                "get_forecasts",
                {"type": "hourly"},
                target={"entity_id": entity_id},
                blocking=True,
                return_response=True,
            )

            if forecast_response and entity_id in forecast_response:
                entity_forecast = forecast_response[entity_id]
                if isinstance(entity_forecast, dict):
                    forecast_list = entity_forecast.get("forecast", [])
                    if isinstance(forecast_list, list):
                        forecasts = forecast_list[:FORECAST_HOURS]

                        if forecasts:
                            # Moyenne température
                            temps: list[float] = []
                            winds: list[float] = []

                            for f in forecasts:
                                if isinstance(f, dict):
                                    temp_val = f.get("temperature")
                                    if isinstance(temp_val, (int, float)):
                                        temps.append(float(temp_val))

                                    wind_val = f.get("wind_speed")
                                    if isinstance(wind_val, (int, float)):
                                        winds.append(float(wind_val))

                            if temps:
                                self.data.temperature_forecast_avg = sum(temps) / len(
                                    temps
                                )

                            if winds:
                                self.data.wind_speed_forecast_avg = sum(winds) / len(
                                    winds
                                )

                            _LOGGER.debug(
                                "Prévisions mises à jour: temp=%.1f°C, vent=%.1fkm/h",
                                self.data.temperature_forecast_avg,
                                self.data.wind_speed_forecast_avg,
                            )
        except Exception as ex:
            _LOGGER.warning(
                "Erreur lors de la récupération des prévisions météo: %s", ex
            )

    def _calculate_windchill(self) -> None:
        """Calcul de la température ressentie (windchill)
        Formule identique au YAML
        """
        if self.data.exterior_temp is None:
            return

        temp = self.data.exterior_temp
        wind_kmh = self.data.wind_speed * 3.6

        # Formule de windchill (JAG/TI) - active si temp < 10°C et vent > 4.8 km/h
        if temp < 10 and wind_kmh > 4.8:
            self.data.windchill = round(
                13.12
                + 0.6215 * temp
                - 11.37 * wind_kmh**0.16
                + 0.3965 * temp * wind_kmh**0.16,
                1,
            )
        else:
            self.data.windchill = temp

    def _update_target_from_alarm(self) -> None:
        """Met à jour l'heure cible depuis l'alarme"""
        if not self.data.phone_alarm:
            return
        try:
            alarm_dt = datetime.fromisoformat(self.data.phone_alarm)
            tomorrow = (dt_util.now() + timedelta(days=1)).date()
            if alarm_dt.date() in (dt_util.now().date(), tomorrow):
                self.data.target_hour = alarm_dt.time()
                self.calculate_recovery_time()
                self._notify_listeners()
        except (ValueError, TypeError):
            pass

    # ─────────────────────────────────────────────────────────────────────────
    # Interpolation thermique
    # ─────────────────────────────────────────────────────────────────────────

    def _interpolate(self, low: float, high: float, wind_kmh: float) -> float:
        """Interpole une valeur en fonction du vent"""
        wind_clamped = max(WIND_LOW, min(WIND_HIGH, wind_kmh))
        ratio = (WIND_HIGH - wind_clamped) / (WIND_HIGH - WIND_LOW)
        return max(0.1, high + (low - high) * ratio)

    def _get_interpolated_rcth(self, wind_kmh: float) -> float:
        return self._interpolate(self.data.rcth_lw, self.data.rcth_hw, wind_kmh)

    def _get_interpolated_rpth(self, wind_kmh: float) -> float:
        return self._interpolate(self.data.rpth_lw, self.data.rpth_hw, wind_kmh)

    # ─────────────────────────────────────────────────────────────────────────
    # Calculs thermiques
    # ─────────────────────────────────────────────────────────────────────────

    def calculate_recovery_time(self) -> None:
        """Calcule l'heure de démarrage de la relance
        Équivalent du script calculate_recovery_time du YAML
        Utilise les prévisions météo pour le calcul
        """
        if self.data.interior_temp is None:
            return

        # Utiliser les prévisions météo comme dans le YAML
        text = (
            self.data.temperature_forecast_avg
            if self.data.temperature_forecast_avg
            else (self.data.exterior_temp or 0.0)
        )
        tint = self.data.interior_temp
        tsp = self.data.tsp

        # Utiliser les prévisions de vent
        wind_kmh = (
            self.data.wind_speed_forecast_avg
            if self.data.wind_speed_forecast_avg
            else (self.data.wind_speed * 3.6)
        )

        rcth = self._get_interpolated_rcth(wind_kmh)
        rpth = self._get_interpolated_rpth(wind_kmh)

        now = dt_util.now()
        target_dt = now.replace(
            hour=self.data.target_hour.hour,
            minute=self.data.target_hour.minute,
            second=0,
            microsecond=0,
        )
        if target_dt < now:
            target_dt += timedelta(days=1)

        time_remaining = (target_dt - now).total_seconds() / 3600
        max_duration = max(time_remaining - 1 / 6, 0)

        try:
            ratio = (rpth + text - tint) / (rpth + text - tsp)
            duree_relance = min(max(rcth * math.log(max(ratio, 0.1)), 0), max_duration)
        except (ValueError, ZeroDivisionError):
            duree_relance = max_duration

        # Prédiction itérative (20 itérations comme dans le YAML)
        for _ in range(20):
            try:
                tint_start = text + (tint - text) / math.exp(
                    (time_remaining - duree_relance) / rcth
                )
                ratio = (rpth + text - tint_start) / (rpth + text - tsp)
                if ratio > 0.1:
                    duree_relance = min(
                        (duree_relance + 2 * max(rcth * math.log(ratio), 0)) / 3,
                        max_duration,
                    )
            except (ValueError, ZeroDivisionError):
                break

        prev_recovery_start = self.data.recovery_start_hour
        self.data.recovery_start_hour = target_dt - timedelta(
            seconds=int(duree_relance * 3600)
        )

        # Si l'heure de relance a changé, reprogrammer le trigger
        if (
            prev_recovery_start != self.data.recovery_start_hour
            and self.data.recovery_start_hour > now
        ):
            self._schedule_recovery_start(self.data.recovery_start_hour)

        # Calculer et programmer la prochaine mise à jour
        update_time = self.calculate_recovery_update_time()
        if update_time:
            self.data.recovery_update_hour = update_time
            self._schedule_recovery_update(update_time)

        _LOGGER.debug(
            "Recovery time: %s (%.2fh avant target)",
            self.data.recovery_start_hour,
            duree_relance,
        )

    def calculate_recovery_update_time(self) -> datetime | None:
        """Calcule l'heure de mise à jour de la relance
        Équivalent du script calculate_recoveryupdate_time du YAML
        """
        if self.data.recovery_start_hour is None:
            return None

        now = dt_util.now()
        recovery_time = self.data.recovery_start_hour
        if recovery_time < now:
            recovery_time += timedelta(days=1)

        time_remaining = (recovery_time - now).total_seconds()

        # Recalcule pas plus tard que dans 1200s (20min)
        # À moins de 30min avant la relance on arrête
        if time_remaining < 1800:
            seconds = 3600  # Impose un calcul après la relance
        else:
            seconds = min(max(time_remaining / 3, 0), 1200)

        return now + timedelta(seconds=seconds)

    def calculate_rcth_fast(self) -> None:
        """Calcule l'évolution dynamique de RCth"""
        if (
            self.data.interior_temp is None
            or self.data.exterior_temp is None
            or self.data.time_recovery_calc is None
        ):
            return

        tint: float = self.data.interior_temp
        text: float = self.data.exterior_temp
        tint_off: float = self.data.temp_recovery_calc
        text_off: float = self.data.text_recovery_calc

        dt_hours = (dt_util.now() - self.data.time_recovery_calc).total_seconds() / 3600
        if dt_hours < 0:
            dt_hours += 24

        avg_text = (text_off + text) / 2

        if tint < tint_off and tint > avg_text:
            try:
                self.data.rcth_fast = dt_hours / max(
                    0.0001, math.log((avg_text - tint_off) / (avg_text - tint))
                )
            except (ValueError, ZeroDivisionError):
                pass

    def calculate_rcth_at_recovery_start(self) -> None:
        """Calcule RCth au démarrage de la relance"""
        if (
            self.data.time_recovery_start is None
            or self.data.time_recovery_calc is None
        ):
            return

        dt = (
            self.data.time_recovery_start.timestamp()
            - self.data.time_recovery_calc.timestamp()
        ) / 3600
        avg_text = (self.data.text_recovery_start + self.data.text_recovery_calc) / 2

        try:
            self.data.rcth_calculated = min(
                19999,
                dt
                / math.log(
                    (avg_text - self.data.temp_recovery_calc)
                    / (avg_text - self.data.temp_recovery_start)
                ),
            )
        except (ValueError, ZeroDivisionError):
            pass

        if self.data.recovery_adaptive_mode:
            self._update_coefficients("rcth")

    def calculate_rpth_at_recovery_end(self) -> None:
        """Calcule RPth à la fin de la relance"""
        if self.data.time_recovery_start is None or self.data.time_recovery_end is None:
            return

        dt = (
            self.data.time_recovery_end.timestamp()
            - self.data.time_recovery_start.timestamp()
        ) / 3600
        avg_text = (self.data.text_recovery_start + self.data.text_recovery_end) / 2
        rcth_interpol = self._get_interpolated_rcth(self.data.wind_speed * 3.6)

        try:
            exp_term = math.exp(dt / rcth_interpol)
            numerator = (avg_text - self.data.temp_recovery_end) * exp_term - (
                avg_text - self.data.temp_recovery_start
            )
            self.data.rpth_calculated = min(19999, max(0.1, numerator / (1 - exp_term)))
        except (ValueError, ZeroDivisionError):
            pass

        if self.data.recovery_adaptive_mode:
            self._update_coefficients("rpth")

    def _update_coefficients(self, coef_type: str) -> None:
        """Met à jour les coefficients avec relaxation"""
        wind_kmh = self.data.wind_speed * 3.6
        x = (wind_kmh - WIND_LOW) / (WIND_HIGH - WIND_LOW) - 0.5
        relax = self.data.relaxation_factor

        if coef_type == "rcth":
            lw, hw, calc = (
                self.data.rcth_lw,
                self.data.rcth_hw,
                self.data.rcth_calculated,
            )
            interpol = max(0.1, lw + (hw - lw) * (x + 0.5))
            err = calc - interpol

            lw_new = max(
                0.1, lw + err * (1 - 5 / 3 * x - 2 * x * x + 8 / 3 * x * x * x)
            )
            hw_new = max(
                0.1, hw + err * (1 + 5 / 3 * x - 2 * x * x - 8 / 3 * x * x * x)
            )

            self.data.rcth_lw = min(19999, (lw + relax * lw_new) / (1 + relax))
            self.data.rcth_hw = min(
                self.data.rcth_lw, (hw + relax * hw_new) / (1 + relax)
            )
            self.data.rcth = max(0.1, (self.data.rcth + relax * calc) / (1 + relax))
        else:
            lw, hw, calc = (
                self.data.rpth_lw,
                self.data.rpth_hw,
                self.data.rpth_calculated,
            )
            interpol = max(0.1, lw + (hw - lw) * (x + 0.5))
            err = calc - interpol

            lw_new = max(
                0.1, lw + err * (1 - 5 / 3 * x - 2 * x * x + 8 / 3 * x * x * x)
            )
            hw_new = max(
                0.1, hw + err * (1 + 5 / 3 * x - 2 * x * x - 8 / 3 * x * x * x)
            )

            self.data.rpth_lw = min(19999, (lw + relax * lw_new) / (1 + relax))
            self.data.rpth_hw = min(
                self.data.rpth_lw, (hw + relax * hw_new) / (1 + relax)
            )
            self.data.rpth = min(
                19999, max(0.1, (self.data.rpth + relax * calc) / (1 + relax))
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Événements chauffage
    # ─────────────────────────────────────────────────────────────────────────

    def _check_temperature_thresholds(self) -> None:
        """Vérifie les seuils de température
        Gère la détection du lag de température et la fin de relance
        """
        if self.data.interior_temp is None:
            return

        # Détection du lag de température (équivalent de l'automation detect_temperature_lag)
        if self.data.temp_lag_detection_active:
            temp_threshold = self.data.temp_recovery_calc - TEMP_DECREASE_THRESHOLD

            if self.data.interior_temp <= temp_threshold:
                # Température a baissé de 0.2°C - le refroidissement réel commence
                self._on_temperature_decrease_detected()
            elif self.data.interior_temp > self.data.temp_recovery_calc:
                # Température a augmenté - mettre à jour le snapshot
                self.data.temp_recovery_calc = self.data.interior_temp

        # Vérifier si la consigne est atteinte pendant le mode rp_calc
        if self.data.rp_calc_mode and self.data.interior_temp >= self.data.tsp:
            self.on_recovery_end()

    def _on_temperature_decrease_detected(self) -> None:
        """Appelé quand la température commence réellement à baisser
        Équivalent du trigger 'temperatureDecrease' dans l'automation detect_temperature_lag
        """
        if self.data.time_recovery_calc is None:
            return

        now = dt_util.now()

        # Calculer la durée du lag
        self.data.stop_lag_duration = min(
            (now.timestamp() - self.data.time_recovery_calc.timestamp()), 10799
        )

        # Mettre à jour les snapshots avec les vraies valeurs de départ du refroidissement
        self.data.temp_recovery_calc = self.data.interior_temp or 17.0
        self.data.text_recovery_calc = self.data.exterior_temp or 0.0
        self.data.time_recovery_calc = now

        # Activer le mode calcul et calculer
        self.data.recovery_calc_mode = True
        self.data.temp_lag_detection_active = False

        self.calculate_recovery_time()

        _LOGGER.info(
            "SmartHRT: Baisse de température détectée après %.0fs de lag",
            self.data.stop_lag_duration,
        )
        self._notify_listeners()

    def on_heating_stop(self) -> None:
        """Appelé quand le chauffage s'arrête (service manuel)"""
        self.data.time_recovery_calc = dt_util.now()
        self.data.temp_recovery_calc = self.data.interior_temp or 17.0
        self.data.text_recovery_calc = self.data.exterior_temp or 0.0
        self.data.temp_lag_detection_active = True
        self.calculate_recovery_time()
        self._notify_listeners()

    def on_recovery_start(self) -> None:
        """Appelé au début de la relance
        Équivalent de l'automation 'boostTIME' du YAML
        """
        self.data.time_recovery_start = dt_util.now()
        self.data.temp_recovery_start = self.data.interior_temp or 17.0
        self.data.text_recovery_start = self.data.exterior_temp or 0.0

        self.calculate_rcth_at_recovery_start()

        self.data.rp_calc_mode = True
        self.data.recovery_calc_mode = False
        self.data.temp_lag_detection_active = False

        _LOGGER.info(
            "SmartHRT: Début de relance - Tint=%.1f°C, RCth calculé=%.2f",
            self.data.temp_recovery_start,
            self.data.rcth_calculated,
        )
        self._notify_listeners()

    def on_recovery_end(self) -> None:
        """Appelé à la fin de la relance (consigne atteinte ou target_hour)
        Équivalent de l'automation 'recoveryendTIME' du YAML
        """
        if not self.data.rp_calc_mode:
            return

        self.data.time_recovery_end = dt_util.now()
        self.data.temp_recovery_end = self.data.interior_temp or 17.0
        self.data.text_recovery_end = self.data.exterior_temp or 0.0

        self.calculate_rpth_at_recovery_end()

        self.data.rp_calc_mode = False

        _LOGGER.info(
            "SmartHRT: Fin de relance - Tint=%.1f°C, RPth calculé=%.2f",
            self.data.temp_recovery_end,
            self.data.rpth_calculated,
        )
        self._notify_listeners()

    def _on_recovery_end(self) -> None:
        """Ancienne méthode interne - redirige vers on_recovery_end"""
        self.on_recovery_end()

    # ─────────────────────────────────────────────────────────────────────────
    # Setters publics
    # ─────────────────────────────────────────────────────────────────────────

    def set_tsp(self, value: float) -> None:
        self.data.tsp = value
        self.calculate_recovery_time()
        self._notify_listeners()

    def set_target_hour(self, value: dt_time) -> None:
        self.data.target_hour = value
        self._setup_time_triggers()  # Reconfigure les triggers
        self.calculate_recovery_time()
        self._notify_listeners()

    def set_recoverycalc_hour(self, value: dt_time) -> None:
        """Définit l'heure de coupure chauffage"""
        self.data.recoverycalc_hour = value
        self._setup_time_triggers()  # Reconfigure les triggers
        self._notify_listeners()

    def set_smartheating_mode(self, value: bool) -> None:
        self.data.smartheating_mode = value
        self._notify_listeners()

    def set_recovery_adaptive_mode(self, value: bool) -> None:
        self.data.recovery_adaptive_mode = value
        self._notify_listeners()

    def set_adaptive_mode(self, value: bool) -> None:
        self.set_recovery_adaptive_mode(value)

    def set_rcth(self, value: float) -> None:
        self.data.rcth = value
        self.calculate_recovery_time()
        self._notify_listeners()

    def set_rpth(self, value: float) -> None:
        self.data.rpth = value
        self.calculate_recovery_time()
        self._notify_listeners()

    def set_relaxation_factor(self, value: float) -> None:
        self.data.relaxation_factor = value
        self._notify_listeners()

    def set_rcth_lw(self, value: float) -> None:
        self.data.rcth_lw = value
        self.calculate_recovery_time()
        self._notify_listeners()

    def set_rcth_hw(self, value: float) -> None:
        self.data.rcth_hw = value
        self.calculate_recovery_time()
        self._notify_listeners()

    def set_rpth_lw(self, value: float) -> None:
        self.data.rpth_lw = value
        self.calculate_recovery_time()
        self._notify_listeners()

    def set_rpth_hw(self, value: float) -> None:
        self.data.rpth_hw = value
        self.calculate_recovery_time()
        self._notify_listeners()

    # ─────────────────────────────────────────────────────────────────────────
    # Listeners
    # ─────────────────────────────────────────────────────────────────────────

    def register_listener(self, listener: Callable[[], None]) -> None:
        self._listeners.append(listener)

    def unregister_listener(self, listener: Callable[[], None]) -> None:
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _notify_listeners(self) -> None:
        for listener in self._listeners:
            listener()
