""" Les constantes pour l'intégration SmartHRT """

from homeassistant.const import Platform

DOMAIN = "smarthrt"
PLATFORMS: list[Platform] = [Platform.SENSOR,
                             Platform.NUMBER, Platform.TIME, Platform.SWITCH]

# Configuration keys
CONF_NAME = "name"
CONF_DEVICE_ID = "device_id"
CONF_TARGET_HOUR = "target_hour"
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
