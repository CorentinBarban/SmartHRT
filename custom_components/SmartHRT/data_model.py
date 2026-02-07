"""Modèle de données unifié SmartHRT (ADR-047: Single Source of Truth).

Ce module fusionne l'ancien SmartHRTData (dataclass custom) et
PersistedDataModel (Pydantic) en un seul modèle Pydantic v2.

Avantages:
- Une seule source de vérité pour types, contraintes et valeurs par défaut
- Validation automatique à l'assignation (validate_assignment=True)
- Sérialisation native via model_dump()/model_validate()
- Suppression de serialization.py et des conversions manuelles

Le module serialization.py est supprimé, remplacé par les sérialiseurs
Pydantic intégrés.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, time as dt_time
from typing import Annotated, Any, ClassVar, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    BeforeValidator,
    field_validator,
    model_validator,
)

from .const import (
    DEFAULT_RCTH,
    DEFAULT_RPTH,
    DEFAULT_RCTH_MIN,
    DEFAULT_RCTH_MAX,
    DEFAULT_RELAXATION_FACTOR,
    DEFAULT_TSP,
)
from .core import SmartHRTState


# ─────────────────────────────────────────────────────────────────────────────
# Types personnalisés avec sérialiseurs Pydantic (remplace JSONEncoder)
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
# Modèle unifié SmartHRTData (ADR-047)
# ─────────────────────────────────────────────────────────────────────────────


class SmartHRTData(BaseModel):
    """Modèle de données unifié pour SmartHRT (ADR-047: Single Source of Truth).

    Ce modèle Pydantic remplace:
    - L'ancienne classe SmartHRTData (custom avec sous-structures)
    - PersistedDataModel (validation Pydantic séparée)
    - JSONEncoder/serialization.py (sérialisation custom)

    La validation est effectuée:
    - À l'instanciation
    - À chaque assignation (validate_assignment=True)
    - Au chargement depuis le stockage (model_validate)

    La sérialisation/désérialisation est native via:
    - model_dump(mode="json") pour sauvegarder
    - model_validate(data) pour restaurer
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
    # Coefficients thermiques appris (ADR-006, ADR-007)
    # ─────────────────────────────────────────────────────────────────────────
    rcth: float = Field(default=DEFAULT_RCTH, ge=DEFAULT_RCTH_MIN, le=DEFAULT_RCTH_MAX)
    rpth: float = Field(default=DEFAULT_RPTH, ge=DEFAULT_RCTH_MIN, le=DEFAULT_RCTH_MAX)
    rcth_lw: float = Field(default=DEFAULT_RCTH, ge=0)
    rcth_hw: float = Field(default=DEFAULT_RCTH, ge=0)
    rpth_lw: float = Field(default=DEFAULT_RPTH, ge=0)
    rpth_hw: float = Field(default=DEFAULT_RPTH, ge=0)
    relaxation_factor: float = Field(default=DEFAULT_RELAXATION_FACTOR, ge=0.1, le=10.0)

    # ─────────────────────────────────────────────────────────────────────────
    # État de la machine à états (ADR-003, ADR-028, ADR-040)
    # ─────────────────────────────────────────────────────────────────────────
    current_state: SmartHRTStateField = Field(default=SmartHRTState.HEATING_ON)
    stop_lag_duration: float = Field(default=0.0, ge=0)

    # Snapshots de référence
    time_recovery_calc: DateTimeField = Field(default=None)
    time_recovery_start: DateTimeField = Field(default=None)
    time_recovery_end: DateTimeField = Field(default=None)
    temp_recovery_calc: float = Field(default=17.0)
    temp_recovery_start: float = Field(default=17.0)
    temp_recovery_end: float = Field(default=17.0)
    text_recovery_calc: float = Field(default=0.0)
    text_recovery_start: float = Field(default=0.0)
    text_recovery_end: float = Field(default=0.0)

    # Triggers programmés
    recovery_start_hour: DateTimeField = Field(default=None)
    recovery_update_hour: DateTimeField = Field(default=None)

    # ─────────────────────────────────────────────────────────────────────────
    # Données météorologiques (ADR-038)
    # ─────────────────────────────────────────────────────────────────────────
    interior_temp: float | None = Field(default=None)
    exterior_temp: float | None = Field(default=None)
    wind_speed: float = Field(default=0.0, ge=0)  # m/s
    windchill: float | None = Field(default=None)
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
    # ADR-040: Flags calculés depuis current_state (propriétés en lecture seule)
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
    # ADR-047: Méthodes de sérialisation (remplace as_dict/from_dict custom)
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
        # Heures configurées
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
        """Sérialise les données persistantes en dictionnaire JSON-compatible.

        Utilise model_dump native de Pydantic avec filtrage des champs.

        Returns:
            Dictionnaire avec toutes les données à persister.
        """
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

        Utilise model_validate native de Pydantic.

        Args:
            data: Dictionnaire JSON chargé depuis le stockage
            defaults: Instance par défaut pour les champs manquants

        Returns:
            Nouvelle instance SmartHRTData avec données restaurées.
        """
        if defaults is None:
            defaults = cls()

        # Merge defaults avec les données chargées
        merged = defaults.model_dump()
        merged.update(data)

        # Validation et création
        return cls.model_validate(merged)

    @classmethod
    def migrate_legacy_format(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Migre les données de l'ancien format (JSONEncoder avec __type__).

        Détecte l'ancien format et convertit au format Pydantic natif.

        Args:
            data: Données au format legacy (avec __type__)

        Returns:
            Données au nouveau format Pydantic
        """
        migrated: dict[str, Any] = {}

        for key, value in data.items():
            if value is None:
                migrated[key] = None
                continue

            # Ancien format avec __type__
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
                # Valeurs primitives ou nouveau format - pas de changement
                migrated[key] = value

        return migrated

    def update(self, **kwargs: Any) -> Self:
        """Met à jour les attributs en place et retourne self.

        Permet une syntaxe fluide: self.data.update(tsp=20, rcth=100)

        Note: La validation est effectuée grâce à validate_assignment=True.
        """
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        return self

    # ─────────────────────────────────────────────────────────────────────────
    # Compatibilité avec l'ancienne API (accès aux sous-structures)
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def config(self) -> SmartHRTData:
        """Alias pour compatibilité avec l'ancien code utilisant self.data.config.

        Retourne self car le modèle est maintenant unifié.
        """
        return self

    @property
    def coefficients(self) -> SmartHRTData:
        """Alias pour compatibilité avec l'ancien code utilisant self.data.coefficients."""
        return self

    @property
    def state(self) -> SmartHRTData:
        """Alias pour compatibilité avec l'ancien code utilisant self.data.state."""
        return self

    @property
    def weather(self) -> SmartHRTData:
        """Alias pour compatibilité avec l'ancien code utilisant self.data.weather."""
        return self

    @property
    def diagnostic(self) -> SmartHRTData:
        """Alias pour compatibilité avec l'ancien code utilisant self.data.diagnostic."""
        return self


