"""Les constantes pour l'intégration SmartHRT.

ADR implémentées dans ce module:
- ADR-041: PERSISTED_FIELDS supprimé, remplacé par SmartHRTData.as_dict/from_dict
- ADR-051: TimerKey pour la gestion centralisée des timers
"""

from enum import StrEnum

from homeassistant.const import Platform


class TimerKey(StrEnum):
    """Clés des timers gérés par le système (ADR-051).

    Utilisées avec TimerManager pour identifier les timers de manière unique.
    """

    RECOVERYCALC_HOUR = "recoverycalc_hour"
    TARGET_HOUR = "target_hour"
    RECOVERY_START = "recovery_start"
    RECOVERY_UPDATE = "recovery_update"


DOMAIN = "smarthrt"
PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.TIME,
    Platform.SWITCH,
]

# Configuration keys
CONF_NAME = "name"
CONF_DEVICE_ID = "device_id"
CONF_TARGET_HOUR = "target_hour"
CONF_RECOVERYCALC_HOUR = "recoverycalc_hour"
CONF_SENSOR_INTERIOR_TEMP = "sensor_interior_temperature"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_TSP = "tsp"

# Default values
DEFAULT_TSP = 19.0
DEFAULT_TSP_MIN = 13.0
DEFAULT_TSP_MAX = 26.0
DEFAULT_TSP_STEP = 0.1

# Thermal coefficients defaults
DEFAULT_RCTH = 50.0
DEFAULT_RPTH = 50.0
DEFAULT_RCTH_MIN = 0.0
DEFAULT_RCTH_MAX = 19999.0
DEFAULT_RPTH_MIN = 0.0
DEFAULT_RPTH_MAX = 19999.0
DEFAULT_RELAXATION_FACTOR = 2.0

# ADR-007: Compensation météo - seuils de vent pour interpolation
# WIND_LOW: vent faible (utilise rcth_lw), WIND_HIGH: vent fort (utilise rcth_hw)
WIND_HIGH = 60.0
WIND_LOW = 10.0

# Device info
DEVICE_MANUFACTURER = "SmartHRT"

# Data keys for hass.data[DOMAIN][entry_id]
DATA_COORDINATOR = "coordinator"

# ADR-043: Services essentiels uniquement
# Services simplifiés
SERVICE_START_HEATING_CYCLE = "start_heating_cycle"
SERVICE_STOP_HEATING = "stop_heating"
SERVICE_START_RECOVERY = "start_recovery"
SERVICE_END_RECOVERY = "end_recovery"
SERVICE_GET_STATE = "get_state"

# Services utilitaires
SERVICE_RESET_LEARNING = "reset_learning"
SERVICE_TRIGGER_CALCULATION = "trigger_calculation"

# Weather forecast settings
FORECAST_HOURS = 3

# ADR-008: Validation arrêt par détection lag
# Seuil de baisse de température pour confirmer l'arrêt réel du chauffage
TEMP_DECREASE_THRESHOLD = 0.2  # °C

# ADR-053: Optimisation inter-saison (Snooze) et sécurisation apprentissage
# Seuil minimum d'activation (en heures): si durée estimée <= seuil, pas de relance
MIN_DURATION_THRESHOLD_HOURS = 0.25  # 15 minutes
# Seuil minimum d'apprentissage (en heures): durée réelle de chauffe requise pour calculer RPth
MIN_LEARNING_DURATION_HOURS = 0.25  # 15 minutes

# Default recoverycalc hour (23:00)
DEFAULT_RECOVERYCALC_HOUR = "23:00:00"

# ADR-041: PERSISTED_FIELDS supprimé
# La sérialisation est maintenant centralisée dans SmartHRTData.as_dict/from_dict
# Voir coordinator.py pour _PERSISTENT_FIELDS et la logique de migration
