"""The Zepp OS integration: Home Assistant on an Amazfit watch."""

from homeassistant.const import CONF_API_KEY, CONF_WEBHOOK_ID, EVENT_HOMEASSISTANT_STOP
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, ZeppConfigEntry
from .handler import ZeppPairStatusView, ZeppPairView, ZeppView
from .pairing import DATA_PAIRINGS, Pairings

# `zepp:` in the configuration opens the pairing route before any watch is added.
CONFIG_SCHEMA = cv.empty_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the routes the phones call, shared by all the watches."""
    pairings = hass.data[DATA_PAIRINGS] = Pairings(hass)

    @callback
    def _async_stop(_event: Event) -> None:
        pairings.async_cancel()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)
    hass.http.register_view(ZeppPairView())
    hass.http.register_view(ZeppPairStatusView())
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
