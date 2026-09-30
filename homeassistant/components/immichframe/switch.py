"""Memories switches of the ImmichFrame integration."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import ImmichFrameClient, ImmichFrameConnectionError
from .const import DOMAIN
from .coordinator import ImmichFrameConfigEntry, ImmichFrameCoordinator
from .entity import ImmichFrameEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class ImmichFrameSwitchEntityDescription(SwitchEntityDescription):
    """A switch the frame keeps across restarts."""

    state_key: str
    set_fn: Callable[[ImmichFrameClient, bool], Awaitable[None]]


SWITCHES: tuple[ImmichFrameSwitchEntityDescription, ...] = (
    ImmichFrameSwitchEntityDescription(
        key="memories",
        translation_key="memories",
        state_key="memoriesEnabled",
        set_fn=lambda client, on: client.set_memories(enabled=on),
    ),
    # Wins over the memories switch; the frame falls back to the usual photos on
    # a day without memories.
    ImmichFrameSwitchEntityDescription(
        key="memories_only",
        translation_key="memories_only",
        state_key="memoriesOnly",
        set_fn=lambda client, on: client.set_memories(only=on),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ImmichFrameConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the memories switches."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        ImmichFrameSwitch(coordinator, description) for description in SWITCHES
    )


class ImmichFrameSwitch(ImmichFrameEntity, SwitchEntity):
    """A switch whose state lives on the frame."""

    entity_description: ImmichFrameSwitchEntityDescription

    def __init__(
        self,
        coordinator: ImmichFrameCoordinator,
        description: ImmichFrameSwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        """Return the state the frame reports."""
        return bool(self.coordinator.data.get(self.entity_description.state_key))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._async_set(False)

    async def _async_set(self, on: bool) -> None:
        try:
            await self.entity_description.set_fn(self.coordinator.client, on)
        except ImmichFrameConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="cannot_connect"
            ) from err
        self.coordinator.async_set_updated_data(
            {**self.coordinator.data, self.entity_description.state_key: on}
        )
