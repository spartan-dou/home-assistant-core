"""Memories switch of the ImmichFrame integration."""

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import ImmichFrameConnectionError
from .const import DOMAIN
from .coordinator import ImmichFrameConfigEntry, ImmichFrameCoordinator
from .entity import ImmichFrameEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ImmichFrameConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the memories switch."""
    async_add_entities([ImmichFrameMemoriesSwitch(entry.runtime_data.coordinator)])


class ImmichFrameMemoriesSwitch(ImmichFrameEntity, SwitchEntity):
    """Shows or hides memories; the frame keeps the state across restarts."""

    _attr_translation_key = "memories"

    def __init__(self, coordinator: ImmichFrameCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, "memories")

    @property
    def is_on(self) -> bool:
        """Return whether memories are shown."""
        return bool(self.coordinator.data.get("memoriesEnabled"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Show memories."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Hide memories."""
        await self._async_set(False)

    async def _async_set(self, enabled: bool) -> None:
        try:
            await self.coordinator.client.set_memories(enabled)
        except ImmichFrameConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="cannot_connect"
            ) from err
        self.coordinator.async_set_updated_data(
            {**self.coordinator.data, "memoriesEnabled": enabled}
        )
