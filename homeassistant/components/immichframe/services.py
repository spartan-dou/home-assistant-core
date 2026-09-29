"""Actions of the ImmichFrame integration."""

import voluptuous as vol

from homeassistant.components.notify import ATTR_MESSAGE, DOMAIN as NOTIFY_DOMAIN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, service

from .const import (
    ATTR_DURATION,
    ATTR_LINK,
    ATTR_REPLACE,
    DOMAIN,
    SERVICE_SHOW_NOTIFICATION,
)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the actions."""
    service.async_register_platform_entity_service(
        hass,
        DOMAIN,
        SERVICE_SHOW_NOTIFICATION,
        entity_domain=NOTIFY_DOMAIN,
        schema={
            # An empty message clears the notification shown.
            vol.Required(ATTR_MESSAGE): cv.string,
            vol.Optional(ATTR_LINK): cv.string,
            vol.Optional(ATTR_DURATION): vol.All(vol.Coerce(float), vol.Range(min=0)),
            vol.Optional(ATTR_REPLACE, default=True): cv.boolean,
        },
        func="async_show_notification",
    )
