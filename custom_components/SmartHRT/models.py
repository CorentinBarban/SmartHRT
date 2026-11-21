"""Modèles Pydantic de validation des données persistées et du config flow."""

import logging
from collections import deque
from datetime import datetime
from datetime import time as dt_time
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from .const import (
    DEFAULT_RCTH,
    DEFAULT_RCTH_MAX,
    DEFAULT_RCTH_MIN,
    DEFAULT_RPTH,
    DEFAULT_TSP,
    DEFAULT_TSP_MAX,
    DEFAULT_TSP_MIN,
)

_LOGGER = logging.getLogger(__name__)


class PersistedDataModel(BaseModel):
    """Valide les types et bornes des données chargées depuis le stockage."""

    # Coefficients thermiques
    rcth: float = Field(default=DEFAULT_RCTH, ge=DEFAULT_RCTH_MIN, le=DEFAULT_RCTH_MAX)
    rpth: float = Field(default=DEFAULT_RPTH, ge=DEFAULT_RCTH_MIN, le=DEFAULT_RCTH_MAX)
    rcth_lw: float = Field(default=DEFAULT_RCTH, ge=0)
    rcth_hw: float = Field(default=DEFAULT_RCTH, ge=0)
    rpth_lw: float = Field(default=DEFAULT_RPTH, ge=0)
    rpth_hw: float = Field(default=DEFAULT_RPTH, ge=0)
    last_rcth_error: float = Field(default=0.0)
    last_rpth_error: float = Field(default=0.0)

    # État machine (string, sera converti en SmartHRTState par le coordinator)
    current_state: str = Field(default="heating_on")

    # Durée du lag de température
    stop_lag_duration: float = Field(default=0.0, ge=0)

    # Heures configurées (optionnelles)
    target_hour: dt_time | None = Field(default=None)
    recoverycalc_hour: dt_time | None = Field(default=None)

    # Snapshots de session
    time_recovery_calc: datetime | None = Field(default=None)
    temp_recovery_calc: float = Field(default=17.0)
    text_recovery_calc: float = Field(default=0.0)

    # Trigger programmé
    recovery_start_hour: datetime | None = Field(default=None)

    # Prévisions météo
    temperature_forecast_avg: float = Field(default=0.0)
    wind_speed_forecast_avg: float = Field(default=0.0, ge=0)

    # Historique vent (liste, sera convertie en deque)
    wind_speed_history: list[float] = Field(default_factory=list)

    model_config = {
        "extra": "ignore",  # Ignore les champs inconnus (migration)
        "validate_assignment": True,  # Valide aussi lors des assignations
    }

    @field_validator("current_state")
    @classmethod
    def validate_state(cls, v: str) -> str:
        """Valide que l'état est connu, sinon fallback sur heating_on."""
        valid_states = {
            "heating_on",
            "detecting_lag",
            "monitoring",
            "recovery",
            "heating_process",
        }
        if v not in valid_states:
            _LOGGER.warning("État invalide '%s', utilisation de 'heating_on'", v)
            return "heating_on"
        return v

    @field_validator("rcth", "rpth", "rcth_lw", "rcth_hw", "rpth_lw", "rpth_hw")
    @classmethod
    def clamp_coefficients(cls, v: float) -> float:
        """S'assure que les coefficients sont dans les limites."""
        if v < DEFAULT_RCTH_MIN:
            return DEFAULT_RCTH_MIN
        if v > DEFAULT_RCTH_MAX:
            return DEFAULT_RCTH_MAX
        return v

    @field_validator("wind_speed_history", mode="before")
    @classmethod
    def ensure_list(cls, v: Any) -> list[float]:
        """Convertit en liste si nécessaire."""
        if v is None:
            return []
        if isinstance(v, (list, tuple)):
            return [float(x) for x in v if x is not None]
        if isinstance(v, deque):
            return list(v)
        return []


class ConfigFlowDataModel(BaseModel):
    """Valide les entrées utilisateur du config flow."""

    name: str = Field(min_length=1, max_length=100)
    target_hour: str  # Format "HH:MM:SS"
    recoverycalc_hour: str = Field(default="23:00:00")
    sensor_interior_temperature: str  # Entity ID
    weather_entity: str  # Entity ID
    tsp: float = Field(default=DEFAULT_TSP, ge=DEFAULT_TSP_MIN, le=DEFAULT_TSP_MAX)

    model_config = {
        "extra": "ignore",
    }

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
    def validate_time_sequence(self) -> "ConfigFlowDataModel":
        """Valide que recoverycalc_hour précède target_hour (passage à minuit)."""
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
        """Convertit target_hour en objet time."""
        parts = self.target_hour.split(":")
        return dt_time(
            int(parts[0]),
            int(parts[1]) if len(parts) > 1 else 0,
            int(parts[2]) if len(parts) > 2 else 0,
        )

    @property
    def recoverycalc_hour_as_time(self) -> dt_time:
        """Convertit recoverycalc_hour en objet time."""
        parts = self.recoverycalc_hour.split(":")
        return dt_time(
            int(parts[0]),
            int(parts[1]) if len(parts) > 1 else 0,
            int(parts[2]) if len(parts) > 2 else 0,
        )


def validate_persisted_data(data: dict[str, Any]) -> dict[str, Any]:
    """Valide et normalise les données persistées ; retourne les défauts si invalides (ne lève pas)."""
    try:
        model = PersistedDataModel.model_validate(data)
        return model.model_dump()
    except Exception as e:
        _LOGGER.warning("Erreur de validation des données persistées: %s", e)
        return PersistedDataModel().model_dump()


def validate_config_flow_data(
    data: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, str]]:
    """Valide les données du config flow.

    Returns:
        Tuple (données validées ou None, erreurs {champ: code_erreur} pour l'UI).
    """
    errors: dict[str, str] = {}

    try:
        model = ConfigFlowDataModel.model_validate(data)
        return model.model_dump(), errors
    except Exception as e:
        # Mappe le message d'erreur Pydantic vers un code d'erreur UI
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