# ─────────────────────────────────────────────────────────────────────────────
# ConfigFlowDataModel (validation entrées utilisateur - migré depuis models.py)
# ─────────────────────────────────────────────────────────────────────────────


class ConfigFlowDataModel(BaseModel):
    """Modèle Pydantic pour les données du config flow (ADR-032).

    Valide les entrées utilisateur lors de la configuration.
    Séparé de SmartHRTData car les formats diffèrent:
    - ConfigFlow: heures en string "HH:MM:SS", entity_id en string
    - SmartHRTData: heures en dt_time, données métier validées
    """

    name: str = Field(min_length=1, max_length=100)
    target_hour: str  # Format "HH:MM:SS"
    recoverycalc_hour: str = Field(default="23:00:00")
    sensor_interior_temperature: str  # Entity ID
    weather_entity: str  # Entity ID
    tsp: float = Field(default=DEFAULT_TSP, ge=13.0, le=26.0)

    model_config = ConfigDict(extra="ignore")

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Valide que le nom n'est pas vide."""
        v = v.strip()
        if not v:
            raise ValueError("Le nom ne peut pas être vide")
        return v

    @field_validator("target_hour", "recoverycalc_hour")
    @classmethod
    def validate_time_format(cls, v: str) -> str:
        """Valide le format de l'heure."""
        try:
            parts = v.split(":")
            hour = int(parts[0])
            minute = int(parts[1]) if len(parts) > 1 else 0
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Heure invalide")
        except (ValueError, IndexError) as e:
            raise ValueError(f"Format d'heure invalide: {v}") from e
        return v

    @model_validator(mode="after")
    def validate_time_sequence(self) -> Self:
        """Valide que recoverycalc_hour précède target_hour (passage à minuit).

        La logique: recoverycalc (23:00) doit être le soir, target (06:00) le matin.
        Si recoverycalc < target (même journée), c'est une erreur.
        """
        try:
            rc_parts = self.recoverycalc_hour.split(":")
            tg_parts = self.target_hour.split(":")
            rc_minutes = int(rc_parts[0]) * 60 + int(
                rc_parts[1] if len(rc_parts) > 1 else 0
            )
            tg_minutes = int(tg_parts[0]) * 60 + int(
                tg_parts[1] if len(tg_parts) > 1 else 0
            )

            # Cas invalide: recoverycalc (ex: 05:00) < target (06:00) sur même journée
            # Cas valide: recoverycalc (23:00) > target (06:00) implique passage à minuit
            # Ou target très tôt (avant midi) est OK même si recoverycalc proche
            if rc_minutes < tg_minutes and tg_minutes >= 12 * 60:
                raise ValueError(
                    "L'heure de coupure doit précéder l'heure cible (passage à minuit)"
                )
        except (ValueError, IndexError):
            pass  # Les erreurs de parsing sont gérées par validate_time_format
        return self

    @property
    def target_hour_as_time(self) -> dt_time:
        """Convertit target_hour en objet time (ADR-045)."""
        parts = self.target_hour.split(":")
        return dt_time(
            int(parts[0]),
            int(parts[1]) if len(parts) > 1 else 0,
            int(parts[2]) if len(parts) > 2 else 0,
        )

    @property
    def recoverycalc_hour_as_time(self) -> dt_time:
        """Convertit recoverycalc_hour en objet time (ADR-045)."""
        parts = self.recoverycalc_hour.split(":")
        return dt_time(
            int(parts[0]),
            int(parts[1]) if len(parts) > 1 else 0,
            int(parts[2]) if len(parts) > 2 else 0,
        )


def validate_config_flow_data(
    data: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, str]]:
    """Valide les données du config flow.

    Args:
        data: Données saisies par l'utilisateur

    Returns:
        Tuple (données_validées, erreurs)
        - données_validées: None si erreurs, sinon dict validé
        - erreurs: dict {champ: code_erreur} pour affichage UI
    """
    import logging

    _LOGGER = logging.getLogger(__name__)
    errors: dict[str, str] = {}

    try:
        model = ConfigFlowDataModel.model_validate(data)
        return model.model_dump(), errors
    except Exception as e:
        # Parser les erreurs Pydantic pour les mapper aux champs
        error_str = str(e)
        if "tsp" in error_str.lower():
            errors["tsp"] = "tsp_out_of_range"
        elif "name" in error_str.lower():
            errors["name"] = "invalid_name"
        elif "heure" in error_str.lower() or "time" in error_str.lower():
            errors["base"] = "invalid_time_sequence"
        else:
            errors["base"] = "unknown_error"

        _LOGGER.debug("Erreur de validation config flow: %s", e)
        return None, errors
