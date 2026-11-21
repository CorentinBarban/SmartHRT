"""Modèle de données unifié SmartHRT (Pydantic v2).

Toutes les températures sont stockées en Celsius ; la conversion Fahrenheit est
faite par le coordinator à la lecture des capteurs, pas à la persistance.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime
from datetime import time as dt_time
from typing import Annotated, Any, ClassVar, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    PlainSerializer,
    field_validator,
)

from .const import (
    DEFAULT_RCTH,
    DEFAULT_RCTH_MAX,
    DEFAULT_RCTH_MIN,
    DEFAULT_RELAXATION_FACTOR,
    DEFAULT_RPTH,
    DEFAULT_TSP,
)
from .core import SmartHRTState

# ─────────────────────────────────────────────────────────────────────────────
# Types personnalisés avec sérialiseurs Pydantic
# ─────────────────────────────────────────────────────────────────────────────


def _deque_validator(v: Any) -> deque[float]:
    """Convertit une liste en deque, préservant maxlen=50."""
    if v is None:
        return deque(maxlen=50)
    if isinstance(v, deque):
        return v
    if isinstance(v, (list, tuple)):
        return deque([float(x) for x in v if x is not None], maxlen=50)
    return deque(maxlen=50)


def _deque_serializer(d: deque[float]) -> list[float]:
    """Sérialise une deque en liste."""
    return list(d)


def _state_validator(v: Any) -> SmartHRTState:
    """Convertit une string en SmartHRTState."""
    if isinstance(v, SmartHRTState):
        return v
    if isinstance(v, str):
        try:
            return SmartHRTState(v)
        except ValueError:
            # État invalide → fallback sur HEATING_ON
            return SmartHRTState.HEATING_ON
    return SmartHRTState.HEATING_ON


def _state_serializer(state: SmartHRTState) -> str:
    """Sérialise un SmartHRTState en string."""
    return state.value


def _time_validator(v: Any) -> dt_time | None:
    """Convertit une string ISO en time."""
    if v is None:
        return None
    if isinstance(v, dt_time):
        return v
    if isinstance(v, str):
        try:
            return dt_time.fromisoformat(v)
        except ValueError:
            return None
    return None


def _datetime_validator(v: Any) -> datetime | None:
    """Convertit une string ISO en datetime."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        try:
            return datetime.fromisoformat(v)
        except ValueError:
            return None
    return None


# Types annotés avec validation et sérialisation automatiques
DequeFloat = Annotated[
    deque[float],
    BeforeValidator(_deque_validator),
    PlainSerializer(_deque_serializer, return_type=list[float]),
]

SmartHRTStateField = Annotated[
    SmartHRTState,
    BeforeValidator(_state_validator),
    PlainSerializer(_state_serializer, return_type=str),
]

TimeField = Annotated[
    dt_time | None,
    BeforeValidator(_time_validator),
]

DateTimeField = Annotated[
    datetime | None,
    BeforeValidator(_datetime_validator),
]


# ─────────────────────────────────────────────────────────────────────────────
# Modèle unifié SmartHRTData
# ─────────────────────────────────────────────────────────────────────────────


