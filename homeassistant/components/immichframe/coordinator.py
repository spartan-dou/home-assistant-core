"""Coordinator for the ImmichFrame integration."""

from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ImmichFrameClient, ImmichFrameConnectionError
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

type ImmichFrameConfigEntry = ConfigEntry[ImmichFrameData]


@dataclass
class ImmichFrameData:
    """Runtime data of a frame."""

    client: ImmichFrameClient
    coordinator: ImmichFrameCoordinator


class ImmichFrameCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Polls what the frame shows, mostly to follow the memories switch."""

    config_entry: ImmichFrameConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ImmichFrameConfigEntry,
        client: ImmichFrameClient,
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

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            return await self.client.get_overlay()
        except ImmichFrameConnectionError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="cannot_connect"
            ) from err
