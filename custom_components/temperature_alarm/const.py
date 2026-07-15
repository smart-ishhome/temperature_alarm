"""Constants for the Temperature Alarm integration."""

DOMAIN = "temperature_alarm"

# Configuration keys
CONF_SOURCE_ENTITY = "source_entity"
CONF_MODE = "mode"

# Flow-only key for the "show all sensors" toggle on the source-selection
# step; never persisted into entry data
CONF_SHOW_ALL_SENSORS = "show_all_sensors"
CONF_MIN_TEMP = "min_temp"
CONF_MAX_TEMP = "max_temp"

# Monitoring modes - defined in evaluator.py (the domain core), re-exported here
from .evaluator import MODE_MAX_ONLY, MODE_MIN_MAX, MODE_MIN_ONLY  # noqa: F401

MODES = [MODE_MIN_ONLY, MODE_MAX_ONLY, MODE_MIN_MAX]

# Alarm Device Class - how HA announces the Alarm's on-state; values are
# BinarySensorDeviceClass enum values, kept as plain strings so const.py
# stays free of HA component imports
CONF_DEVICE_CLASS = "device_class"

# Default values
DEFAULT_MIN_TEMP = 50.0
DEFAULT_MAX_TEMP = 90.0
DEFAULT_MODE = MODE_MIN_MAX
DEFAULT_DEVICE_CLASS = "problem"

# Number entity constraints
MIN_TEMP_LIMIT = -50.0
MAX_TEMP_LIMIT = 500.0
TEMP_STEP = 0.5

# Trigger delay configuration
CONF_DELAY_ENABLED = "delay_enabled"
CONF_DELAY_TIME = "delay_time"
CONF_DELAY_UPDATES = "delay_updates"
DEFAULT_DELAY_TIME = 300  # seconds
DEFAULT_DELAY_UPDATES = 3  # update count

# Optional entity creation
CONF_CREATE_MIN_ENTITY = "create_min_entity"
CONF_CREATE_MAX_ENTITY = "create_max_entity"

# Platforms (setup order is enforced in __init__.async_setup_entry:
# number first, so Threshold Entities exist before the Alarm subscribes)
PLATFORMS = ["number", "binary_sensor"]
