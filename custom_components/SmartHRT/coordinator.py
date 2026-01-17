"""Coordinator pour SmartHRT - Gère la logique de chauffage intelligent"""

import logging
import math
from datetime import datetime, timedelta, time as dt_time
from dataclasses import dataclass, field
from typing import Callable, Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, callback, ServiceCall, SupportsResponse
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import (
    async_track_time_interval,
    async_track_state_change_event,
)
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from .const import (
    DOMAIN,
    CONF_NAME,
    CONF_TARGET_HOUR,
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
    DATA_COORDINATOR,
)

_LOGGER = logging.getLogger(__name__)

# Liste des services disponibles
SERVICES = [
    SERVICE_CALCULATE_RECOVERY_TIME,
    SERVICE_CALCULATE_RECOVERY_UPDATE_TIME,
    SERVICE_CALCULATE_RCTH_FAST,
    SERVICE_ON_HEATING_STOP,
    SERVICE_ON_RECOVERY_START,
]


@dataclass
class SmartHRTData:
    """Données du système SmartHRT"""

    # Configuration
    name: str = "SmartHRT"
    tsp: float = DEFAULT_TSP
    target_hour: dt_time = field(default_factory=lambda: dt_time(6, 0, 0))

    # Modes
    smartheating_mode: bool = True
    recovery_adaptive_mode: bool = True
    recovery_calc_mode: bool = False
    rp_calc_mode: bool = False

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
    wind_speed: float = 0.0
    windchill: float | None = None

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

    # Alarme téléphone
    phone_alarm: str | None = None


