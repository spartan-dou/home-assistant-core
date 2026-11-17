"""The Dou's Home Launcher integration: its photo frame, driven by Home Assistant."""

from homeassistant.const import CONF_API_KEY, CONF_URL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import LauncherClient
from .const import DOMAIN
from .coordinator import LauncherConfigEntry, LauncherCoordinator, LauncherData
from .pusher import SensorPusher
from .services import async_setup_services

PLATFORMS: list[Platform] = [
    Platform.BUTTON,
    Platform.NOTIFY,
    Platform.NUMBER,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the actions."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: LauncherConfigEntry) -> None:
    """Set up a frame."""
    client = LauncherClient(
        async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_API_KEY]
    )
    coordinator = LauncherCoordinator(hass, entry, client)
    # Not a first refresh, which would fail the setup: the frame only answers while
    # it is on screen, so Home Assistant often starts without it.
    await coordinator.async_refresh()
    entry.runtime_data = LauncherData(client, coordinator)

    entry.async_on_unload(SensorPusher(hass, entry).async_start())
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)


async def async_unload_entry(hass: HomeAssistant, entry: LauncherConfigEntry) -> None:
    """Unload a frame."""
    await hass.config_entries.async_unload_platforms_or_raise(entry, PLATFORMS)
