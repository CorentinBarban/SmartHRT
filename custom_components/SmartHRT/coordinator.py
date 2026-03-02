"""Coordinator pour SmartHRT - Gère la logique de chauffage intelligent.

ADR implémentées dans ce module:
- ADR-002: Sélection explicite de l'entité météo (weather_entity_id)
- ADR-003: Machine à états explicite (SmartHRTState)
- ADR-004: Stratégie hybride de persistance (_save/_restore_learned_data)
- ADR-005: Stratégie de pilotage anticipation (via core.ThermalSolver)
- ADR-006: Apprentissage continu (via core.ThermalSolver)
- ADR-007: Compensation météo interpolation vent (via core.ThermalSolver)
- ADR-008: Validation arrêt par détection lag (TEMP_DECREASE_THRESHOLD)
- ADR-009: Persistance coefficients (PERSISTED_FIELDS, Store)
- ADR-013: Historique vent pour calcul (wind_speed_history, wind_speed_avg)
- ADR-014: Format des dates (dt_util.now(), dt_util.as_local())
- ADR-018: Identification instance dans les logs (_log_prefix)
- ADR-019: Restauration état après redémarrage (_restore_state_after_restart)
- ADR-020: Initialisation météo différée (EVENT_HOMEASSISTANT_STARTED)
- ADR-021: Triggers dynamiques (_schedule_recovery_start, async_track_point_in_time)
- ADR-022: Calcul itératif anticipation (via core.ThermalSolver, 20 itérations)
- ADR-023: Protection erreurs setters (try/except dans _schedule_recovery_start)
- ADR-024: Sérialisation types (PERSISTED_FIELDS avec datetime, time, list)
- ADR-025: Fréquence dynamique recalcul (via core.ThermalSolver)
- ADR-026: Extraction modèle thermique (core.ThermalSolver, core.ThermalState)
- ADR-027: Héritage DataUpdateCoordinator (notifications automatiques, CoordinatorEntity)
- ADR-028: Modernisation StrEnum pour machine à états (SmartHRTState, VALID_TRANSITIONS)
- ADR-029: Validation données persistées avec Pydantic (models.py)
- ADR-033: Découplage logique état (SmartHRTStateMachine)
- ADR-034: Gestion centralisée effets de bord (Action handlers)
- ADR-035: Immuabilité état (transitions atomiques)
- ADR-036: Factorisation setters (_update_and_recalculate)
- ADR-037: Suppression polling minute (listener météo push)
- ADR-039: Simplification restauration (auto-correction, _is_state_coherent)
- ADR-040: Délégation flags à la machine à états (propriétés calculées)
- ADR-041: Sérialisation globale via as_dict/from_dict (remplace PERSISTED_FIELDS)
- ADR-047: Unification du modèle de données (Single Source of Truth)
- ADR-053: Optimisation inter-saison (Snooze) et sécurisation apprentissage
- ADR-054: Abstraction unités (_normalize_to_celsius, conversion Fahrenheit→Celsius)
"""

import asyncio
import logging
from datetime import datetime, timedelta, time as dt_time
from typing import Any, Callable
from collections import deque

