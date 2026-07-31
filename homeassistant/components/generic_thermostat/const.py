"""Constants for the Generic Thermostat helper."""

from datetime import timedelta

from homeassistant.components.climate import (
    PRESET_ACTIVITY,
    PRESET_AWAY,
    PRESET_COMFORT,
    PRESET_ECO,
    PRESET_HOME,
    PRESET_SLEEP,
)
from homeassistant.const import Platform

DOMAIN = "generic_thermostat"

PLATFORMS = [Platform.CLIMATE]

CONF_AC_MODE = "ac_mode"
CONF_COLD_TOLERANCE = "cold_tolerance"
CONF_HEATER = "heater"
CONF_HOT_TOLERANCE = "hot_tolerance"
CONF_MAX_TEMP = "max_temp"
CONF_MIN_DUR = "min_cycle_duration"
CONF_MAX_DUR = "max_cycle_duration"
CONF_DUR_COOLDOWN = "cycle_cooldown"
CONF_MIN_TEMP = "min_temp"
CONF_PRESETS = {
    p: f"{p}_temp"
    for p in (
        PRESET_AWAY,
        PRESET_COMFORT,
        PRESET_ECO,
        PRESET_HOME,
        PRESET_SLEEP,
        PRESET_ACTIVITY,
    )
}
CONF_SENSOR = "target_sensor"
CONF_KEEP_ALIVE = "keep_alive"
CONF_OPENINGS = "openings"
CONF_OPENINGS_TIMEOUT = "openings_timeout"
DEFAULT_TOLERANCE = 0.3
# Resume heating after this long even if the opening is still open, so a window
# left ajar cannot switch the heating off indefinitely.
DEFAULT_OPENINGS_TIMEOUT = timedelta(minutes=30)

ATTR_TARGET_TEMP_PRESET_NONE = "target_temp_preset_none"
ATTR_OPENINGS_SAVED_HVAC_MODE = "openings_saved_hvac_mode"
