"""Constants for the Zepp OS integration."""

from homeassistant.config_entries import ConfigEntry

DOMAIN = "zepp"

# The runtime data of a watch is the id of its device.
type ZeppConfigEntry = ConfigEntry[str]

CONF_AREAS = "areas"
CONF_FAVORITES = "favorites"
CONF_LABEL = "label"
CONF_PIPELINE = "pipeline"

# A base64 recording of about a minute: the watch stops well before.
MAX_AUDIO_LENGTH = 400_000
