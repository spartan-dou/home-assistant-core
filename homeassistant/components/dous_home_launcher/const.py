"""Constants for the Dou's Home Launcher integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "dous_home_launcher"

CONF_SENSORS: Final = "sensors"

UPDATE_INTERVAL: Final = timedelta(seconds=30)
# The frame forgets values it has not heard of for a while, and only listens while
# it is on screen: pushing on an interval as well as on change brings them back.
PUSH_INTERVAL: Final = timedelta(seconds=60)
# A burst of changes (a thermostat updates several attributes at once) becomes one push.
PUSH_COOLDOWN: Final = 1.0

SERVICE_SHOW_NOTIFICATION: Final = "show_notification"
ATTR_LINK: Final = "link"
ATTR_DURATION: Final = "duration"
ATTR_TAG: Final = "tag"
