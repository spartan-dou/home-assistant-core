"""Constants for the ImmichFrame integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "immichframe"

CONF_SENSORS: Final = "sensors"

UPDATE_INTERVAL: Final = timedelta(seconds=30)
# The frame blanks values it has not heard of for a while: pushing on an interval
# as well as on change keeps them after a restart of either side.
PUSH_INTERVAL: Final = timedelta(seconds=60)

SERVICE_SHOW_NOTIFICATION: Final = "show_notification"
ATTR_LINK: Final = "link"
ATTR_DURATION: Final = "duration"
ATTR_REPLACE: Final = "replace"