class SmartHRTCoordinator:
    """Coordinateur central pour SmartHRT"""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._listeners: list[Callable[[], None]] = []
        self._unsub_listeners: list = []

        self.data = SmartHRTData(
            name=entry.data.get(CONF_NAME, "SmartHRT"),
            tsp=entry.data.get(CONF_TSP, DEFAULT_TSP),
            target_hour=self._parse_time(entry.data.get(CONF_TARGET_HOUR, "06:00:00")),
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
            "Configuration SmartHRT '%s' - TSP=%.1f°C, target_hour=%s",
            self.data.name, self.data.tsp, self.data.target_hour,
        )

        await self._update_initial_states()
        self._setup_listeners()
        await self._register_services()
        self.calculate_recovery_time()

    def _setup_listeners(self) -> None:
        """Configure les listeners pour les capteurs"""
        sensors = [s for s in [self._interior_temp_sensor_id, self._phone_alarm_sensor_id] if s]
        
        if sensors:
            self._unsub_listeners.append(
                async_track_state_change_event(self._hass, sensors, self._on_sensor_state_change)
            )

        self._unsub_listeners.append(
            async_track_time_interval(self._hass, self._periodic_update, timedelta(minutes=1))
        )

    async def async_unload(self) -> None:
        """Déchargement du coordinateur"""
        await self._unregister_services()
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
        }

        for service_name, handler in handlers.items():
            self._hass.services.async_register(
                DOMAIN, service_name, handler,
                schema=schema, supports_response=SupportsResponse.OPTIONAL,
            )
            _LOGGER.debug("Service enregistré: %s.%s", DOMAIN, service_name)

    async def _unregister_services(self) -> None:
        """Désenregistre les services si dernière instance"""
        if DOMAIN not in self._hass.data:
            return

        remaining = sum(
            1 for data in self._hass.data[DOMAIN].values()
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

    async def _handle_calculate_recovery_time(self, call: ServiceCall) -> dict[str, Any]:
        coord = self._get_coordinator(call.data.get("entry_id"))
        if not coord:
            return {"success": False, "error": "Coordinator not found"}
        coord.calculate_recovery_time()
        return {
            "recovery_start_hour": coord.data.recovery_start_hour.isoformat() if coord.data.recovery_start_hour else None,
            "success": True,
        }

    async def _handle_calculate_recovery_update_time(self, call: ServiceCall) -> dict[str, Any]:
        coord = self._get_coordinator(call.data.get("entry_id"))
        if not coord:
            return {"success": False, "error": "Coordinator not found"}
        result = coord.calculate_recovery_update_time()
        return {"recovery_update_hour": result.isoformat() if result else None, "success": True}

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
            "time_recovery_calc": coord.data.time_recovery_calc.isoformat() if coord.data.time_recovery_calc else None,
            "success": True,
        }

    async def _handle_on_recovery_start(self, call: ServiceCall) -> dict[str, Any]:
        coord = self._get_coordinator(call.data.get("entry_id"))
        if not coord:
            return {"success": False, "error": "Coordinator not found"}
        coord.on_recovery_start()
        return {
            "time_recovery_start": coord.data.time_recovery_start.isoformat() if coord.data.time_recovery_start else None,
            "rcth_calculated": coord.data.rcth_calculated,
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
        """Mise à jour périodique"""
        self._update_weather_data()

        if self.data.smartheating_mode and self.data.recovery_calc_mode:
            self.calculate_rcth_fast()
            self.calculate_recovery_time()

        self._notify_listeners()

    # ─────────────────────────────────────────────────────────────────────────
    # Données météo
    # ─────────────────────────────────────────────────────────────────────────

    def _update_weather_data(self) -> None:
        """Mise à jour des données météo"""
        weather_entities = [
            s for s in self._hass.states.async_all("weather")
            if s.attributes.get("temperature") is not None
        ]

        if not weather_entities:
            return

        weather = weather_entities[0]
        
        if (temp := weather.attributes.get("temperature")) is not None:
            self.data.exterior_temp = float(temp)

        if (wind := weather.attributes.get("wind_speed")) is not None:
            self.data.wind_speed = float(wind) / 3.6

        self._calculate_windchill()

    def _calculate_windchill(self) -> None:
        """Calcul de la température ressentie"""
        if self.data.exterior_temp is None:
            return

        temp, wind_kmh = self.data.exterior_temp, self.data.wind_speed * 3.6

        if temp < 10 and wind_kmh > 4.8:
            self.data.windchill = round(
                13.12 + 0.6215 * temp - 11.37 * wind_kmh**0.16 + 0.3965 * temp * wind_kmh**0.16, 1
            )
        else:
            self.data.windchill = temp

    def _update_target_from_alarm(self) -> None:
        """Met à jour l'heure cible depuis l'alarme"""
        if not self.data.phone_alarm:
            return
        try:
            alarm_dt = datetime.fromisoformat(self.data.phone_alarm)
            tomorrow = (datetime.now() + timedelta(days=1)).date()
            if alarm_dt.date() in (datetime.now().date(), tomorrow):
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
        """Calcule l'heure de démarrage de la relance"""
        if self.data.interior_temp is None or self.data.exterior_temp is None:
            return

        text, tint, tsp = self.data.exterior_temp, self.data.interior_temp, self.data.tsp
        wind_kmh = self.data.wind_speed * 3.6
        rcth, rpth = self._get_interpolated_rcth(wind_kmh), self._get_interpolated_rpth(wind_kmh)

        now = datetime.now()
        target_dt = now.replace(
            hour=self.data.target_hour.hour, minute=self.data.target_hour.minute,
            second=0, microsecond=0,
        )
        if target_dt < now:
            target_dt += timedelta(days=1)

        time_remaining = (target_dt - now).total_seconds() / 3600
        max_duration = max(time_remaining - 1/6, 0)

        try:
            ratio = (rpth + text - tint) / (rpth + text - tsp)
            duree_relance = min(max(rcth * math.log(ratio), 0), max_duration) if ratio > 0.1 else max_duration
        except (ValueError, ZeroDivisionError):
            duree_relance = max_duration

        # Prédiction itérative
        for _ in range(20):
            try:
                tint_start = text + (tint - text) / math.exp((time_remaining - duree_relance) / rcth)
                ratio = (rpth + text - tint_start) / (rpth + text - tsp)
                if ratio > 0.1:
                    duree_relance = min((duree_relance + 2 * max(rcth * math.log(ratio), 0)) / 3, max_duration)
            except (ValueError, ZeroDivisionError):
                break

        self.data.recovery_start_hour = target_dt - timedelta(seconds=int(duree_relance * 3600))
        _LOGGER.debug("Recovery time: %s (%.2fh)", self.data.recovery_start_hour, duree_relance)

    def calculate_recovery_update_time(self) -> datetime | None:
        """Calcule l'heure de mise à jour de la relance"""
        if self.data.recovery_start_hour is None:
            return None

        now = datetime.now()
        recovery_time = self.data.recovery_start_hour
        if recovery_time < now:
            recovery_time += timedelta(days=1)

        time_remaining = (recovery_time - now).total_seconds()
        seconds = 3600 if time_remaining < 1800 else min(max(time_remaining / 3, 0), 1200)

        return now + timedelta(seconds=seconds)

    def calculate_rcth_fast(self) -> None:
        """Calcule l'évolution dynamique de RCth"""
        if None in (self.data.interior_temp, self.data.exterior_temp, self.data.time_recovery_calc):
            return

        tint, text = self.data.interior_temp, self.data.exterior_temp
        tint_off, text_off = self.data.temp_recovery_calc, self.data.text_recovery_calc

        dt_hours = (datetime.now() - self.data.time_recovery_calc).total_seconds() / 3600
        if dt_hours < 0:
            dt_hours += 24

        avg_text = (text_off + text) / 2

        if tint < tint_off and tint > avg_text:
            try:
                self.data.rcth_fast = dt_hours / max(0.0001, math.log((avg_text - tint_off) / (avg_text - tint)))
            except (ValueError, ZeroDivisionError):
                pass

    def calculate_rcth_at_recovery_start(self) -> None:
        """Calcule RCth au démarrage de la relance"""
        if self.data.time_recovery_start is None or self.data.time_recovery_calc is None:
            return

        dt = (self.data.time_recovery_start.timestamp() - self.data.time_recovery_calc.timestamp()) / 3600
        avg_text = (self.data.text_recovery_start + self.data.text_recovery_calc) / 2

        try:
            self.data.rcth_calculated = min(
                19999,
                dt / math.log((avg_text - self.data.temp_recovery_calc) / (avg_text - self.data.temp_recovery_start))
            )
        except (ValueError, ZeroDivisionError):
            pass

        if self.data.recovery_adaptive_mode:
            self._update_coefficients("rcth")

    def calculate_rpth_at_recovery_end(self) -> None:
        """Calcule RPth à la fin de la relance"""
        if self.data.time_recovery_start is None or self.data.time_recovery_end is None:
            return

        dt = (self.data.time_recovery_end.timestamp() - self.data.time_recovery_start.timestamp()) / 3600
        avg_text = (self.data.text_recovery_start + self.data.text_recovery_end) / 2
        rcth_interpol = self._get_interpolated_rcth(self.data.wind_speed * 3.6)

        try:
            exp_term = math.exp(dt / rcth_interpol)
            numerator = (avg_text - self.data.temp_recovery_end) * exp_term - (avg_text - self.data.temp_recovery_start)
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
            lw, hw, calc = self.data.rcth_lw, self.data.rcth_hw, self.data.rcth_calculated
            interpol = max(0.1, lw + (hw - lw) * (x + 0.5))
            err = calc - interpol

            lw_new = max(0.1, lw + err * (1 - 5/3*x - 2*x*x + 8/3*x*x*x))
            hw_new = max(0.1, hw + err * (1 + 5/3*x - 2*x*x - 8/3*x*x*x))

            self.data.rcth_lw = min(19999, (lw + relax * lw_new) / (1 + relax))
            self.data.rcth_hw = min(self.data.rcth_lw, (hw + relax * hw_new) / (1 + relax))
            self.data.rcth = max(0.1, (self.data.rcth + relax * calc) / (1 + relax))
        else:
            lw, hw, calc = self.data.rpth_lw, self.data.rpth_hw, self.data.rpth_calculated
            interpol = max(0.1, lw + (hw - lw) * (x + 0.5))
            err = calc - interpol

            lw_new = max(0.1, lw + err * (1 - 5/3*x - 2*x*x + 8/3*x*x*x))
            hw_new = max(0.1, hw + err * (1 + 5/3*x - 2*x*x - 8/3*x*x*x))

            self.data.rpth_lw = min(19999, (lw + relax * lw_new) / (1 + relax))
            self.data.rpth_hw = min(self.data.rpth_lw, (hw + relax * hw_new) / (1 + relax))
            self.data.rpth = min(19999, max(0.1, (self.data.rpth + relax * calc) / (1 + relax)))

    # ─────────────────────────────────────────────────────────────────────────
    # Événements chauffage
    # ─────────────────────────────────────────────────────────────────────────

    def _check_temperature_thresholds(self) -> None:
        """Vérifie les seuils de température"""
        if self.data.interior_temp and self.data.rp_calc_mode and self.data.interior_temp >= self.data.tsp:
            self._on_recovery_end()

    def on_heating_stop(self) -> None:
        """Appelé quand le chauffage s'arrête"""
        self.data.time_recovery_calc = datetime.now()
        self.data.temp_recovery_calc = self.data.interior_temp or 17.0
        self.data.text_recovery_calc = self.data.exterior_temp or 0.0
        self.data.recovery_calc_mode = True
        self.calculate_recovery_time()
        self._notify_listeners()

    def on_recovery_start(self) -> None:
        """Appelé au début de la relance"""
        self.data.time_recovery_start = datetime.now()
        self.data.temp_recovery_start = self.data.interior_temp or 17.0
        self.data.text_recovery_start = self.data.exterior_temp or 0.0
        self.calculate_rcth_at_recovery_start()
        self.data.rp_calc_mode = True
        self.data.recovery_calc_mode = False
        self._notify_listeners()

    def _on_recovery_end(self) -> None:
        """Appelé à la fin de la relance"""
        self.data.time_recovery_end = datetime.now()
        self.data.temp_recovery_end = self.data.interior_temp or 17.0
        self.data.text_recovery_end = self.data.exterior_temp or 0.0
        self.calculate_rpth_at_recovery_end()
        self.data.rp_calc_mode = False
        self._notify_listeners()

    # ─────────────────────────────────────────────────────────────────────────
    # Setters publics
    # ─────────────────────────────────────────────────────────────────────────

    def set_tsp(self, value: float) -> None:
        self.data.tsp = value
        self.calculate_recovery_time()
        self._notify_listeners()

    def set_target_hour(self, value: dt_time) -> None:
        self.data.target_hour = value
        self.calculate_recovery_time()
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
