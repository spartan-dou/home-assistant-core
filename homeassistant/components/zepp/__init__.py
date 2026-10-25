"""The Zepp OS integration: Home Assistant on an Amazfit watch."""

from functools import partial

from aiohttp.hdrs import METH_POST

from homeassistant.components import webhook
from homeassistant.const import CONF_WEBHOOK_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, ZeppConfigEntry
from .handler import async_webhook_handler


async def async_setup_entry(hass: HomeAssistant, entry: ZeppConfigEntry) -> bool:
    """Set up a watch: its device, and the webhook its phone calls."""
    entry.runtime_data = (
        dr.async_get(hass)
        .async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, entry.entry_id)},
            manufacturer="Zepp Health",
            name=entry.title,
        )
        .id
    )
    webhook_id = entry.data[CONF_WEBHOOK_ID]
    webhook.async_register(
        hass,
        DOMAIN,
        entry.title,
        webhook_id,
        async_webhook_handler(entry),
        allowed_methods=[METH_POST],
    )
    entry.async_on_unload(partial(webhook.async_unregister, hass, webhook_id))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ZeppConfigEntry) -> bool:
    """Unload a watch; its webhook goes with it."""
    return True
