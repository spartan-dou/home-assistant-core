"""The ImmichFrame integration: a photo frame driven by Home Assistant."""

from homeassistant.const import CONF_API_KEY, CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import ImmichFrameClient
from .const import DOMAIN
from .coordinator import ImmichFrameConfigEntry, ImmichFrameCoordinator, ImmichFrameData
from .pusher import SensorPusher
from .services import async_setup_services

PLATFORMS: list[Platform] = [Platform.NOTIFY, Platform.SWITCH]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the actions."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ImmichFrameConfigEntry) -> bool:
    """Set up a frame."""
    client = ImmichFrameClient(
        async_get_clientsession(hass),
        entry.data[CONF_URL],
        entry.data.get(CONF_API_KEY),
    )
    coordinator = ImmichFrameCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = ImmichFrameData(client, coordinator)

    entry.async_on_unload(SensorPusher(hass, entry).async_start())
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ImmichFrameConfigEntry
) -> bool:
    """Unload a frame."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
