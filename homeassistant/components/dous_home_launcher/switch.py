"""Switches of the Dou's Home Launcher integration."""

from dataclasses import dataclass
from typing import Any, override

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import LauncherConnectionError
from .const import DOMAIN
from .coordinator import LauncherConfigEntry, LauncherCoordinator
from .entity import LauncherEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class LauncherSwitchEntityDescription(SwitchEntityDescription):
    """A switch whose state lives on the frame, under the same key."""


SWITCHES: tuple[LauncherSwitchEntityDescription, ...] = (
    LauncherSwitchEntityDescription(key="memories", translation_key="memories"),
    # Wins over the memories switch; the frame falls back to the usual photos on
    # a day without memories.
    LauncherSwitchEntityDescription(
        key="memories_only", translation_key="memories_only"
    ),
    LauncherSwitchEntityDescription(key="paused", translation_key="paused"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LauncherConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switches."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        LauncherSwitch(coordinator, description) for description in SWITCHES
    )


class LauncherSwitch(LauncherEntity, SwitchEntity):
    """A setting of the frame."""

    entity_description: LauncherSwitchEntityDescription

    def __init__(
        self,
        coordinator: LauncherCoordinator,
        description: LauncherSwitchEntityDescription,
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    @override
    def is_on(self) -> bool:
        """Return the setting as the frame last reported it."""
        return self.coordinator.data[self.entity_description.key]

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the setting on."""
        await self._async_set(True)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the setting off."""
        await self._async_set(False)

    async def _async_set(self, on: bool) -> None:
        try:
            state = await self.coordinator.client.set_settings(
                **{self.entity_description.key: on}
            )
        except LauncherConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="cannot_connect"
            ) from err
        self.coordinator.async_set_updated_data(state)
