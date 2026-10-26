"""The Zepp OS integration: Home Assistant on an Amazfit watch."""

from homeassistant.const import CONF_API_KEY, CONF_WEBHOOK_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, ZeppConfigEntry
from .handler import ZeppView

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the route the phones call, shared by all the watches."""
    hass.http.register_view(ZeppView())
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ZeppConfigEntry) -> bool:
    """Set up a watch: its device. The route answers it once the entry is loaded."""
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
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ZeppConfigEntry) -> bool:
    """Unload a watch; the route stops answering its key."""
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ZeppConfigEntry) -> bool:
    """Keep the secret of a first version watch: its webhook id becomes its key."""
    if entry.version == 1:
        hass.config_entries.async_update_entry(
            entry, data={CONF_API_KEY: entry.data[CONF_WEBHOOK_ID]}, version=2
        )
    return True
