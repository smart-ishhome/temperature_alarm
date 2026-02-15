"""Constants for the Temperature Alarm integration."""

DOMAIN = "temperature_alarm"

# Configuration keys
CONF_SOURCE_ENTITY = "source_entity"
CONF_MODE = "mode"
CONF_MIN_TEMP = "min_temp"
CONF_MAX_TEMP = "max_temp"

# Monitoring modes
MODE_MIN_ONLY = "min_only"
MODE_MAX_ONLY = "max_only"
MODE_MIN_MAX = "min_max"

MODES = [MODE_MIN_ONLY, MODE_MAX_ONLY, MODE_MIN_MAX]

# Default values
DEFAULT_MIN_TEMP = 68.0
DEFAULT_MAX_TEMP = 80.0
DEFAULT_MODE = MODE_MIN_MAX

# Number entity constraints
MIN_TEMP_LIMIT = -50.0
MAX_TEMP_LIMIT = 150.0
TEMP_STEP = 0.5

# Platforms - number must come before binary_sensor to ensure thresholds exist
PLATFORMS = ["number", "binary_sensor"]
