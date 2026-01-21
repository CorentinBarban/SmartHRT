"""Les constantes pour l'intégration SmartHRT"""

from homeassistant.const import Platform

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
CONF_PHONE_ALARM = "phone_alarm_selector"
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

# Wind thresholds (km/h)
WIND_HIGH = 60.0
WIND_LOW = 10.0

# Device info
DEVICE_MANUFACTURER = "SmartHRT"

# Data keys for hass.data[DOMAIN][entry_id]
DATA_COORDINATOR = "coordinator"

# Service names
SERVICE_CALCULATE_RECOVERY_TIME = "calculate_recovery_time"
SERVICE_CALCULATE_RECOVERY_UPDATE_TIME = "calculate_recovery_update_time"
SERVICE_CALCULATE_RCTH_FAST = "calculate_rcth_fast"
SERVICE_ON_HEATING_STOP = "on_heating_stop"
SERVICE_ON_RECOVERY_START = "on_recovery_start"
SERVICE_ON_RECOVERY_END = "on_recovery_end"
SERVICE_RESET_LEARNING = "reset_learning"
SERVICE_TRIGGER_CALCULATION = "trigger_calculation"

# Weather forecast settings
FORECAST_HOURS = 3

# Temperature detection thresholds
TEMP_DECREASE_THRESHOLD = 0.2  # °C drop threshold to detect actual cooling start

# Default recoverycalc hour (23:00)
DEFAULT_RECOVERYCALC_HOUR = "23:00:00"

# Storage keys for RestoreEntity persistence
STORAGE_KEY_RCTH = "rcth"
STORAGE_KEY_RPTH = "rpth"
STORAGE_KEY_RCTH_LW = "rcth_lw"
STORAGE_KEY_RCTH_HW = "rcth_hw"
STORAGE_KEY_RPTH_LW = "rpth_lw"
STORAGE_KEY_RPTH_HW = "rpth_hw"
STORAGE_KEY_LAST_RCTH_ERROR = "last_rcth_error"
STORAGE_KEY_LAST_RPTH_ERROR = "last_rpth_error"