from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.event import (
    async_track_time_interval,
    async_track_state_change_event,
    async_track_point_in_time,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.const import (
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    EVENT_HOMEASSISTANT_STARTED,
    UnitOfTemperature,
    UnitOfSpeed,
)
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import TemperatureConverter, SpeedConverter
from homeassistant.exceptions import ServiceNotFound

from .const import (
    DOMAIN,
    CONF_NAME,
    CONF_TARGET_HOUR,
    CONF_RECOVERYCALC_HOUR,
    CONF_SENSOR_INTERIOR_TEMP,
    CONF_WEATHER_ENTITY,
    CONF_TSP,
    DEFAULT_TSP,
    DEFAULT_RCTH,
    DEFAULT_RPTH,
    DEFAULT_RELAXATION_FACTOR,
    WIND_HIGH,
    WIND_LOW,
    FORECAST_HOURS,
    TEMP_DECREASE_THRESHOLD,
    DEFAULT_RECOVERYCALC_HOUR,
    TimerKey,
    # ADR-053: Seuils pour Snooze et sécurisation apprentissage
    MIN_DURATION_THRESHOLD_HOURS,
    MIN_LEARNING_DURATION_HOURS,
)

# ADR-051: Import du gestionnaire centralisé de timers
from .timer_manager import TimerManager

# ADR-047: Import du modèle de données unifié (remplace serialization.py)
from .data_model import SmartHRTData

# ADR-026: Import du modèle thermique Pure Python
from .core import (
    ThermalSolver,
    ThermalState,
    ThermalCoefficients,
    ThermalConfig,
    Action,
    StateTransitionResult,
    SmartHRTState,
    SmartHRTStateMachine,
    VALID_TRANSITIONS,
    TRANSITION_ACTIONS,
    # ADR-040: get_state_flags n'est plus utilisé, flags sont des propriétés calculées
)

_LOGGER = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# ADR-047: SmartHRTData est maintenant importé de data_model.py
# Les anciennes dataclasses (SmartHRTConfig, LearnedCoefficients, etc.)
# sont supprimées car fusionnées dans le modèle Pydantic unifié.
# ─────────────────────────────────────────────────────────────────────────────


class SmartHRTCoordinator(DataUpdateCoordinator[SmartHRTData]):
    """Coordinateur central pour SmartHRT (ADR-027: hérite de DataUpdateCoordinator).

    Hérite de DataUpdateCoordinator pour bénéficier de:
    - Gestion automatique des listeners via CoordinatorEntity
    - Debouncing des mises à jour
    - Gestion d'erreurs standardisée
    - Logging intégré
    """

    STORAGE_VERSION = 1

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        # Initialiser DataUpdateCoordinator avec update_interval=None
        # car les mises à jour sont pilotées par les triggers et événements
        super().__init__(
            hass,
            _LOGGER,
            name=f"SmartHRT {entry.data.get(CONF_NAME, 'SmartHRT')}",
            update_interval=None,  # Pas de polling automatique, mises à jour manuelles
        )

        self._entry = entry
        self._unsub_listeners: list = []
        # ADR-051: Gestionnaire centralisé des timers
        self._timer_manager = TimerManager(hass)
        # ADR-004 & ADR-009: Stratégie hybride de persistance
        # Les coefficients appris (RCth, RPth) et l'état survivent aux redémarrages
        self._store: Store = Store(
            hass, self.STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )

        self.data = SmartHRTData(
            name=entry.data.get(CONF_NAME, "SmartHRT"),
            tsp=entry.data.get(CONF_TSP, DEFAULT_TSP),
            target_hour=self._parse_time(entry.data.get(CONF_TARGET_HOUR, "06:00:00")),
            recoverycalc_hour=self._parse_time(
                entry.data.get(CONF_RECOVERYCALC_HOUR, DEFAULT_RECOVERYCALC_HOUR)
            ),
        )

        # ADR-033/034/046: Machine à états avec actions déclaratives
        # ADR-049: Démarrage en INITIALIZING, transition vers l'état restauré dans _restore_learned_data
        log_prefix = f"[{self.data.name}#{entry.entry_id[:8]}]"
        self._state_machine = SmartHRTStateMachine(
            SmartHRTState.INITIALIZING,  # ADR-049: Toujours démarrer en INITIALIZING
            transition_actions=TRANSITION_ACTIONS,
            logger=_LOGGER,  # type: ignore[arg-type]
            log_prefix=log_prefix,
        )
        self._state_machine.on_enter(SmartHRTState.HEATING_ON, self._on_state_entered)
        self._state_machine.on_enter(
            SmartHRTState.DETECTING_LAG, self._on_state_entered
        )
        self._state_machine.on_enter(SmartHRTState.MONITORING, self._on_state_entered)
        self._state_machine.on_enter(SmartHRTState.RECOVERY, self._on_state_entered)
        self._state_machine.on_enter(
            SmartHRTState.HEATING_PROCESS, self._on_state_entered
        )

        self._interior_temp_sensor_id = entry.data.get(CONF_SENSOR_INTERIOR_TEMP)
        # ADR-002: Entité météo sélectionnée explicitement par l'utilisateur
        self._weather_entity_id = entry.data.get(CONF_WEATHER_ENTITY)

        # ADR-026: Initialisation du solveur thermique Pure Python
        thermal_config = ThermalConfig(
            wind_low_kmh=WIND_LOW,
            wind_high_kmh=WIND_HIGH,
            default_rcth=DEFAULT_RCTH,
            default_rpth=DEFAULT_RPTH,
            default_relaxation_factor=DEFAULT_RELAXATION_FACTOR,
        )
        self._thermal_solver = ThermalSolver(
            thermal_config, logger=_LOGGER, log_prefix=log_prefix
        )

    def _log_prefix(self) -> str:
        """Retourne un préfixe pour les logs incluant le nom et entry_id de l'instance.

        Permet de dissocier les entrées de log quand plusieurs instances SmartHRT
        sont configurées, en incluant le nom et l'identifiant unique.
        """
        return f"[{self.data.name}#{self._entry.entry_id[:8]}]"

    # ─────────────────────────────────────────────────────────────────────────
    # ADR-054: Conversion des unités de température
    # ─────────────────────────────────────────────────────────────────────────

    def _get_sensor_unit(self, entity_id: str) -> str:
        """Récupère l'unité de température d'un capteur.

        ADR-054: Détecte l'unité du capteur pour la conversion.

        Pour les weather entities: lit l'attribut temperature_unit de l'entité.
        Pour les sensor entities: utilise l'attribut unit_of_measurement.

        Args:
            entity_id: ID de l'entité capteur

        Returns:
            L'unité de température (CELSIUS ou FAHRENHEIT), défaut CELSIUS.
        """
        state = self.hass.states.get(entity_id)
        if state and state.attributes:
            # Weather entities: lire l'attribut temperature_unit
            if entity_id.startswith("weather."):
                unit = state.attributes.get("temperature_unit")
                if unit == UnitOfTemperature.FAHRENHEIT:
                    return UnitOfTemperature.FAHRENHEIT
                # Défaut pour weather: Celsius (Météo France, etc.)
                return UnitOfTemperature.CELSIUS
            # Sensor entities: unit_of_measurement reflète l'unité exposée
            unit = state.attributes.get("unit_of_measurement")
            if unit == UnitOfTemperature.FAHRENHEIT:
                return UnitOfTemperature.FAHRENHEIT
        return UnitOfTemperature.CELSIUS

    def _normalize_to_celsius(
        self, temp: float | None, source_unit: str = UnitOfTemperature.CELSIUS
    ) -> float | None:
        """Convertit une température vers Celsius si nécessaire.

        ADR-054: Normalisation pour le ThermalSolver qui travaille en °C.

        Args:
            temp: Température à convertir (ou None)
            source_unit: Unité source (CELSIUS ou FAHRENHEIT)

        Returns:
            Température en Celsius (ou None si temp est None)
        """
        if temp is None:
            return None
        if source_unit == UnitOfTemperature.FAHRENHEIT:
            return TemperatureConverter.convert(
                temp, UnitOfTemperature.FAHRENHEIT, UnitOfTemperature.CELSIUS
            )
        return temp

    # ─────────────────────────────────────────────────────────────────────────
    # ADR-055: Conversion des unités de vitesse du vent
    # ─────────────────────────────────────────────────────────────────────────

    def _get_wind_speed_unit(self, entity_id: str) -> UnitOfSpeed:
        """Récupère l'unité de vitesse du vent d'un capteur.

        ADR-055: Détecte l'unité du capteur pour la conversion vers m/s.

        Pour les weather entities: lit l'attribut wind_speed_unit de l'entité.
        Pour les sensor entities: lit l'attribut unit_of_measurement.

        Args:
            entity_id: ID de l'entité capteur

        Returns:
            L'unité de vitesse (m/s, km/h, mph, etc.), défaut km/h.
        """
        state = self.hass.states.get(entity_id)
        if state and state.attributes:
            # Weather entities: lire l'attribut wind_speed_unit
            if entity_id.startswith("weather."):
                unit = state.attributes.get("wind_speed_unit")
                if unit in (
                    UnitOfSpeed.MILES_PER_HOUR,
                    UnitOfSpeed.KILOMETERS_PER_HOUR,
                    UnitOfSpeed.KNOTS,
                    UnitOfSpeed.FEET_PER_SECOND,
                    UnitOfSpeed.METERS_PER_SECOND,
                ):
                    return UnitOfSpeed(unit)
                # Fallback: la plupart des weather integrations utilisent km/h
                return UnitOfSpeed.KILOMETERS_PER_HOUR
            # Sensor entities: unit_of_measurement reflète l'unité exposée
            unit = state.attributes.get("unit_of_measurement")
            if unit in (
                UnitOfSpeed.MILES_PER_HOUR,
                UnitOfSpeed.KILOMETERS_PER_HOUR,
                UnitOfSpeed.KNOTS,
                UnitOfSpeed.FEET_PER_SECOND,
                UnitOfSpeed.METERS_PER_SECOND,
            ):
                return UnitOfSpeed(unit)
        # Fallback: km/h (unité la plus courante pour le vent)
        return UnitOfSpeed.KILOMETERS_PER_HOUR

    def _normalize_to_ms(
        self,
        speed: float | None,
        source_unit: UnitOfSpeed = UnitOfSpeed.METERS_PER_SECOND,
    ) -> float | None:
        """Convertit une vitesse de vent vers m/s si nécessaire.

        ADR-055: Normalisation pour le ThermalSolver qui travaille en m/s.

        Args:
            speed: Vitesse à convertir (ou None)
            source_unit: Unité source (m/s, km/h, mph, etc.)

        Returns:
            Vitesse en m/s (ou None si speed est None)
        """
        if speed is None:
            return None
        if source_unit == UnitOfSpeed.METERS_PER_SECOND:
            return speed
        return SpeedConverter.convert(speed, source_unit, UnitOfSpeed.METERS_PER_SECOND)

    def _normalize_to_kmh(
        self,
        speed: float | None,
        source_unit: UnitOfSpeed = UnitOfSpeed.KILOMETERS_PER_HOUR,
    ) -> float | None:
        """Convertit une vitesse de vent vers km/h si nécessaire.

        ADR-055: Normalisation pour wind_speed_forecast_avg qui est stocké en km/h.

        Args:
            speed: Vitesse à convertir (ou None)
            source_unit: Unité source (m/s, km/h, mph, etc.)

        Returns:
            Vitesse en km/h (ou None si speed est None)
        """
        if speed is None:
            return None
        if source_unit == UnitOfSpeed.KILOMETERS_PER_HOUR:
            return speed
        return SpeedConverter.convert(
            speed, source_unit, UnitOfSpeed.KILOMETERS_PER_HOUR
        )

    def _on_state_entered(
        self, _old_state: SmartHRTState, new_state: SmartHRTState
    ) -> None:
        """Synchronise l'état exposé avec la machine à états."""
        self.data.current_state = new_state

    def transition_to(self, new_state: SmartHRTState) -> bool:
        """Effectue une transition d'état si elle est valide (ADR-028).

        Note: Les logs de transition sont émis par la state machine elle-même.
        """
        # La state machine gère le logging des transitions (succès et échecs)
        return self._state_machine.transition_to(new_state)

    def _apply_state_transition_with_actions(
        self,
        new_state: SmartHRTState,
        updates: dict[str, object] | None = None,
        omit_actions: set[Action] | None = None,
    ) -> list[Action] | None:
        current = self._state_machine.state
        valid_targets = VALID_TRANSITIONS.get(current, set())
        if not self._state_machine.can_transition(current, new_state):
            _LOGGER.warning(
                "%s Transition invalide %s → %s (autorisées: %s)",
                self._log_prefix(),
                current.value,
                new_state.value,
                (
                    ", ".join(s.value for s in valid_targets)
                    if valid_targets
                    else "aucune"
                ),
            )
            return None

        # ADR-040: Les flags sont maintenant des propriétés calculées depuis current_state
        # On ne merge plus get_state_flags(), juste les updates fournis
        self.data.update(current_state=new_state, **(updates or {}))
        self._state_machine._force_state_unsafe(new_state, run_callbacks=False)

        actions = self._state_machine.actions_for_transition(current, new_state)
        if omit_actions:
            actions = [action for action in actions if action not in omit_actions]
        return actions

    def transition_with_actions(
        self, new_state: SmartHRTState
    ) -> StateTransitionResult:
        """Effectue une transition et retourne les actions à exécuter (ADR-034).

        Note: Les logs de transition sont émis par la state machine elle-même.
        """
        # La state machine gère le logging des transitions (succès et échecs)
        return self._state_machine.transition_with_actions(new_state)

    def _execute_actions(self, actions: list[Action]) -> None:
        """Exécute les actions émises par la machine à états (ADR-034).

        Gère les handlers sync et async avec logging et gestion d'erreurs.
        """
        if not actions:
            return

        action_handlers = {
            Action.SNAPSHOT_RECOVERY_START: self._snapshot_recovery_start,
            Action.SNAPSHOT_RECOVERY_END: self._snapshot_recovery_end,
            Action.CALCULATE_RCTH: self._calculate_rcth_at_recovery_start,
            Action.CALCULATE_RPTH: self._calculate_rpth_at_recovery_end,
            Action.SAVE_DATA: self._save_learned_data,
            Action.SCHEDULE_RECOVERY_UPDATE: self._schedule_recovery_update_from_data,
            Action.CANCEL_RECOVERY_TIMER: self._cancel_recovery_start_timer,
        }

        _LOGGER.debug(
            "%s Exécution actions: %s",
            self._log_prefix(),
            [a.value for a in actions],
        )

        for action in actions:
            handler = action_handlers.get(action)
            if not handler:
                _LOGGER.warning(
                    "%s Action non gérée: %s", self._log_prefix(), action.value
                )
                continue
            try:
                result = handler()
                if asyncio.iscoroutine(result):
                    self.hass.async_create_task(result)
            except Exception as e:
                _LOGGER.error(
                    "%s Erreur lors de l'action %s: %s",
                    self._log_prefix(),
                    action.value,
                    e,
                )

    def _cancel_recovery_start_timer(self) -> None:
        """Annule le trigger de recovery_start si présent (ADR-051)."""
        self._timer_manager.cancel(TimerKey.RECOVERY_START)

    def _snapshot_recovery_start(self) -> None:
        """Snapshot des données au démarrage de relance."""
        self.data.time_recovery_start = dt_util.now()
        self.data.temp_recovery_start = self.data.interior_temp or 17.0
        self.data.text_recovery_start = self.data.exterior_temp or 0.0

    def _snapshot_recovery_end(self) -> None:
        """Snapshot des données à la fin de relance."""
        self.data.time_recovery_end = dt_util.now()
        self.data.temp_recovery_end = self.data.interior_temp or 17.0
        self.data.text_recovery_end = self.data.exterior_temp or 0.0

    def _calculate_rcth_at_recovery_start(self) -> None:
        """Calcule RCth au démarrage de relance."""
        self.calculate_rcth_at_recovery_start()

    def _calculate_rpth_at_recovery_end(self) -> None:
        """Calcule RPth à la fin de relance."""
        self.calculate_rpth_at_recovery_end()

    def _schedule_recovery_update_from_data(self) -> None:
        """Programme la mise à jour de relance si une heure est connue."""
        if self.data.recovery_update_hour:
            self._schedule_recovery_update(self.data.recovery_update_hour)

    def force_state(self, new_state: SmartHRTState) -> None:
        """Force un changement d'état sans validation (ADR-028, ADR-035).

        ADR-049: Cette méthode reste pour les cas de fallback et services admin.
        Pour la restauration après redémarrage, utiliser transition_to depuis INITIALIZING.

        Met à jour atomiquement l'état et les flags associés.
        À utiliser avec parcimonie (restauration, services admin).
        """
        old_state = self._state_machine.state
        if new_state == old_state:
            return

        # ADR-040: Les flags sont maintenant calculés depuis current_state
        # Seul current_state est mis à jour
        self.data.update(current_state=new_state)
        self._state_machine._force_state_unsafe(new_state, run_callbacks=False)

        _LOGGER.info(
            "%s État forcé %s → %s",
            self._log_prefix(),
            old_state.value,
            new_state.value,
        )

    async def _async_update_data(self) -> SmartHRTData:
        """Méthode requise par DataUpdateCoordinator.

        Retourne les données actuelles car les mises à jour sont pilotées
        par les événements et triggers, pas par le polling.
        """
        return self.data

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
        """Configuration asynchrone du coordinateur.

        PERF: Les opérations bloquantes (météo, calculs) sont différées
        via async_create_task pour ne pas bloquer le setup de l'entrée.
        """
        _LOGGER.debug(
            "%s Configuration - TSP=%.1f°C, target_hour=%s, recoverycalc_hour=%s",
            self._log_prefix(),
            self.data.tsp,
            self.data.target_hour,
            self.data.recoverycalc_hour,
        )

        # Restore learned coefficients from storage (rapide, lecture locale)
        await self._restore_learned_data()

        await self._update_initial_states()
        self._setup_listeners()
        self._setup_time_triggers()

        # Restaurer les triggers selon l'état (ne dépend pas de la météo)
        await self._restore_state_after_restart()

        # PERF: Différer l'initialisation météo pour ne pas bloquer le setup
        # Les opérations météo (service calls) peuvent prendre >1s
        if self._weather_entity_id:
            weather = self.hass.states.get(self._weather_entity_id)
            if weather is None:
                _LOGGER.debug(
                    "%s Entité météo %s pas encore disponible, initialisation différée",
                    self._log_prefix(),
                    self._weather_entity_id,
                )
                # Différer l'initialisation météo après le démarrage complet
                self.hass.bus.async_listen_once(
                    EVENT_HOMEASSISTANT_STARTED, self._on_homeassistant_started
                )
            else:
                # Entité météo disponible - lancer en tâche de fond (non-bloquant)
                self.hass.async_create_task(
                    self._complete_weather_setup(),
                    name=f"SmartHRT {self.data.name} weather setup",
                )
        else:
            # Pas d'entité météo configurée - setup minimal en tâche de fond
            self.hass.async_create_task(
                self._complete_weather_setup(),
                name=f"SmartHRT {self.data.name} weather setup",
            )

    async def _on_homeassistant_started(self, event: Event) -> None:
        """Callback appelé après le démarrage complet de Home Assistant.

        Permet d'initialiser les fonctionnalités météo une fois que toutes
        les intégrations sont chargées.
        """
        _LOGGER.info(
            "%s Home Assistant démarré, initialisation météo de %s",
            self._log_prefix(),
            self._weather_entity_id,
        )
        await self._complete_weather_setup()

    async def _complete_weather_setup(self) -> None:
        """Termine l'initialisation des fonctionnalités dépendantes de la météo."""
        await self._update_weather_forecasts()

        # ADR-048: Calcul synchrone (< 10ms, pas d'I/O bloquante)
        # Ne pas écraser recovery_start_hour si déjà valide pour aujourd'hui
        now = dt_util.now()
        should_recalculate = True
        if self.data.recovery_start_hour:
            if self.data.recovery_start_hour.date() == now.date():
                _LOGGER.debug(
                    "%s recovery_start_hour déjà défini pour aujourd'hui (%s), pas de recalcul",
                    self._log_prefix(),
                    self.data.recovery_start_hour.strftime("%H:%M"),
                )
                should_recalculate = False

        if should_recalculate:
            self.calculate_recovery_time()

        # Programmer le trigger de relance si nécessaire
        if self.data.recovery_start_hour and self.data.recovery_start_hour > now:
            self._schedule_recovery_start(self.data.recovery_start_hour)

        # Programmer la première mise à jour de recovery_update_hour
        # Le trigger est toujours programmé pour maintenir la chaîne de mises à jour active
        if self.data.smartheating_mode and self.data.recovery_start_hour:
            # ADR-048: Calcul synchrone (< 10ms)
            update_time = self.calculate_recovery_update_time()
            if update_time:
                self.data.recovery_update_hour = update_time
                self._schedule_recovery_update(update_time)

    async def _restore_learned_data(self) -> None:
        """Restore learned coefficients and state from persistent storage.

        ADR-004: Stratégie hybride de persistance
        ADR-009: Persistance des coefficients thermiques
        ADR-047: Sérialisation native Pydantic (remplace ADR-029, ADR-041)

        This ensures that learned thermal constants (RCth, RPth) and the
        current state machine state survive Home Assistant restarts.
        """
        stored_data = await self._store.async_load()
        if stored_data:
            _LOGGER.info(
                "%s Restoration des données apprises depuis le stockage",
                self._log_prefix(),
            )

            # ADR-047: Détecter et migrer l'ancien format si nécessaire
            # L'ancien format utilise __type__ pour les valeurs complexes
            if self._is_legacy_format(stored_data):
                _LOGGER.debug("%s Migration depuis l'ancien format", self._log_prefix())
                stored_data = SmartHRTData.migrate_legacy_format(stored_data)

            # ADR-047: Désérialisation native Pydantic
            self.data = SmartHRTData.from_dict(stored_data, defaults=self.data)

            _LOGGER.debug(
                "%s Données restaurées: state=%s, rcth=%.2f, rpth=%.2f, recovery_calc_mode=%s, temp_forecast=%.1f°C, wind_forecast=%.1f",
                self._log_prefix(),
                self.data.current_state,
                self.data.rcth,
                self.data.rpth,
                self.data.recovery_calc_mode,
                self.data.temperature_forecast_avg,
                self.data.wind_speed_forecast_avg,
            )
        else:
            _LOGGER.debug(
                "%s Aucune donnée apprise trouvée, utilisation des défauts",
                self._log_prefix(),
            )

        # ADR-049: NE PAS faire la transition ici !
        # La transition sera gérée par _restore_state_after_restart() APRÈS
        # vérification de cohérence de l'état persisté.
        # On reste en INITIALIZING jusqu'à ce que la cohérence soit vérifiée.
        _LOGGER.debug(
            "%s État persisté: %s (transition différée)",
            self._log_prefix(),
            self.data.current_state.value,
        )

    def _is_legacy_format(self, data: dict) -> bool:
        """Détecte si les données sont au format legacy (PERSISTED_FIELDS).

        Le nouveau format utilise des dict avec __type__ pour datetime, time, etc.
        L'ancien format stocke directement les strings ISO.
        """
        # Si current_state est une string simple (pas un dict), c'est l'ancien format
        current_state = data.get("current_state")
        if isinstance(current_state, str):
            return True
        # Si c'est un dict avec __type__, c'est le nouveau format
        if isinstance(current_state, dict) and "__type__" in current_state:
            return False
        # Par défaut, considérer comme nouveau format
        return False

    async def _save_learned_data(self) -> None:
        """Save learned coefficients and state to persistent storage.

        ADR-047: Sérialisation native Pydantic via as_dict().

        Called after each state transition and learning cycle to persist
        the updated coefficients and state.
        """
        data_to_store = self.data.as_dict()
        await self._store.async_save(data_to_store)
        _LOGGER.debug(
            "%s Données apprises et état sauvegardés en stockage", self._log_prefix()
        )

    def _setup_listeners(self) -> None:
        """Configure les listeners pour les capteurs.

        ADR-037: Architecture push (pilotée par événements) :
        - Listener sur le capteur de température intérieure
        - Listener sur l'entité météo (remplace le polling minute)
        - Mise à jour horaire des prévisions météo
        """
        sensors = [s for s in [self._interior_temp_sensor_id] if s]

        if sensors:
            self._unsub_listeners.append(
                async_track_state_change_event(
                    self.hass, sensors, self._on_sensor_state_change
                )
            )

        # ADR-037: Listener sur l'entité météo (remplace le polling minute)
        if self._weather_entity_id:
            self._unsub_listeners.append(
                async_track_state_change_event(
                    self.hass, [self._weather_entity_id], self._on_weather_state_change
                )
            )

        # Update weather forecasts every hour
        self._unsub_listeners.append(
            async_track_time_interval(
                self.hass, self._hourly_forecast_update, timedelta(hours=1)
            )
        )

    def _setup_time_triggers(self) -> None:
        """Configure les déclencheurs horaires selon le YAML (ADR-051)."""
        self._cancel_time_triggers()

        now = dt_util.now()

        # Guards pour target_hour et recoverycalc_hour (requis pour le fonctionnement)
        if not self.data.target_hour or not self.data.recoverycalc_hour:
            _LOGGER.error(
                "%s target_hour ou recoverycalc_hour non défini, triggers non configurés",
                self._log_prefix(),
            )
            return

        # Trigger pour recoverycalc_hour (arrêt chauffage le soir)
        recoverycalc_dt = now.replace(
            hour=self.data.recoverycalc_hour.hour,
            minute=self.data.recoverycalc_hour.minute,
            second=0,
            microsecond=0,
        )
        if recoverycalc_dt <= now:
            recoverycalc_dt += timedelta(days=1)

        self._timer_manager.schedule(
            TimerKey.RECOVERYCALC_HOUR,
            self._on_recoverycalc_hour,
            recoverycalc_dt,
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

        self._timer_manager.schedule(
            TimerKey.TARGET_HOUR,
            self._on_target_hour,
            target_dt,
        )

        # Trigger pour recovery_start_hour (démarrage relance)
        if self.data.recovery_start_hour:
            recovery_start = self.data.recovery_start_hour
            if recovery_start.tzinfo is None:
                recovery_start = dt_util.as_local(recovery_start)
            if recovery_start > now:
                self._timer_manager.schedule(
                    TimerKey.RECOVERY_START,
                    self._on_recovery_start_hour,
                    recovery_start,
                )
                _LOGGER.info(
                    "%s Trigger RECOVERY_START programmé pour %s",
                    self._log_prefix(),
                    recovery_start.time(),
                )
            else:
                _LOGGER.debug(
                    "%s recovery_start_hour %s est dans le passé, trigger non programmé",
                    self._log_prefix(),
                    recovery_start,
                )

        # Trigger pour recovery_update_hour (mise à jour calcul)
        if self.data.recovery_update_hour:
            recovery_update = self.data.recovery_update_hour
            if recovery_update.tzinfo is None:
                recovery_update = dt_util.as_local(recovery_update)
            if recovery_update > now:
                self._timer_manager.schedule(
                    TimerKey.RECOVERY_UPDATE,
                    self._on_recovery_update_hour,
                    recovery_update,
                )

    def _cancel_time_triggers(self) -> None:
        """Annule les déclencheurs horaires (ADR-051)."""
        self._timer_manager.cancel(TimerKey.RECOVERYCALC_HOUR)
        self._timer_manager.cancel(TimerKey.TARGET_HOUR)
        self._timer_manager.cancel(TimerKey.RECOVERY_START)
        self._timer_manager.cancel(TimerKey.RECOVERY_UPDATE)

    async def async_unload(self) -> None:
        """Déchargement du coordinateur (ADR-051)."""
        # ADR-051: Annulation de tous les timers en une seule opération
        self._timer_manager.cancel_all()

        # Annuler les listeners d'événements
        for unsub in self._unsub_listeners:
            unsub()
        self._unsub_listeners.clear()

    # ─────────────────────────────────────────────────────────────────────────
    # État initial et callbacks
    # ─────────────────────────────────────────────────────────────────────────

    async def _update_initial_states(self) -> None:
        """Récupération des états initiaux (ADR-054: conversion vers Celsius)"""
        if self._interior_temp_sensor_id:
            state = self.hass.states.get(self._interior_temp_sensor_id)
            if state and state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
                try:
                    # ADR-054: Convertir vers Celsius pour le ThermalSolver
                    raw_temp = float(state.state)
                    source_unit = self._get_sensor_unit(self._interior_temp_sensor_id)
                    self.data.interior_temp = self._normalize_to_celsius(
                        raw_temp, source_unit
                    )
                except ValueError:
                    pass

        self._update_weather_data()

    @callback
    def _on_sensor_state_change(self, event) -> None:
        """Callback lors d'un changement d'état du capteur de température.

        ADR-054: Convertit les températures vers Celsius pour le ThermalSolver.
        """
        new_state = event.data.get("new_state")
        if not new_state or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        entity_id = new_state.entity_id

        if entity_id == self._interior_temp_sensor_id:
            try:
                # ADR-054: Convertir vers Celsius
                raw_temp = float(new_state.state)
                source_unit = self._get_sensor_unit(entity_id)
                self.data.interior_temp = self._normalize_to_celsius(
                    raw_temp, source_unit
                )
                self._check_temperature_thresholds()
            except ValueError:
                pass

        self.async_set_updated_data(self.data)

    @callback
    def _on_weather_state_change(self, event) -> None:
        """Callback lors d'un changement d'état de l'entité météo.

        ADR-037: Remplace le polling périodique d'une minute.
        Met à jour les données météo et la moyenne de vent uniquement
        quand l'entité météo change réellement.
        """
        new_state = event.data.get("new_state")
        if not new_state or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        self._update_weather_data()
        self._update_wind_speed_average()
        self.async_set_updated_data(self.data)

    @callback
    def _hourly_forecast_update(self, _now) -> None:
        """Mise à jour des prévisions météo (chaque heure)"""
        self.hass.async_create_task(self._update_weather_forecasts())

    # ─────────────────────────────────────────────────────────────────────────
    # Déclencheurs horaires (équivalent des automations YAML)
    # ─────────────────────────────────────────────────────────────────────────

    @callback
    def _on_recoverycalc_hour(self, _now) -> None:
        """Appelé à l'heure de coupure du chauffage (recoverycalc_hour)
        Équivalent de l'automation 'heatingstopTIME' du YAML
        """
        _LOGGER.info("%s Heure de coupure chauffage atteinte", self._log_prefix())

        if not self.data.smartheating_mode:
            self._reschedule_recoverycalc_hour()
            return

        # Déléguer les calculs lourds à une tâche asynchrone
        self.hass.async_create_task(self._async_on_recoverycalc_hour())

    async def _async_on_recoverycalc_hour(self) -> None:
        """Exécute l'initialisation à l'heure de coupure du chauffage.

        Transition: HEATING_ON → DETECTING_LAG (État 1 → État 2)

        Conformément au YAML original (automation heatingstopTIME):
        - On enregistre les valeurs courantes (temps, température)
        - On active la détection du lag de température
        - On N'appelle PAS calculate_recovery_time ici (sera fait après
          détection de la baisse de -0.2°C dans _on_temperature_decrease_detected)
        """
        # Initialisation des constantes si première exécution
        if self.data.rcth_lw <= 0:
            self.data.rcth_lw = 50.0
            self.data.rcth_hw = 50.0
            self.data.rpth_lw = 50.0
            self.data.rpth_hw = 50.0
            _LOGGER.info("%s Initialisation des constantes à 50", self._log_prefix())

        # Enregistre les valeurs courantes (snapshot avant refroidissement)
        self.data.time_recovery_calc = dt_util.now()
        self.data.temp_recovery_calc = self.data.interior_temp or 17.0
        self.data.text_recovery_calc = self.data.exterior_temp or 0.0

        # Transition vers DETECTING_LAG (État 2)
        # On attend la baisse de température de 0.2°C avant de lancer les calculs
        if not self.transition_to(SmartHRTState.DETECTING_LAG):
            self.force_state(SmartHRTState.DETECTING_LAG)
        # ADR-040: temp_lag_detection_active est maintenant calculé depuis current_state
        _LOGGER.debug("%s Transition vers état DETECTING_LAG", self._log_prefix())

        # Sauvegarder l'heure de relance avant calcul
        prev_recovery_start = self.data.recovery_start_hour

        # ADR-048: Calculs synchrones car < 10ms et pas d'I/O bloquante
        self.calculate_recovery_time()

        # Programmer le trigger de relance si nécessaire (depuis le thread principal)
        now = dt_util.now()
        if (
            self.data.recovery_start_hour
            and prev_recovery_start != self.data.recovery_start_hour
            and self.data.recovery_start_hour > now
        ):
            self._schedule_recovery_start(self.data.recovery_start_hour)

        # Toujours programmer la mise à jour de recovery_update_hour
        # pour maintenir la chaîne de mises à jour active
        # ADR-048: Calcul synchrone (< 10ms)
        update_time = self.calculate_recovery_update_time()
        if update_time:
            self.data.recovery_update_hour = update_time
            self._schedule_recovery_update(update_time)

        self._reschedule_recoverycalc_hour()

        # Sauvegarder l'état après la transition
        await self._save_learned_data()

        self.async_set_updated_data(self.data)

    @callback
    def _on_recovery_start_hour(self, _now) -> None:
        """Appelé à l'heure calculée de démarrage de la relance (recoverystart_hour)
        Équivalent de l'automation 'boostTIME' du YAML
        """
        _LOGGER.info("%s Heure de démarrage relance atteinte", self._log_prefix())

        if not self.data.smartheating_mode:
            return

        # Éviter de déclencher si on est déjà en RECOVERY ou HEATING_PROCESS
        if self.data.current_state in (
            SmartHRTState.RECOVERY,
            SmartHRTState.HEATING_PROCESS,
        ):
            _LOGGER.debug(
                "%s Relance ignorée, déjà en état %s",
                self._log_prefix(),
                self.data.current_state,
            )
            return

        self.on_recovery_start()

    @callback
    def _on_target_hour(self, _now) -> None:
        """Appelé à l'heure cible (target_hour / réveil)
        Équivalent de l'automation 'recoveryendTIME' du YAML
        """
        _LOGGER.info("%s Heure cible atteinte", self._log_prefix())

        if self.data.smartheating_mode and self.data.rp_calc_mode:
            self.on_recovery_end()

        self._reschedule_target_hour()

    @callback
    def _on_recovery_update_hour(self, _now) -> None:
        """Appelé pour mettre à jour le calcul de l'heure de relance
        Équivalent de l'automation 'Nth_RECOVERY_calc' du YAML
        """
        if not self.data.smartheating_mode:
            return

        _LOGGER.debug("%s Mise à jour du calcul de relance", self._log_prefix())
        # Déléguer les calculs lourds à une tâche asynchrone
        self.hass.async_create_task(self._async_on_recovery_update_hour())

    async def _async_on_recovery_update_hour(self) -> None:
        """Exécute les calculs de mise à jour (ADR-048: synchrones car < 10ms).

        ADR-053: Implémente le Snooze intelligent - si la durée estimée de relance
        est inférieure au seuil MIN_DURATION_THRESHOLD_HOURS (15 min), aucune
        relance n'est programmée et le système reste silencieusement en MONITORING.
        """
        # Sauvegarder l'heure de relance avant calcul
        prev_recovery_start = self.data.recovery_start_hour

        # N'exécuter les calculs que si recovery_calc_mode est actif
        # ADR-048: Calculs synchrones (pas d'I/O, < 10ms chacun)
        if self.data.recovery_calc_mode:
            self.calculate_rcth_fast()
            self.calculate_recovery_time()

            # Programmer le trigger de relance si nécessaire (depuis le thread principal)
            now = dt_util.now()

            # ADR-053: Snooze intelligent - vérifier le seuil minimum d'activation
            if self.data.recovery_duration_hours < MIN_DURATION_THRESHOLD_HOURS:
                # Durée insuffisante → Snooze: annuler tout trigger existant
                if self._timer_manager.is_active(TimerKey.RECOVERY_START):
                    self._timer_manager.cancel(TimerKey.RECOVERY_START)
                    _LOGGER.info(
                        "%s [ADR-053 Snooze] Durée estimée %.1f min < seuil %d min "
                        "→ relance annulée, reste en MONITORING",
                        self._log_prefix(),
                        self.data.recovery_duration_hours * 60,
                        int(MIN_DURATION_THRESHOLD_HOURS * 60),
                    )
                else:
                    _LOGGER.debug(
                        "%s [ADR-053 Snooze] Durée estimée %.1f min < seuil %d min "
                        "→ pas de relance programmée",
                        self._log_prefix(),
                        self.data.recovery_duration_hours * 60,
                        int(MIN_DURATION_THRESHOLD_HOURS * 60),
                    )
            elif (
                self.data.recovery_start_hour
                and prev_recovery_start != self.data.recovery_start_hour
                and self.data.recovery_start_hour > now
            ):
                self._schedule_recovery_start(self.data.recovery_start_hour)

        # Toujours reprogrammer le prochain trigger de mise à jour
        # pour maintenir la chaîne active même si recovery_calc_mode est off
        # ADR-048: Calcul synchrone (< 10ms)
        update_time = self.calculate_recovery_update_time()

        if update_time:
            self.data.recovery_update_hour = update_time
            self._schedule_recovery_update(update_time)
            _LOGGER.debug(
                "%s Prochaine mise à jour programmée: %s",
                self._log_prefix(),
                update_time,
            )

        self.async_set_updated_data(self.data)

    def _reschedule_recoverycalc_hour(self) -> None:
        """Reprogramme le déclencheur recoverycalc_hour pour la prochaine occurrence (ADR-051).

        Calcule la prochaine occurrence : aujourd'hui si l'heure n'est pas
        encore passée, demain sinon. Ceci évite de sauter un jour quand
        un cycle est forcé manuellement avant l'heure de coupure.
        """
        if not self.data.recoverycalc_hour:
            return
        now = dt_util.now()
        next_trigger = now.replace(
            hour=self.data.recoverycalc_hour.hour,
            minute=self.data.recoverycalc_hour.minute,
            second=0,
            microsecond=0,
        )
        # Ajouter 1 jour seulement si l'heure est déjà passée aujourd'hui
        if next_trigger <= now:
            next_trigger += timedelta(days=1)

        self._timer_manager.schedule(
            TimerKey.RECOVERYCALC_HOUR,
            self._on_recoverycalc_hour,
            next_trigger,
        )
        _LOGGER.debug(
            "%s Timer RECOVERYCALC_HOUR reprogrammé pour %s",
            self._log_prefix(),
            next_trigger,
        )

    def _reschedule_target_hour(self) -> None:
        """Reprogramme le déclencheur target_hour pour la prochaine occurrence (ADR-051).

        Calcule la prochaine occurrence : aujourd'hui si l'heure n'est pas
        encore passée, demain sinon.
        """
        if not self.data.target_hour:
            return
        now = dt_util.now()
        next_trigger = now.replace(
            hour=self.data.target_hour.hour,
            minute=self.data.target_hour.minute,
            second=0,
            microsecond=0,
        )
        # Ajouter 1 jour seulement si l'heure est déjà passée aujourd'hui
        if next_trigger <= now:
            next_trigger += timedelta(days=1)

        self._timer_manager.schedule(
            TimerKey.TARGET_HOUR,
            self._on_target_hour,
            next_trigger,
        )
        _LOGGER.debug(
            "%s Timer TARGET_HOUR reprogrammé pour %s",
            self._log_prefix(),
            next_trigger,
        )

    def _schedule_recovery_start(self, trigger_time: datetime) -> None:
        """Programme le déclencheur de démarrage de relance (ADR-051).

        Annule le trigger précédent s'il existe avant d'en programmer un nouveau.
        Génère des logs appropriés pour la traçabilité.
        """
        was_active = self._timer_manager.is_active(TimerKey.RECOVERY_START)

        # ADR-051: schedule() annule automatiquement l'ancien timer
        self._timer_manager.schedule(
            TimerKey.RECOVERY_START,
            self._on_recovery_start_hour,
            trigger_time,
        )

        if was_active:
            _LOGGER.debug(
                "%s Trigger reprogrammé: annulation du précédent, nouveau à %s",
                self._log_prefix(),
                trigger_time,
            )
        else:
            _LOGGER.debug(
                "%s Nouveau trigger recovery_start programmé: %s",
                self._log_prefix(),
                trigger_time,
            )

    @callback
    def _schedule_recovery_update(self, trigger_time: datetime) -> None:
        """Programme le déclencheur de mise à jour du calcul (ADR-051)."""
        _LOGGER.debug(
            "%s Programmation prochaine mise à jour: %s",
            self._log_prefix(),
            trigger_time,
        )
        # ADR-051: schedule() annule automatiquement l'ancien timer
        self._timer_manager.schedule(
            TimerKey.RECOVERY_UPDATE,
            self._on_recovery_update_hour,
            trigger_time,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Données météo
    # ─────────────────────────────────────────────────────────────────────────

    def _update_weather_data(self) -> None:
        """Mise à jour des données météo actuelles.

        ADR-002: Utilise l'entité météo configurée explicitement par l'utilisateur
        au lieu de scanner automatiquement toutes les entités weather.
        ADR-054: Convertit les températures vers Celsius pour le ThermalSolver.
        """
        if not self._weather_entity_id:
            _LOGGER.debug(
                "%s Aucune entité météo configurée, mise à jour météo ignorée",
                self._log_prefix(),
            )
            return

        weather = self.hass.states.get(self._weather_entity_id)
        if weather is None:
            _LOGGER.warning(
                "%s Entité météo %s non trouvée",
                self._log_prefix(),
                self._weather_entity_id,
            )
            return

        if (temp := weather.attributes.get("temperature")) is not None:
            # ADR-054: Convertir vers Celsius
            raw_temp = float(temp)
            source_unit = self._get_sensor_unit(self._weather_entity_id)
            self.data.exterior_temp = self._normalize_to_celsius(raw_temp, source_unit)

        if (wind := weather.attributes.get("wind_speed")) is not None:
            # ADR-055: Convertir vers m/s
            raw_wind = float(wind)
            wind_unit = self._get_wind_speed_unit(self._weather_entity_id)
            self.data.wind_speed = self._normalize_to_ms(raw_wind, wind_unit) or 0.0
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
        """Mise à jour des prévisions météo (température et vent).

        ADR-002: Utilise l'entité météo configurée explicitement par l'utilisateur.
        ADR-054: Convertit les températures vers Celsius pour le ThermalSolver.
        """
        if not self._weather_entity_id:
            _LOGGER.debug(
                "%s Aucune entité météo configurée, mise à jour prévisions ignorée",
                self._log_prefix(),
            )
            return

        entity_id = self._weather_entity_id
        # ADR-054: Détecter l'unité du capteur météo pour conversion température
        source_unit = self._get_sensor_unit(entity_id)
        # ADR-055: Détecter l'unité du capteur météo pour conversion vitesse du vent
        wind_source_unit = self._get_wind_speed_unit(entity_id)

        try:
            # Vérifier que le service existe avant de l'appeler
            if not self.hass.services.has_service("weather", "get_forecasts"):
                _LOGGER.debug(
                    "%s Service weather.get_forecasts pas encore disponible (démarrage en cours)",
                    self._log_prefix(),
                )
                return

            # Appeler le service weather.get_forecasts
            forecast_response = await self.hass.services.async_call(
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
                                        # ADR-054: Convertir vers Celsius
                                        temp_c = self._normalize_to_celsius(
                                            float(temp_val), source_unit
                                        )
                                        if temp_c is not None:
                                            temps.append(temp_c)

                                    wind_val = f.get("wind_speed")
                                    if isinstance(wind_val, (int, float)):
                                        # ADR-055: Convertir vers km/h
                                        wind_kmh = self._normalize_to_kmh(
                                            float(wind_val), wind_source_unit
                                        )
                                        if wind_kmh is not None:
                                            winds.append(wind_kmh)

                            if temps:
                                self.data.temperature_forecast_avg = sum(temps) / len(
                                    temps
                                )

                            if winds:
                                self.data.wind_speed_forecast_avg = sum(winds) / len(
                                    winds
                                )

                            _LOGGER.debug(
                                "%s Prévisions mises à jour: temp=%.1f°C, vent=%.1fkm/h",
                                self._log_prefix(),
                                self.data.temperature_forecast_avg,
                                self.data.wind_speed_forecast_avg,
                            )
        except ServiceNotFound:
            _LOGGER.debug(
                "%s Service weather.get_forecasts non disponible au démarrage",
                self._log_prefix(),
            )
        except Exception as ex:
            _LOGGER.warning(
                "%s Erreur lors de la récupération des prévisions météo: %s",
                self._log_prefix(),
                ex,
            )

    def _calculate_windchill(self) -> None:
        """Calcul de la température ressentie (windchill).

        ADR-026: Délègue au ThermalSolver pour le calcul Pure Python.
        """
        if self.data.exterior_temp is None:
            return

        self.data.windchill = self._thermal_solver.calculate_windchill(
            self.data.exterior_temp,
            self.data.wind_speed,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # ADR-007: Compensation météo - Interpolation linéaire selon le vent
    # ─────────────────────────────────────────────────────────────────────────

    def _get_interpolated_rcth(self, wind_kmh: float) -> float:
        """Retourne RCth interpolé selon le vent (ADR-026: via ThermalSolver)."""
        coeffs = self._build_thermal_coefficients()
        return self._thermal_solver.get_interpolated_rcth(coeffs, wind_kmh)

    def _get_interpolated_rpth(self, wind_kmh: float) -> float:
        """Retourne RPth interpolé selon le vent (ADR-026: via ThermalSolver)."""
        coeffs = self._build_thermal_coefficients()
        return self._thermal_solver.get_interpolated_rpth(coeffs, wind_kmh)

    def _build_thermal_coefficients(self) -> ThermalCoefficients:
        """Construit un objet ThermalCoefficients depuis les données actuelles.

        ADR-026: Facilite le passage des données au ThermalSolver.
        """
        return ThermalCoefficients(
            rcth=self.data.rcth,
            rpth=self.data.rpth,
            rcth_lw=self.data.rcth_lw,
            rcth_hw=self.data.rcth_hw,
            rpth_lw=self.data.rpth_lw,
            rpth_hw=self.data.rpth_hw,
            rcth_calculated=self.data.rcth_calculated,
            rpth_calculated=self.data.rpth_calculated,
            rcth_fast=self.data.rcth_fast,
            relaxation_factor=self.data.relaxation_factor,
            last_rcth_error=self.data.last_rcth_error,
            last_rpth_error=self.data.last_rpth_error,
        )

    def _build_thermal_state(self) -> ThermalState:
        """Construit un objet ThermalState depuis les données actuelles.

        ADR-026: Facilite le passage des données au ThermalSolver.
        """
        return ThermalState(
            interior_temp=self.data.interior_temp,
            exterior_temp=self.data.exterior_temp,
            windchill=self.data.windchill,
            wind_speed_ms=self.data.wind_speed,
            wind_speed_avg_ms=self.data.wind_speed_avg,
            temperature_forecast_avg=self.data.temperature_forecast_avg,
            wind_speed_forecast_avg_kmh=self.data.wind_speed_forecast_avg,
            tsp=self.data.tsp,
            target_hour=self.data.target_hour or dt_time(6, 0),
            now=dt_util.now(),
            temp_recovery_calc=self.data.temp_recovery_calc,
            text_recovery_calc=self.data.text_recovery_calc,
            temp_recovery_start=self.data.temp_recovery_start,
            text_recovery_start=self.data.text_recovery_start,
            temp_recovery_end=self.data.temp_recovery_end,
            text_recovery_end=self.data.text_recovery_end,
            time_recovery_calc=self.data.time_recovery_calc,
            time_recovery_start=self.data.time_recovery_start,
            time_recovery_end=self.data.time_recovery_end,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # ADR-005: Stratégie de pilotage - Calculs thermiques d'anticipation
    # ─────────────────────────────────────────────────────────────────────────

    def calculate_recovery_time(self) -> None:
        """Calcule l'heure de démarrage de la relance (ADR-005, ADR-026, ADR-053).

        ADR-026: Délègue au ThermalSolver pour le calcul Pure Python.
        ADR-053: Stocke aussi la durée estimée pour le Snooze intelligent.
        Utilise les prévisions météo et 20 itérations pour affiner la prédiction.
        """
        now = dt_util.now()
        state = self._build_thermal_state()
        coeffs = self._build_thermal_coefficients()

        result = self._thermal_solver.calculate_recovery_duration(state, coeffs, now)

        self.data.recovery_start_hour = result.recovery_start_hour
        # ADR-053: Stocker la durée estimée pour le Snooze
        self.data.recovery_duration_hours = result.duration_hours

        # Note: Le scheduling du trigger est fait dans le contexte async appelant
        # car async_track_point_in_time doit être appelé depuis le thread principal

        _LOGGER.debug(
            "%s Recovery time: %s (%.2fh avant target)",
            self._log_prefix(),
            self.data.recovery_start_hour,
            result.duration_hours,
        )

    def calculate_recovery_update_time(self) -> datetime | None:
        """Calcule l'heure de mise à jour de la relance (ADR-026: via ThermalSolver).

        La logique:
        - Reconstruit recoverystart_time à partir de l'heure de recovery_start_hour
        - Calcule le temps restant avant la relance
        - Reprogramme dans max(time_remaining/3, 0) secondes, plafonné à 1200s (20min)
        - À moins de 30min avant la relance, arrête en programmant dans 3600s
        """
        if self.data.recovery_start_hour is None:
            return None

        now = dt_util.now()
        update_time = self._thermal_solver.calculate_recovery_update_time(
            self.data.recovery_start_hour,
            now,
        )

        if update_time:
            _LOGGER.debug(
                "%s Recovery update time calculated: %s",
                self._log_prefix(),
                update_time,
            )

        return update_time

    def calculate_rcth_fast(self) -> None:
        """Calcule l'évolution dynamique de RCth (ADR-026: via ThermalSolver)."""
        if (
            self.data.interior_temp is None
            or self.data.exterior_temp is None
            or self.data.time_recovery_calc is None
        ):
            return

        dt_hours = (dt_util.now() - self.data.time_recovery_calc).total_seconds() / 3600

        result = self._thermal_solver.calculate_rcth_fast(
            interior_temp=self.data.interior_temp,
            exterior_temp=self.data.exterior_temp,
            temp_at_start=self.data.temp_recovery_calc,
            text_at_start=self.data.text_recovery_calc,
            time_since_start_hours=dt_hours,
        )

        if result is not None:
            self.data.rcth_fast = result

    def calculate_rcth_at_recovery_start(self) -> None:
        """Calcule RCth au démarrage de la relance (ADR-026: via ThermalSolver)."""
        if (
            self.data.time_recovery_start is None
            or self.data.time_recovery_calc is None
        ):
            return

        result = self._thermal_solver.calculate_rcth_at_recovery(
            temp_recovery_calc=self.data.temp_recovery_calc,
            temp_recovery_start=self.data.temp_recovery_start,
            text_recovery_calc=self.data.text_recovery_calc,
            text_recovery_start=self.data.text_recovery_start,
            time_recovery_calc=self.data.time_recovery_calc,
            time_recovery_start=self.data.time_recovery_start,
        )

        if result is not None:
            self.data.rcth_calculated = result

        if self.data.recovery_adaptive_mode:
            self._update_coefficients("rcth")

    def calculate_rpth_at_recovery_end(self) -> None:
        """Calcule RPth à la fin de la relance (ADR-026, ADR-053: via ThermalSolver).

        ADR-053: Sécurisation de l'apprentissage - Le calcul est conditionné par:
        - La durée réelle de chauffe >= MIN_LEARNING_DURATION_HOURS (15 min)
        Si le cycle a été trop court (Snooze passif ou apports extérieurs),
        le calcul est annulé pour éviter de corrompre le modèle thermique.

        Utilise wind_speed_avg (moyenne 4h) pour l'interpolation RCth,
        conformément au YAML original.
        """
        if self.data.time_recovery_start is None or self.data.time_recovery_end is None:
            return

        # ADR-053: Calculer la durée réelle de chauffe
        actual_heating_duration_hours = (
            self.data.time_recovery_end.timestamp()
            - self.data.time_recovery_start.timestamp()
        ) / 3600

        # ADR-053: Vérifier le seuil minimum d'apprentissage
        if actual_heating_duration_hours < MIN_LEARNING_DURATION_HOURS:
            _LOGGER.info(
                "%s [ADR-053 Learning Guard] Durée réelle de chauffe %.1f min < seuil %d min "
                "→ calcul RPth annulé pour protéger le modèle thermique",
                self._log_prefix(),
                actual_heating_duration_hours * 60,
                int(MIN_LEARNING_DURATION_HOURS * 60),
            )
            return

        # Utiliser wind_speed_avg (moyenne 4h) comme dans le YAML
        wind_kmh = self.data.wind_speed_avg * 3.6
        rcth_interpol = self._get_interpolated_rcth(wind_kmh)

        result = self._thermal_solver.calculate_rpth_at_recovery(
            temp_recovery_start=self.data.temp_recovery_start,
            temp_recovery_end=self.data.temp_recovery_end,
            text_recovery_start=self.data.text_recovery_start,
            text_recovery_end=self.data.text_recovery_end,
            time_recovery_start=self.data.time_recovery_start,
            time_recovery_end=self.data.time_recovery_end,
            rcth_interpolated=rcth_interpol,
        )

        if result is not None:
            self.data.rpth_calculated = result

        if self.data.recovery_adaptive_mode:
            self._update_coefficients("rpth")

    def _update_coefficients(self, coef_type: str) -> None:
        """Met à jour les coefficients avec relaxation (ADR-006, ADR-026).

        ADR-026: Délègue au ThermalSolver pour le calcul Pure Python.
        Utilise wind_speed_avg (moyenne 4h) conformément au YAML original.
        """
        # Utiliser wind_speed_avg (moyenne 4h) comme dans le YAML
        wind_kmh = self.data.wind_speed_avg * 3.6

        if coef_type == "rcth":
            result = self._thermal_solver.update_coefficients(
                coef_type="rcth",
                current_lw=self.data.rcth_lw,
                current_hw=self.data.rcth_hw,
                current_main=self.data.rcth,
                calculated_value=self.data.rcth_calculated,
                wind_kmh=wind_kmh,
                relaxation_factor=self.data.relaxation_factor,
            )
            self.data.rcth_lw = result.coef_lw
            self.data.rcth_hw = result.coef_hw
            self.data.rcth = result.coef_main
            self.data.last_rcth_error = result.error
            # Note: La sauvegarde est effectuée par la fonction appelante
        else:
            result = self._thermal_solver.update_coefficients(
                coef_type="rpth",
                current_lw=self.data.rpth_lw,
                current_hw=self.data.rpth_hw,
                current_main=self.data.rpth,
                calculated_value=self.data.rpth_calculated,
                wind_kmh=wind_kmh,
                relaxation_factor=self.data.relaxation_factor,
            )
            self.data.rpth_lw = result.coef_lw
            self.data.rpth_hw = result.coef_hw
            self.data.rpth = result.coef_main
            self.data.last_rpth_error = result.error
            # Note: La sauvegarde est effectuée par la fonction appelante

    # ─────────────────────────────────────────────────────────────────────────
    # Événements chauffage
    # ─────────────────────────────────────────────────────────────────────────

    def _check_temperature_thresholds(self) -> None:
        """Vérifie les seuils de température
        Gère la détection du lag de température et la fin de relance
        """
        if self.data.interior_temp is None:
            return

        # ADR-008: Validation arrêt par détection lag de température
        # Attend une baisse de 0.2°C pour confirmer l'arrêt réel du chauffage
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

        Transition: DETECTING_LAG → MONITORING (État 2 → État 3)
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

        # Transition vers MONITORING (État 3)
        if not self.transition_to(SmartHRTState.MONITORING):
            self.force_state(SmartHRTState.MONITORING)
        # ADR-040: recovery_calc_mode et temp_lag_detection_active sont calculés depuis current_state
        _LOGGER.debug("%s Transition vers état MONITORING", self._log_prefix())

        self.calculate_recovery_time()

        # Calculer et programmer la prochaine mise à jour (comme dans le YAML)
        update_time = self.calculate_recovery_update_time()
        if update_time:
            self.data.recovery_update_hour = update_time
            self._schedule_recovery_update(update_time)

        _LOGGER.info(
            "%s Baisse de température détectée après %.0fs de lag",
            self._log_prefix(),
            self.data.stop_lag_duration,
        )

        # Sauvegarder l'état après la transition
        self.hass.async_create_task(self._save_learned_data())

        self.async_set_updated_data(self.data)

    # ─────────────────────────────────────────────────────────────────────────
    # ADR-039: Restauration simplifiée avec auto-correction
    # ─────────────────────────────────────────────────────────────────────────

    def _is_night_period(
        self, current_time: dt_time, target: dt_time, recoverycalc: dt_time
    ) -> bool:
        """Détermine si on est en période nocturne (entre recoverycalc et target).

        Args:
            current_time: Heure actuelle (time)
            target: Heure cible du matin (ex: 06:00)
            recoverycalc: Heure de calcul du soir (ex: 23:00)

        Returns:
            True si on est en période nocturne (MONITORING attendu)
        """
        if target < recoverycalc:
            # Cas normal: target=06:00, recoverycalc=23:00
            # Nuit = après 23:00 OU avant 06:00
            return current_time >= recoverycalc or current_time < target
        else:
            # Cas atypique: recoverycalc=13:30, target=17:30
            # "Nuit" = entre 13:30 et 17:30
            return recoverycalc <= current_time < target

    def _is_state_coherent(self, persisted_state: SmartHRTState, now: datetime) -> bool:
        """Vérifie si l'état persisté est cohérent avec l'heure actuelle (ADR-039).

        Règles simplifiées :
        1. HEATING_ON est toujours valide (état par défaut sûr)
        2. MONITORING/DETECTING_LAG sont valides la nuit (après recoverycalc, avant target)
        3. RECOVERY/HEATING_PROCESS sont valides si recovery_start_hour <= now < target

        Args:
            persisted_state: État lu depuis la persistance
            now: Heure actuelle

        Returns:
            True si l'état est cohérent, False sinon
        """
        # HEATING_ON est toujours valide (état sûr par défaut)
        if persisted_state == SmartHRTState.HEATING_ON:
            return True

        current_time = now.time()
        target = self.data.target_hour
        recoverycalc = self.data.recoverycalc_hour

        # Si target ou recoverycalc manquent, on ne peut pas déterminer la cohérence
        if not target or not recoverycalc:
            return False

        is_night = self._is_night_period(current_time, target, recoverycalc)

        # MONITORING/DETECTING_LAG valides la nuit OU si recovery_start_hour est proche
        if persisted_state in (SmartHRTState.MONITORING, SmartHRTState.DETECTING_LAG):
            if is_night:
                return True
            # Aussi valide si recovery_start_hour est dans le futur proche (< 6h)
            if self.data.recovery_start_hour and self.data.recovery_start_hour > now:
                hours_until_recovery = (
                    self.data.recovery_start_hour - now
                ).total_seconds() / 3600
                if hours_until_recovery < 6:
                    return True
            return False

        # RECOVERY/HEATING_PROCESS valides pendant la période de relance
        if persisted_state in (SmartHRTState.RECOVERY, SmartHRTState.HEATING_PROCESS):
            if not self.data.recovery_start_hour:
                return False  # Pas de recovery_start_hour = incohérent
            # recovery_start_hour doit être récent (< 24h) pour être valide
            hours_since_recovery = (
                now - self.data.recovery_start_hour
            ).total_seconds() / 3600
            if hours_since_recovery > 24:
                return False  # État périmé
            # Valide si : recovery_start_hour <= now ET current_time < target
            return now >= self.data.recovery_start_hour and current_time < target

        # État inconnu = incohérent
        return False

    def _restore_triggers_for_state(self, state: SmartHRTState, now: datetime) -> None:
        """Reprogramme les triggers appropriés pour l'état restauré (ADR-039).

        Args:
            state: État courant restauré
            now: Heure actuelle
        """
        if state == SmartHRTState.MONITORING:
            # Reprogrammer TARGET_HOUR pour le matin
            self._reschedule_target_hour()
            # Et RECOVERY_START si pas encore passé
            if self.data.recovery_start_hour:
                # Vérifier que recovery_start_hour est bien aujourd'hui
                if self.data.recovery_start_hour.date() == now.date():
                    if self.data.recovery_start_hour > now:
                        self._schedule_recovery_start(self.data.recovery_start_hour)
                    else:
                        # L'heure est passée AUJOURD'HUI = on démarre
                        _LOGGER.info(
                            "%s Heure de relance dépassée, démarrage immédiat",
                            self._log_prefix(),
                        )
                        self.on_recovery_start()
                else:
                    # Date périmée → recalculer recovery_start_hour
                    _LOGGER.info(
                        "%s recovery_start_hour périmé (%s), recalcul",
                        self._log_prefix(),
                        self.data.recovery_start_hour,
                    )
                    self.calculate_recovery_time()
                    if (
                        self.data.recovery_start_hour
                        and self.data.recovery_start_hour > now
                    ):
                        self._schedule_recovery_start(self.data.recovery_start_hour)

        elif state == SmartHRTState.DETECTING_LAG:
            # La surveillance de température reprendra automatiquement
            # Mais il faut reprogrammer TARGET_HOUR pour le matin
            self._reschedule_target_hour()

        elif state in (SmartHRTState.RECOVERY, SmartHRTState.HEATING_PROCESS):
            # Vérifier si target_hour est dépassée
            if not self.data.target_hour:
                return
            target_dt = now.replace(
                hour=self.data.target_hour.hour,
                minute=self.data.target_hour.minute,
                second=0,
                microsecond=0,
            )
            if now >= target_dt:
                # Target dépassée, terminer le cycle
                self.on_recovery_end()
            else:
                # Reprogrammer le timer TARGET_HOUR
                self._reschedule_target_hour()

        elif state == SmartHRTState.HEATING_ON:
            # Reprogrammer les timers perdus au redémarrage
            self._reschedule_recoverycalc_hour()
            self._reschedule_target_hour()

    async def _restore_state_after_restart(self) -> None:
        """Restaure l'état après redémarrage avec vérification minimale (ADR-039).

        Principe "Trust the Persistence, Verify Minimally" :
        - L'état persisté est la source de vérité
        - Vérification de cohérence minimaliste
        - En cas d'incohérence, déduit le bon état (MONITORING ou HEATING_ON)
        - Fait la transition depuis INITIALIZING vers l'état cible
        """
        persisted_state = self.data.current_state
        now = dt_util.now()

        _LOGGER.info(
            "%s Restauration - État persisté: %s",
            self._log_prefix(),
            persisted_state.value,
        )

        # Déterminer l'état cible (cohérent ou déduit)
        if self._is_state_coherent(persisted_state, now):
            target_state = persisted_state
            _LOGGER.info(
                "%s État %s cohérent, transition INITIALIZING → %s",
                self._log_prefix(),
                persisted_state.value,
                target_state.value,
            )
        else:
            # Déduire le bon état plutôt que reset brutal vers HEATING_ON
            target_state = self._deduce_correct_state(now)
            _LOGGER.warning(
                "%s État incohérent %s pour l'heure actuelle, correction vers %s",
                self._log_prefix(),
                persisted_state.value,
                target_state.value,
            )
            # Mettre à jour l'état dans data pour cohérence
            self.data.current_state = target_state

        # Faire la transition depuis INITIALIZING vers l'état cible
        if self._state_machine.state == SmartHRTState.INITIALIZING:
            result = self._state_machine.transition_with_actions(target_state)
            if result.success:
                _LOGGER.info(
                    "%s Transition INITIALIZING → %s réussie",
                    self._log_prefix(),
                    target_state.value,
                )
                self._execute_actions(result.actions)
            else:
                _LOGGER.warning(
                    "%s Échec transition vers %s, forçage",
                    self._log_prefix(),
                    target_state.value,
                )
                self._state_machine._force_state_unsafe(target_state)
        else:
            # Déjà dans un état (cas rare), forcer l'état cible
            self.force_state(target_state)

        # Sauvegarder si l'état a été corrigé
        if target_state != persisted_state:
            await self._save_learned_data()

        # Reprogrammer les triggers pour l'état cible
        self._restore_triggers_for_state(target_state, now)
        self.async_set_updated_data(self.data)

    def _deduce_correct_state(self, now: datetime) -> SmartHRTState:
        """Déduit l'état correct basé sur l'heure actuelle.

        Utilisé quand l'état persisté est incohérent.

        Args:
            now: Heure actuelle

        Returns:
            L'état qui devrait être actif selon l'heure
        """
        current_time = now.time()
        target = self.data.target_hour
        recoverycalc = self.data.recoverycalc_hour

        # Si recovery_start_hour est dans le futur proche → MONITORING
        if self.data.recovery_start_hour and self.data.recovery_start_hour > now:
            hours_until = (self.data.recovery_start_hour - now).total_seconds() / 3600
            if hours_until < 6:
                _LOGGER.info(
                    "%s État déduit: MONITORING (recovery_start_hour dans %.1fh)",
                    self._log_prefix(),
                    hours_until,
                )
                return SmartHRTState.MONITORING

        # Si on est en période nocturne → MONITORING
        if target and recoverycalc:
            is_night = self._is_night_period(current_time, target, recoverycalc)
            if is_night:
                _LOGGER.info(
                    "%s État déduit: MONITORING (période nocturne)",
                    self._log_prefix(),
                )
                return SmartHRTState.MONITORING

        # Par défaut → HEATING_ON (état sûr)
        _LOGGER.info(
            "%s État déduit: HEATING_ON (défaut)",
            self._log_prefix(),
        )
        return SmartHRTState.HEATING_ON

    def on_heating_stop(self) -> None:
        """Appelé quand le chauffage s'arrête (service manuel)"""
        self.data.time_recovery_calc = dt_util.now()
        self.data.temp_recovery_calc = self.data.interior_temp or 17.0
        self.data.text_recovery_calc = self.data.exterior_temp or 0.0
        # ADR-040: temp_lag_detection_active est calculé depuis current_state
        self.calculate_recovery_time()
        # Reprogrammer le trigger de relance avec la nouvelle heure calculée
        if (
            self.data.recovery_start_hour
            and self.data.current_state == SmartHRTState.MONITORING
        ):
            try:
                self._schedule_recovery_start(self.data.recovery_start_hour)
            except Exception as e:
                _LOGGER.warning(
                    "%s Erreur reprogrammation trigger: %s", self._log_prefix(), e
                )
        self.async_set_updated_data(self.data)

    def on_recovery_start(self) -> None:
        """Appelé au début de la relance
        Équivalent de l'automation 'boostTIME' du YAML

        Transition: MONITORING → RECOVERY → HEATING_PROCESS (État 3 → État 4 → État 5)
        """
        # Transition vers RECOVERY (État 4)
        now = dt_util.now()
        updates = {
            "time_recovery_start": now,
            "temp_recovery_start": self.data.interior_temp or 17.0,
            "text_recovery_start": self.data.exterior_temp or 0.0,
        }
        actions = self._apply_state_transition_with_actions(
            SmartHRTState.RECOVERY,
            updates=updates,
            omit_actions={Action.SNAPSHOT_RECOVERY_START},
        )
        if actions is None:
            self.data.update(**updates)
            self.force_state(SmartHRTState.RECOVERY)
            actions = [
                Action.CANCEL_RECOVERY_TIMER,
                Action.CALCULATE_RCTH,
                Action.SAVE_DATA,
            ]
        _LOGGER.debug("%s Transition vers état RECOVERY", self._log_prefix())

        pre_actions = [action for action in actions if action != Action.SAVE_DATA]
        if pre_actions:
            self._execute_actions(pre_actions)

        # Transition vers HEATING_PROCESS (État 5) - chauffage en cours
        if not self.transition_to(SmartHRTState.HEATING_PROCESS):
            self.force_state(SmartHRTState.HEATING_PROCESS)
        _LOGGER.debug("%s Transition vers état HEATING_PROCESS", self._log_prefix())

        if Action.SAVE_DATA in actions:
            self._execute_actions([Action.SAVE_DATA])

        _LOGGER.info(
            "%s Début de relance - Tint=%.1f°C, RCth calculé=%.2f",
            self._log_prefix(),
            self.data.temp_recovery_start,
            self.data.rcth_calculated,
        )

        self.async_set_updated_data(self.data)

    def on_recovery_end(self) -> None:
        """Appelé à la fin de la relance (consigne atteinte ou target_hour)
        Équivalent de l'automation 'recoveryendTIME' du YAML

        Transition: HEATING_PROCESS → HEATING_ON (État 5 → État 1)
        """
        if not self.data.rp_calc_mode:
            return

        pre_actions = []
        # Transition vers HEATING_ON (État 1) - cycle terminé
        now = dt_util.now()
        updates = {
            "time_recovery_end": now,
            "temp_recovery_end": self.data.interior_temp or 17.0,
            "text_recovery_end": self.data.exterior_temp or 0.0,
        }
        actions = self._apply_state_transition_with_actions(
            SmartHRTState.HEATING_ON,
            updates=updates,
            omit_actions={Action.SNAPSHOT_RECOVERY_END},
        )
        if actions is None:
            self.data.update(**updates)
            self.force_state(SmartHRTState.HEATING_ON)
            actions = [
                Action.CALCULATE_RPTH,
                Action.SAVE_DATA,
            ]
        _LOGGER.debug(
            "%s Transition vers état HEATING_ON - Cycle terminé", self._log_prefix()
        )

        pre_actions = [action for action in actions if action != Action.SAVE_DATA]
        if pre_actions:
            self._execute_actions(pre_actions)

        if Action.SAVE_DATA in actions:
            self._execute_actions([Action.SAVE_DATA])

        _LOGGER.info(
            "%s Fin de relance - Tint=%.1f°C, RPth calculé=%.2f",
            self._log_prefix(),
            self.data.temp_recovery_end,
            self.data.rpth_calculated,
        )

        # Garantir que les timers sont reprogrammés pour le prochain cycle
        # Ceci évite de perdre le timer si le cycle a été forcé manuellement
        self._reschedule_recoverycalc_hour()
        self._reschedule_target_hour()

        self.async_set_updated_data(self.data)

    def _on_recovery_end(self) -> None:
        """Ancienne méthode interne - redirige vers on_recovery_end"""
        self.on_recovery_end()

    # ─────────────────────────────────────────────────────────────────────────
    # ADR-042: Méthodes Façade pour les services
    # ─────────────────────────────────────────────────────────────────────────

    async def async_manual_stop_heating(self) -> dict[str, Any]:
        """Arrêt manuel du chauffage - méthode façade pour les services (ADR-042).

        Encapsule:
        - Transition vers HEATING_ON
        - Réinitialisation des flags via la machine à états
        - Annulation des timers en cours
        - Reprogrammation des timers quotidiens
        - Sauvegarde des données
        """
        # ADR-051: Annuler les timers via TimerManager
        self._timer_manager.cancel(TimerKey.RECOVERY_START)
        self._timer_manager.cancel(TimerKey.RECOVERY_UPDATE)

        # Transition vers HEATING_ON
        if not self.transition_to(SmartHRTState.HEATING_ON):
            self.force_state(SmartHRTState.HEATING_ON)

        # Garantir que les timers quotidiens sont actifs
        self._reschedule_recoverycalc_hour()
        self._reschedule_target_hour()

        await self._save_learned_data()
        self.async_set_updated_data(self.data)

        _LOGGER.info("%s Arrêt manuel du chauffage effectué", self._log_prefix())

        return {
            "success": True,
            "state": str(self.data.current_state),
            "message": "Chauffage arrêté et réinitialisé",
        }

    async def async_start_heating_cycle(self) -> dict[str, Any]:
        """Démarrage d'un nouveau cycle de chauffage - méthode façade (ADR-042).

        Équivalent à l'appel de recoverycalc_hour.
        """
        await self._async_on_recoverycalc_hour()

        _LOGGER.info(
            "%s Nouveau cycle de chauffage démarré manuellement", self._log_prefix()
        )

        return {
            "success": True,
            "state": str(self.data.current_state),
            "recovery_start_hour": (
                self.data.recovery_start_hour.isoformat()
                if self.data.recovery_start_hour
                else None
            ),
            "message": "Cycle de chauffage démarré",
        }

    async def async_manual_start_recovery(self) -> dict[str, Any]:
        """Démarrage manuel de la relance - méthode façade (ADR-042).

        Encapsule:
        - Appel à on_recovery_start()
        - Sauvegarde des données
        """
        self.on_recovery_start()
        await self._save_learned_data()

        _LOGGER.info("%s Relance démarrée manuellement", self._log_prefix())

        return {
            "success": True,
            "state": str(self.data.current_state),
            "time_recovery_start": (
                self.data.time_recovery_start.isoformat()
                if self.data.time_recovery_start
                else None
            ),
            "rcth_calculated": self.data.rcth_calculated,
            "message": "Relance démarrée",
        }

    async def async_manual_end_recovery(self) -> dict[str, Any]:
        """Fin manuelle de la relance - méthode façade (ADR-042).

        Encapsule:
        - Appel à on_recovery_end()
        - Sauvegarde des données
        """
        self.on_recovery_end()
        await self._save_learned_data()

        _LOGGER.info("%s Relance terminée manuellement", self._log_prefix())

        return {
            "success": True,
            "state": str(self.data.current_state),
            "time_recovery_end": (
                self.data.time_recovery_end.isoformat()
                if self.data.time_recovery_end
                else None
            ),
            "rpth_calculated": self.data.rpth_calculated,
            "message": "Relance terminée",
        }

    def get_state_dict(self) -> dict[str, Any]:
        """Retourne l'état complet du coordinateur - méthode façade (ADR-042).

        Utilisée par le service get_state.
        """
        return {
            "success": True,
            "state": str(self.data.current_state),
            "smartheating_mode": self.data.smartheating_mode,
            "recovery_calc_mode": self.data.recovery_calc_mode,
            "rp_calc_mode": self.data.rp_calc_mode,
            "temp_lag_detection_active": self.data.temp_lag_detection_active,
            "interior_temp": self.data.interior_temp,
            "exterior_temp": self.data.exterior_temp,
            "target_hour": (
                self.data.target_hour.isoformat() if self.data.target_hour else None
            ),
            "recoverycalc_hour": (
                self.data.recoverycalc_hour.isoformat()
                if self.data.recoverycalc_hour
                else None
            ),
            "recovery_start_hour": (
                self.data.recovery_start_hour.isoformat()
                if self.data.recovery_start_hour
                else None
            ),
            "time_to_recovery_hours": self.get_time_to_recovery_hours(),
            "rcth": self.data.rcth,
            "rpth": self.data.rpth,
        }

    async def async_trigger_calculation(self) -> dict[str, Any]:
        """Force un recalcul du temps de relance - méthode façade (ADR-042)."""
        # ADR-048: Calcul synchrone (< 10ms, pas d'I/O bloquante)
        self.calculate_recovery_time()
        self.async_set_updated_data(self.data)

        return {
            "success": True,
            "recovery_start_hour": (
                self.data.recovery_start_hour.isoformat()
                if self.data.recovery_start_hour
                else None
            ),
            "time_to_recovery_hours": self.get_time_to_recovery_hours(),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # ADR-036: Méthode générique pour setters
    # ─────────────────────────────────────────────────────────────────────────

    def _update_and_recalculate(
        self,
        attr_name: str,
        value: float | dt_time,
        recalculate: bool = True,
        reschedule: bool = True,
        persist: bool = False,
    ) -> None:
        """Met à jour un attribut et gère les effets de bord de manière centralisée.

        ADR-036: Factorisation des setters pour éviter la duplication de code.

        Args:
            attr_name: Nom de l'attribut dans self.data (ex: "rcth", "tsp")
            value: Nouvelle valeur à assigner
            recalculate: Si True, recalcule recovery_time après modification
            reschedule: Si True, reprogramme le trigger si en MONITORING
            persist: Si True, sauvegarde les données après modification

        ADR-023: Protection try/except centralisée pour la reprogrammation.
        """
        # 1. Mise à jour atomique de la valeur
        setattr(self.data, attr_name, value)

        # 2. Recalcul optionnel de l'heure de relance
        if recalculate:
            self.calculate_recovery_time()

        # 3. Reprogrammation du trigger si nécessaire (ADR-023)
        if (
            reschedule
            and self.data.recovery_start_hour
            and self.data.current_state == SmartHRTState.MONITORING
        ):
            try:
                self._schedule_recovery_start(self.data.recovery_start_hour)
            except Exception as e:
                _LOGGER.warning(
                    "%s Erreur reprogrammation trigger: %s",
                    self._log_prefix(),
                    e,
                )

        # 4. Notification des entités
        self.async_set_updated_data(self.data)

        # 5. Persistance optionnelle
        if persist:
            self.hass.async_create_task(self._save_learned_data())

    # ─────────────────────────────────────────────────────────────────────────
    # Setters publics (ADR-036: factorisés via _update_and_recalculate)
    # ─────────────────────────────────────────────────────────────────────────

    def set_tsp(self, value: float) -> None:
        """Définit la température de consigne (TSP)."""
        self._update_and_recalculate("tsp", value)

    def set_target_hour(self, value: dt_time) -> None:
        """Définit l'heure cible (réveil)."""
        old_recovery_start = self.data.recovery_start_hour
        self._update_and_recalculate(
            "target_hour",
            value,
            reschedule=False,  # Géré par _setup_time_triggers
            persist=True,
        )
        new_recovery_start = self.data.recovery_start_hour
        _LOGGER.info(
            "%s target_hour=%s → recovery_start_hour: %s → %s",
            self._log_prefix(),
            value,
            old_recovery_start.time() if old_recovery_start else None,
            new_recovery_start.time() if new_recovery_start else None,
        )
        self._setup_time_triggers()

    def set_recoverycalc_hour(self, value: dt_time) -> None:
        """Définit l'heure de coupure chauffage."""
        self._update_and_recalculate(
            "recoverycalc_hour",
            value,
            recalculate=False,
            reschedule=False,
            persist=True,
        )
        self._setup_time_triggers()

    def set_smartheating_mode(self, value: bool) -> None:
        """Active/désactive le mode chauffage intelligent."""
        self.data.smartheating_mode = value
        self.async_set_updated_data(self.data)

    def set_recovery_adaptive_mode(self, value: bool) -> None:
        """Active/désactive le mode adaptatif."""
        self.data.recovery_adaptive_mode = value
        self.async_set_updated_data(self.data)

    def set_adaptive_mode(self, value: bool) -> None:
        """Alias pour set_recovery_adaptive_mode."""
        self.set_recovery_adaptive_mode(value)

    def set_rcth(self, value: float) -> None:
        """Définit le coefficient thermique RCth."""
        self._update_and_recalculate("rcth", value)

    def set_rpth(self, value: float) -> None:
        """Définit le coefficient thermique RPth."""
        self._update_and_recalculate("rpth", value)

    def set_relaxation_factor(self, value: float) -> None:
        """Définit le facteur de relaxation."""
        self._update_and_recalculate(
            "relaxation_factor", value, recalculate=False, reschedule=False
        )

    def set_rcth_lw(self, value: float) -> None:
        """Définit RCth pour vent faible."""
        self._update_and_recalculate("rcth_lw", value)

    def set_rcth_hw(self, value: float) -> None:
        """Définit RCth pour vent fort."""
        self._update_and_recalculate("rcth_hw", value)

    def set_rpth_lw(self, value: float) -> None:
        """Définit RPth pour vent faible."""
        self._update_and_recalculate("rpth_lw", value)

    def set_rpth_hw(self, value: float) -> None:
        """Définit RPth pour vent fort."""
        self._update_and_recalculate("rpth_hw", value)

    # ─────────────────────────────────────────────────────────────────────────
    # Public methods for services
    # ─────────────────────────────────────────────────────────────────────────

    async def reset_learning(self) -> None:
        """Reset all learned thermal coefficients to defaults.

        Resets RCth and RPth (and their wind variants) to default values
        and clears the error tracking. Also clears persistent storage.
        """
        _LOGGER.info(
            "%s Resetting learned coefficients to defaults", self._log_prefix()
        )
        self.data.rcth = DEFAULT_RCTH
        self.data.rpth = DEFAULT_RPTH
        self.data.rcth_lw = DEFAULT_RCTH
        self.data.rcth_hw = DEFAULT_RCTH
        self.data.rpth_lw = DEFAULT_RPTH
        self.data.rpth_hw = DEFAULT_RPTH
        self.data.rcth_calculated = 0.0
        self.data.rpth_calculated = 0.0
        self.data.rcth_fast = 0.0
        self.data.last_rcth_error = 0.0
        self.data.last_rpth_error = 0.0

        # Save the reset values to storage
        await self._save_learned_data()

        # Recalculate recovery time with new coefficients
        self.calculate_recovery_time()
        self.async_set_updated_data(self.data)

    def get_time_to_recovery_hours(self) -> float | None:
        """Calculate the time remaining until recovery starts in hours.

        Returns the duration in hours until the heating should start,
        or None if recovery_start_hour is not set.
        """
        if self.data.recovery_start_hour is None:
            return None

        now = dt_util.now()
        recovery_time = self.data.recovery_start_hour

        if recovery_time.tzinfo is None:
            recovery_time = dt_util.as_local(recovery_time)

        delta = recovery_time - now
        hours = delta.total_seconds() / 3600

        # Return 0 if time has passed
        return max(0, round(hours, 2))
