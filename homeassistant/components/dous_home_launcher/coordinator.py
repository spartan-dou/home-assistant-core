"""Coordinator for the Dou's Home Launcher integration."""

from dataclasses import dataclass
import logging
from typing import Any, override

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import LauncherClient, LauncherConnectionError
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

type LauncherConfigEntry = ConfigEntry[LauncherData]


@dataclass
class LauncherData:
    """Runtime data of a frame."""

    client: LauncherClient
    coordinator: LauncherCoordinator


class LauncherCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls the frame: unreachable means it is not on screen, which is usual."""

    config_entry: LauncherConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: LauncherConfigEntry,
        client: LauncherClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client

    @override
    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.client.get_state()
        except LauncherConnectionError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="cannot_connect"
            ) from err