class SmartHRTData(BaseModel):
    """Source unique des données SmartHRT : types, contraintes, défauts et sérialisation.

    Validé à l'instanciation, à chaque assignation et au chargement depuis le stockage.
    """

    model_config = ConfigDict(
        validate_assignment=True,  # Validation à chaque assignation
        arbitrary_types_allowed=True,  # Pour deque
        extra="ignore",  # Ignore les champs inconnus (migration)
    )

    # ─────────────────────────────────────────────────────────────────────────
    # Configuration statique (modifiable via l'UI ou les services)
    # ─────────────────────────────────────────────────────────────────────────
    name: str = Field(default="SmartHRT", min_length=1, max_length=100)
    tsp: float = Field(default=DEFAULT_TSP, ge=13.0, le=26.0)
    target_hour: TimeField = Field(default_factory=lambda: dt_time(6, 0, 0))
    recoverycalc_hour: TimeField = Field(default_factory=lambda: dt_time(23, 0, 0))
    smartheating_mode: bool = Field(default=True)
    recovery_adaptive_mode: bool = Field(default=True)

    # ─────────────────────────────────────────────────────────────────────────
    # Coefficients thermiques appris
    # ─────────────────────────────────────────────────────────────────────────
    rcth: float = Field(default=DEFAULT_RCTH, ge=DEFAULT_RCTH_MIN, le=DEFAULT_RCTH_MAX)
    rpth: float = Field(default=DEFAULT_RPTH, ge=DEFAULT_RCTH_MIN, le=DEFAULT_RCTH_MAX)
    rcth_lw: float = Field(default=DEFAULT_RCTH, ge=0)
    rcth_hw: float = Field(default=DEFAULT_RCTH, ge=0)
    rpth_lw: float = Field(default=DEFAULT_RPTH, ge=0)
    rpth_hw: float = Field(default=DEFAULT_RPTH, ge=0)
    relaxation_factor: float = Field(default=DEFAULT_RELAXATION_FACTOR, ge=0.1, le=10.0)

    # ─────────────────────────────────────────────────────────────────────────
    # État de la machine à états
    # ─────────────────────────────────────────────────────────────────────────
    current_state: SmartHRTStateField = Field(default=SmartHRTState.HEATING_ON)
    stop_lag_duration: float = Field(default=0.0, ge=0)

    # Snapshots de référence (températures en °C)
    time_recovery_calc: DateTimeField = Field(default=None)
    time_recovery_start: DateTimeField = Field(default=None)
    time_recovery_end: DateTimeField = Field(default=None)
    temp_recovery_calc: float = Field(default=17.0)  # °C
    temp_recovery_start: float = Field(default=17.0)  # °C
    temp_recovery_end: float = Field(default=17.0)  # °C
    text_recovery_calc: float = Field(default=0.0)  # °C (extérieur)
    text_recovery_start: float = Field(default=0.0)  # °C (extérieur)
    text_recovery_end: float = Field(default=0.0)  # °C (extérieur)

    # Triggers programmés
    recovery_start_hour: DateTimeField = Field(default=None)
    recovery_update_hour: DateTimeField = Field(default=None)
    # Durée estimée de la relance (diagnostic et Snooze)
    recovery_duration_hours: float = Field(default=0.0, ge=0.0)
    # Désactive l'apprentissage RCth (sortie de secours de DETECTING_LAG)
    rcth_learning_disabled: bool = Field(default=False)

    # ─────────────────────────────────────────────────────────────────────────
    # Données météorologiques (températures en °C)
    # ─────────────────────────────────────────────────────────────────────────────
    interior_temp: float | None = Field(
        default=None
    )  # °C (converti depuis Fahrenheit si nécessaire)
    exterior_temp: float | None = Field(
        default=None
    )  # °C (converti depuis Fahrenheit si nécessaire)
    wind_speed: float = Field(default=0.0, ge=0)  # m/s
    windchill: float | None = Field(default=None)  # °C
    wind_speed_avg: float = Field(default=0.0, ge=0)  # m/s
    wind_speed_forecast_avg: float = Field(default=0.0, ge=0)  # km/h
    temperature_forecast_avg: float = Field(default=0.0)  # °C
    wind_speed_history: DequeFloat = Field(default_factory=lambda: deque(maxlen=50))

    # ─────────────────────────────────────────────────────────────────────────
    # Données de diagnostic (lecture calculée)
    # ─────────────────────────────────────────────────────────────────────────
    rcth_fast: float = Field(default=0.0)
    rcth_calculated: float = Field(default=0.0)
    rpth_calculated: float = Field(default=0.0)
    last_rcth_error: float = Field(default=0.0)
    last_rpth_error: float = Field(default=0.0)

    # ─────────────────────────────────────────────────────────────────────────
    # Flags calculés depuis current_state (lecture seule)
    # ─────────────────────────────────────────────────────────────────────────
    @property
    def recovery_calc_mode(self) -> bool:
        """True si en état MONITORING (calculs de refroidissement actifs)."""
        return self.current_state == SmartHRTState.MONITORING

    @property
    def rp_calc_mode(self) -> bool:
        """True si en état HEATING_PROCESS (calculs de relance actifs)."""
        return self.current_state == SmartHRTState.HEATING_PROCESS

    @property
    def temp_lag_detection_active(self) -> bool:
        """True si en état DETECTING_LAG (surveillance de baisse température)."""
        return self.current_state == SmartHRTState.DETECTING_LAG

    # ─────────────────────────────────────────────────────────────────────────
    # Validation et normalisation
    # ─────────────────────────────────────────────────────────────────────────
    @field_validator("rcth", "rpth", "rcth_lw", "rcth_hw", "rpth_lw", "rpth_hw")
    @classmethod
    def clamp_coefficients(cls, v: float) -> float:
        """S'assure que les coefficients sont dans les limites."""
        if v < DEFAULT_RCTH_MIN:
            return DEFAULT_RCTH_MIN
        if v > DEFAULT_RCTH_MAX:
            return DEFAULT_RCTH_MAX
        return v

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Valide que le nom n'est pas vide."""
        v = v.strip()
        if not v:
            return "SmartHRT"
        return v

    # ─────────────────────────────────────────────────────────────────────────
    # Méthodes de sérialisation
    # ─────────────────────────────────────────────────────────────────────────

    # Champs à persister (subset du modèle) - ClassVar pour éviter interférence Pydantic
    _PERSISTENT_FIELDS: ClassVar[set[str]] = {
        # Coefficients thermiques
        "rcth",
        "rpth",
        "rcth_lw",
        "rcth_hw",
        "rpth_lw",
        "rpth_hw",
        "last_rcth_error",
        "last_rpth_error",
        # État machine
        "current_state",
        "stop_lag_duration",
        # Modes utilisateur
        "smartheating_mode",
        "recovery_adaptive_mode",
        # Réglages utilisateur (consigne et heures configurées)
        "tsp",
        "target_hour",
        "recoverycalc_hour",
        # Snapshots de session
        "time_recovery_calc",
        "temp_recovery_calc",
        "text_recovery_calc",
        # Triggers programmés
        "recovery_start_hour",
        # Prévisions météo (pour continuité après restart)
        "temperature_forecast_avg",
        "wind_speed_forecast_avg",
        # Historique vent
        "wind_speed_history",
    }

    def as_dict(self) -> dict[str, Any]:
        """Sérialise les champs persistés en dictionnaire JSON-compatible."""
        return self.model_dump(
            mode="json",
            include=self._PERSISTENT_FIELDS,
        )

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        defaults: SmartHRTData | None = None,
    ) -> SmartHRTData:
        """Désérialise un dictionnaire en SmartHRTData.

        Args:
            data: Dictionnaire JSON chargé depuis le stockage
            defaults: Instance fournissant les valeurs des champs manquants
        """
        if defaults is None:
            defaults = cls()

        # Les données chargées complètent/écrasent les valeurs par défaut
        merged = defaults.model_dump()
        merged.update(data)

        return cls.model_validate(merged)

    @classmethod
    def migrate_legacy_format(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Convertit l'ancien format de stockage (valeurs encapsulées avec __type__) en format natif."""
        migrated: dict[str, Any] = {}

        for key, value in data.items():
            if value is None:
                migrated[key] = None
                continue

            # Ancien format : {"__type__": ..., "value": ...}
            if isinstance(value, dict) and "__type__" in value:
                type_name = value.get("__type__")
                inner_value = value.get("value")

                if type_name == "datetime":
                    migrated[key] = inner_value  # String ISO
                elif type_name == "time":
                    migrated[key] = inner_value  # String ISO
                elif type_name == "enum":
                    migrated[key] = inner_value  # String value
                elif type_name == "deque":
                    migrated[key] = value.get("value", [])  # List
                else:
                    migrated[key] = inner_value
            else:
                # Valeurs déjà au format natif
                migrated[key] = value

        return migrated

    def update(self, **kwargs: Any) -> Self:
        """Met à jour les attributs en place (validés à l'assignation) et retourne self."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        return self

    # ─────────────────────────────────────────────────────────────────────────
    # Alias de compatibilité (accès historique par sous-structure)
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def config(self) -> SmartHRTData:
        """Alias de compatibilité : retourne self."""
        return self

    @property
    def coefficients(self) -> SmartHRTData:
        """Alias de compatibilité : retourne self."""
        return self

    @property
    def state(self) -> SmartHRTData:
        """Alias de compatibilité : retourne self."""
        return self

    @property
    def weather(self) -> SmartHRTData:
        """Alias de compatibilité : retourne self."""
        return self

    @property
    def diagnostic(self) -> SmartHRTData:
        """Alias de compatibilité : retourne self."""
        return self
