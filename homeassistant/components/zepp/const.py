"""Constants for the Zepp OS integration."""

from homeassistant.config_entries import ConfigEntry

DOMAIN = "zepp"

URL = "/api/zepp"
PAIR_URL = f"{URL}/pair"
PAIR_STATUS_URL = f"{URL}/pair/status"

# The runtime data of a watch is the id of its device.
type ZeppConfigEntry = ConfigEntry[str]

CONF_AREAS = "areas"
CONF_FAVORITES = "favorites"
CONF_PIPELINE = "pipeline"

# What the phone may choose at once: well beyond what a watch page can show.
MAX_SELECTION = 200

# A base64 recording of about a minute: the watch stops well before.
MAX_AUDIO_LENGTH = 400_000

# A watch waits this long, in seconds, for its code to be entered in Home Assistant.
PAIRING_TIMEOUT = 300
# The pairing route is open to anyone: at most this many requests per window.
PAIRING_LIMIT = 5
PAIRING_WINDOW = 600
MAX_NAME_LENGTH = 64
