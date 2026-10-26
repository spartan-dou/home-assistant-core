"""Constants for the Zepp OS integration."""

from homeassistant.config_entries import ConfigEntry

DOMAIN = "zepp"

URL = "/api/zepp"

# The runtime data of a watch is the id of its device.
type ZeppConfigEntry = ConfigEntry[str]

CONF_AREAS = "areas"
CONF_FAVORITES = "favorites"
CONF_PIPELINE = "pipeline"

# What the phone may choose at once: well beyond what a watch page can show.
MAX_SELECTION = 200

# A base64 recording of about a minute: the watch stops well before.
MAX_AUDIO_LENGTH = 400_000
