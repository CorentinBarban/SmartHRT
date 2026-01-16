""" Coordinator pour SmartHRT - Gère la logique de chauffage intelligent """
import logging
import math
from datetime import datetime, timedelta, time as dt_time
from dataclasses import dataclass, field
from typing import Callable

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import (
    async_track_time_interval,
    async_track_state_change_event,
)
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN

from .const import (
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
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class SmartHRTData:
    """Données du système SmartHRT"""
    # Configuration
    name: str = "SmartHRT"
    tsp: float = DEFAULT_TSP  # Set point (consigne)
    target_hour: dt_time = field(default_factory=lambda: dt_time(6, 0, 0))

    # Modes
    smartheating_mode: bool = True
    recovery_adaptive_mode: bool = True
    recovery_calc_mode: bool = False
    rp_calc_mode: bool = False

    # Coefficients thermiques
    rcth: float = DEFAULT_RCTH  # Constante de temps thermique (heures)
    rpth: float = DEFAULT_RPTH  # Puissance thermique équivalente (°C)
    rcth_lw: float = DEFAULT_RCTH  # RCth low wind
    rcth_hw: float = DEFAULT_RCTH  # RCth high wind
    rpth_lw: float = DEFAULT_RPTH  # RPth low wind
    rpth_hw: float = DEFAULT_RPTH  # RPth high wind
    rcth_fast: float = 0.0  # RCth dynamique
    rcth_calculated: float = 0.0
    rpth_calculated: float = 0.0
    relaxation_factor: float = DEFAULT_RELAXATION_FACTOR

    # Températures actuelles
    interior_temp: float | None = None
    exterior_temp: float | None = None
    wind_speed: float = 0.0  # m/s
    windchill: float | None = None

    # Températures de référence pour calculs
    # Tint au moment du calcul (chauffage OFF)
    temp_recovery_calc: float = 17.0
    temp_recovery_start: float = 17.0  # Tint au début de la relance
    temp_recovery_end: float = 17.0  # Tint à la fin de la relance
    text_recovery_calc: float = 0.0
    text_recovery_start: float = 0.0
    text_recovery_end: float = 0.0

    # Timestamps
    time_recovery_calc: datetime | None = None
    time_recovery_start: datetime | None = None
    time_recovery_end: datetime | None = None

    # Heure de relance calculée
    recovery_start_hour: datetime | None = None

    # Prochaine alarme téléphone
    phone_alarm: str | None = None


class SmartHRTCoordinator:
    """Coordinateur central pour SmartHRT"""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialisation du coordinateur"""
        self._hass = hass
        self._entry = entry
        self._listeners: list[Callable[[], None]] = []
        self._unsub_listeners: list = []

        # Initialisation des données
        self.data = SmartHRTData(
            name=entry.data.get(CONF_NAME, "SmartHRT"),
            tsp=entry.data.get(CONF_TSP, DEFAULT_TSP),
            target_hour=self._parse_time(
                entry.data.get(CONF_TARGET_HOUR, "06:00:00")),
        )

        # IDs des capteurs sources
        self._interior_temp_sensor_id = entry.data.get(
            CONF_SENSOR_INTERIOR_TEMP)
        self._phone_alarm_sensor_id = entry.data.get(CONF_PHONE_ALARM)

    def _parse_time(self, time_str: str) -> dt_time:
        """Parse une chaîne de temps en objet time"""
        try:
            parts = time_str.split(":")
            return dt_time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
        except (ValueError, IndexError):
            return dt_time(6, 0, 0)

    async def async_setup(self) -> None:
        """Configuration asynchrone du coordinateur"""
        # Récupération des états initiaux
        await self._update_initial_states()

        # Écoute des changements de capteurs
        sensors_to_listen = []
        if self._interior_temp_sensor_id:
            sensors_to_listen.append(self._interior_temp_sensor_id)
        if self._phone_alarm_sensor_id:
            sensors_to_listen.append(self._phone_alarm_sensor_id)

        if sensors_to_listen:
            self._unsub_listeners.append(
                async_track_state_change_event(
                    self._hass,
                    sensors_to_listen,
                    self._on_sensor_state_change,
                )
            )

        # Timer pour mise à jour périodique (toutes les minutes)
        self._unsub_listeners.append(
            async_track_time_interval(
                self._hass,
                self._periodic_update,
                timedelta(minutes=1),
            )
        )

        # Calcul initial
        self.calculate_recovery_time()

    async def async_unload(self) -> None:
        """Déchargement du coordinateur"""
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()

    async def _update_initial_states(self) -> None:
        """Récupération des états initiaux des capteurs"""
        # Température intérieure
        if self._interior_temp_sensor_id:
            state = self._hass.states.get(self._interior_temp_sensor_id)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    self.data.interior_temp = float(state.state)
                except ValueError:
                    pass

        # Alarme téléphone
        if self._phone_alarm_sensor_id:
            state = self._hass.states.get(self._phone_alarm_sensor_id)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                self.data.phone_alarm = state.state
                self._update_target_from_alarm()

        # Température extérieure (depuis weather)
        self._update_weather_data()

    @callback
    def _on_sensor_state_change(self, event) -> None:
        """Callback lors d'un changement d'état d'un capteur"""
        new_state = event.data.get("new_state")
        if new_state is None:
            return

        entity_id = new_state.entity_id

        if entity_id == self._interior_temp_sensor_id:
            if new_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    self.data.interior_temp = float(new_state.state)
                    self._check_temperature_thresholds()
                except ValueError:
                    pass

        elif entity_id == self._phone_alarm_sensor_id:
            if new_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
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

    def _update_weather_data(self) -> None:
        """Mise à jour des données météo depuis les entités weather"""
        # Recherche d'une entité weather
        weather_entities = [
            state for state in self._hass.states.async_all("weather")
            if state.attributes.get("temperature") is not None
        ]

        if weather_entities:
            weather = weather_entities[0]

            # Température extérieure
            temp = weather.attributes.get("temperature")
            if temp is not None:
                self.data.exterior_temp = float(temp)

            # Vitesse du vent (convertir km/h en m/s)
            wind = weather.attributes.get("wind_speed")
            if wind is not None:
                self.data.wind_speed = float(wind) / 3.6

            # Calcul du windchill
            self._calculate_windchill()

    def _calculate_windchill(self) -> None:
        """Calcul de la température ressentie (windchill)"""
        if self.data.exterior_temp is None:
            return

        temp = self.data.exterior_temp
        wind_kmh = self.data.wind_speed * 3.6

        if temp < 10 and wind_kmh > 4.8:
            self.data.windchill = round(
                13.12 + 0.6215 * temp - 11.37 * (wind_kmh ** 0.16)
                + 0.3965 * temp * (wind_kmh ** 0.16),
                1
            )
        else:
            self.data.windchill = temp

    def _update_target_from_alarm(self) -> None:
        """Met à jour l'heure cible depuis l'alarme du téléphone"""
        if not self.data.phone_alarm:
            return

        try:
            alarm_dt = datetime.fromisoformat(self.data.phone_alarm)
            tomorrow = (datetime.now() + timedelta(days=1)).date()

            # Vérifie que l'alarme est pour aujourd'hui ou demain
            if alarm_dt.date() in (datetime.now().date(), tomorrow):
                self.data.target_hour = alarm_dt.time()
                self.calculate_recovery_time()
                self._notify_listeners()
        except (ValueError, TypeError):
            pass

    def _get_interpolated_rcth(self, wind_kmh: float) -> float:
        """Interpole RCth en fonction du vent"""
        wind_clamped = max(WIND_LOW, min(WIND_HIGH, wind_kmh))
        ratio = (WIND_HIGH - wind_clamped) / (WIND_HIGH - WIND_LOW)
        return max(0.1, self.data.rcth_hw + (self.data.rcth_lw - self.data.rcth_hw) * ratio)

    def _get_interpolated_rpth(self, wind_kmh: float) -> float:
        """Interpole RPth en fonction du vent"""
        wind_clamped = max(WIND_LOW, min(WIND_HIGH, wind_kmh))
        ratio = (WIND_HIGH - wind_clamped) / (WIND_HIGH - WIND_LOW)
        return max(0.1, self.data.rpth_hw + (self.data.rpth_lw - self.data.rpth_hw) * ratio)

    def calculate_recovery_time(self) -> None:
        """Calcule l'heure de démarrage de la relance du chauffage"""
        if self.data.interior_temp is None or self.data.exterior_temp is None:
            return

        text = self.data.exterior_temp
        tint = self.data.interior_temp
        tsp = self.data.tsp
        wind_kmh = self.data.wind_speed * 3.6

        rcth = self._get_interpolated_rcth(wind_kmh)
        rpth = self._get_interpolated_rpth(wind_kmh)

        # Calcul de l'heure cible
        now = datetime.now()
        target_dt = now.replace(
            hour=self.data.target_hour.hour,
            minute=self.data.target_hour.minute,
            second=0,
            microsecond=0
        )

        # S'assurer que l'heure cible est dans le futur
        if target_dt < now:
            target_dt += timedelta(days=1)

        time_remaining = (target_dt - now).total_seconds() / 3600  # en heures
        max_duration = max(time_remaining - 1/6, 0)

        # Calcul initial de la durée de relance
        try:
            ratio = (rpth + text - tint) / (rpth + text - tsp)
            if ratio > 0.1:
                duree_relance = min(
                    max(rcth * math.log(ratio), 0), max_duration)
            else:
                duree_relance = max_duration
        except (ValueError, ZeroDivisionError):
            duree_relance = max_duration

        # Prédiction itérative
        for _ in range(20):
            try:
                tint_start = text + \
                    (tint - text) / math.exp((time_remaining - duree_relance) / rcth)
                ratio = (rpth + text - tint_start) / (rpth + text - tsp)
                if ratio > 0.1:
                    new_duration = rcth * math.log(ratio)
                    duree_relance = min(
                        (duree_relance + 2 * max(new_duration, 0)) / 3, max_duration)
            except (ValueError, ZeroDivisionError):
                break

        # Calcul de l'heure de relance
        seconds = int(duree_relance * 3600)
        self.data.recovery_start_hour = target_dt - timedelta(seconds=seconds)

        _LOGGER.debug(
            "Recovery time calculated: %s (duration: %.2f hours)",
            self.data.recovery_start_hour,
            duree_relance
        )

    def calculate_rcth_fast(self) -> None:
        """Calcule l'évolution dynamique de RCth"""
        if (self.data.interior_temp is None or
            self.data.exterior_temp is None or
                self.data.time_recovery_calc is None):
            return

        tint = self.data.interior_temp
        text = self.data.exterior_temp
        tint_off = self.data.temp_recovery_calc
        text_off = self.data.text_recovery_calc

        # Calcul du temps écoulé depuis le dernier calcul
        dt_hours = (datetime.now() -
                    self.data.time_recovery_calc).total_seconds() / 3600
        if dt_hours < 0:
            dt_hours += 24

        avg_text = (text_off + text) / 2

        if tint < tint_off and tint > avg_text:
            try:
                self.data.rcth_fast = dt_hours / \
                    max(0.0001, math.log((avg_text - tint_off) / (avg_text - tint)))
            except (ValueError, ZeroDivisionError):
                pass

    def calculate_rcth_at_recovery_start(self) -> None:
        """Calcule RCth au moment du démarrage de la relance"""
        if (self.data.time_recovery_start is None or
                self.data.time_recovery_calc is None):
            return

        t_start = self.data.time_recovery_start.timestamp()
        t_calc = self.data.time_recovery_calc.timestamp()
        dt = (t_start - t_calc) / 3600

        avg_text = (self.data.text_recovery_start +
                    self.data.text_recovery_calc) / 2

        try:
            self.data.rcth_calculated = min(
                19999,
                dt / math.log((avg_text - self.data.temp_recovery_calc) /
                              (avg_text - self.data.temp_recovery_start))
            )
        except (ValueError, ZeroDivisionError):
            pass

        # Auto-calibration
        if self.data.recovery_adaptive_mode:
            self._update_rcth_coefficients()

    def calculate_rpth_at_recovery_end(self) -> None:
        """Calcule RPth à la fin de la relance"""
        if (self.data.time_recovery_start is None or
                self.data.time_recovery_end is None):
            return

        t_start = self.data.time_recovery_start.timestamp()
        t_end = self.data.time_recovery_end.timestamp()
        dt = (t_end - t_start) / 3600

        avg_text = (self.data.text_recovery_start +
                    self.data.text_recovery_end) / 2
        wind_kmh = self.data.wind_speed * 3.6
        rcth_interpol = self._get_interpolated_rcth(wind_kmh)

        try:
            exp_term = math.exp(dt / rcth_interpol)
            numerator = (avg_text - self.data.temp_recovery_end) * \
                exp_term - (avg_text - self.data.temp_recovery_start)
            denominator = 1 - exp_term
            self.data.rpth_calculated = min(
                19999, max(0.1, numerator / denominator))
        except (ValueError, ZeroDivisionError):
            pass

        # Auto-calibration
        if self.data.recovery_adaptive_mode:
            self._update_rpth_coefficients()

    def _update_rcth_coefficients(self) -> None:
        """Met à jour les coefficients RCth avec relaxation"""
        wind_kmh = self.data.wind_speed * 3.6
        x = (wind_kmh - WIND_LOW) / (WIND_HIGH - WIND_LOW) - 0.5

        rcth_interpol = max(0.1, self.data.rcth_lw +
                            (self.data.rcth_hw - self.data.rcth_lw) * (x + 0.5))
        erc = self.data.rcth_calculated - rcth_interpol
        relax = self.data.relaxation_factor

        # Mise à jour RCth low wind
        rcth_lw_new = max(0.1, self.data.rcth_lw + erc *
                          (1 - 5/3*x - 2*x*x + 8/3*x*x*x))
        self.data.rcth_lw = min(
            19999, (self.data.rcth_lw + relax * rcth_lw_new) / (1 + relax))

        # Mise à jour RCth high wind
        rcth_hw_new = max(0.1, self.data.rcth_hw + erc *
                          (1 + 5/3*x - 2*x*x - 8/3*x*x*x))
        self.data.rcth_hw = min(
            self.data.rcth_lw, (self.data.rcth_hw + relax * rcth_hw_new) / (1 + relax))

        # Mise à jour RCth global
        self.data.rcth = max(
            0.1, (self.data.rcth + relax * self.data.rcth_calculated) / (1 + relax))

    def _update_rpth_coefficients(self) -> None:
        """Met à jour les coefficients RPth avec relaxation"""
        wind_kmh = self.data.wind_speed * 3.6
        x = (wind_kmh - WIND_LOW) / (WIND_HIGH - WIND_LOW) - 0.5

        rpth_interpol = max(0.1, self.data.rpth_lw +
                            (self.data.rpth_hw - self.data.rpth_lw) * (x + 0.5))
        erp = self.data.rpth_calculated - rpth_interpol
        relax = self.data.relaxation_factor

        # Mise à jour RPth low wind
        rpth_lw_new = max(0.1, self.data.rpth_lw + erp *
                          (1 - 5/3*x - 2*x*x + 8/3*x*x*x))
        self.data.rpth_lw = min(
            19999, (self.data.rpth_lw + relax * rpth_lw_new) / (1 + relax))

        # Mise à jour RPth high wind
        rpth_hw_new = max(0.1, self.data.rpth_hw + erp *
                          (1 + 5/3*x - 2*x*x - 8/3*x*x*x))
        self.data.rpth_hw = min(
            self.data.rpth_lw, (self.data.rpth_hw + relax * rpth_hw_new) / (1 + relax))

        # Mise à jour RPth global
        self.data.rpth = min(19999, max(
            0.1, (self.data.rpth + relax * self.data.rpth_calculated) / (1 + relax)))

    def _check_temperature_thresholds(self) -> None:
        """Vérifie les seuils de température pour les calculs"""
        if self.data.interior_temp is None:
            return

        # Fin de la relance si température atteinte
        if self.data.rp_calc_mode and self.data.interior_temp >= self.data.tsp:
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

    # Méthodes pour modifier les valeurs depuis les entités
    def set_tsp(self, value: float) -> None:
        """Définit la consigne de température"""
        self.data.tsp = value
        self.calculate_recovery_time()
        self._notify_listeners()

    def set_target_hour(self, value: dt_time) -> None:
        """Définit l'heure cible"""
        self.data.target_hour = value
        self.calculate_recovery_time()
        self._notify_listeners()

    def set_smartheating_mode(self, value: bool) -> None:
        """Active/désactive le mode chauffage intelligent"""
        self.data.smartheating_mode = value
        self._notify_listeners()

    def set_recovery_adaptive_mode(self, value: bool) -> None:
        """Active/désactive l'auto-calibration"""
        self.data.recovery_adaptive_mode = value
        self._notify_listeners()

    def set_adaptive_mode(self, value: bool) -> None:
        """Active/désactive le mode adaptatif (alias pour recovery_adaptive_mode)"""
        self.data.recovery_adaptive_mode = value
        self._notify_listeners()

    def set_rcth(self, value: float) -> None:
        """Définit RCth"""
        self.data.rcth = value
        self.calculate_recovery_time()
        self._notify_listeners()

    def set_rpth(self, value: float) -> None:
        """Définit RPth"""
        self.data.rpth = value
        self.calculate_recovery_time()
        self._notify_listeners()

    def set_relaxation_factor(self, value: float) -> None:
        """Définit le facteur de relaxation"""
        self.data.relaxation_factor = value
        self._notify_listeners()

    def register_listener(self, listener: Callable[[], None]) -> None:
        """Enregistre un listener pour les mises à jour"""
        self._listeners.append(listener)

    def unregister_listener(self, listener: Callable[[], None]) -> None:
        """Désenregistre un listener"""
        if listener in self._listeners:
            self._listeners.remove(listener)

    def _notify_listeners(self) -> None:
        """Notifie tous les listeners d'une mise à jour"""
        for listener in self._listeners:
            listener()
