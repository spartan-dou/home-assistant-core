"""Buttons of the Dou's Home Launcher integration."""

from typing import override

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import LauncherConnectionError
from .const import CONF_TV, DOMAIN
from .coordinator import LauncherConfigEntry, LauncherCoordinator
from .entity import LauncherEntity

PARALLEL_UPDATES = 1

# The key is the command the frame understands.
BUTTONS: tuple[ButtonEntityDescription, ...] = (
    ButtonEntityDescription(key="next", translation_key="next"),
    ButtonEntityDescription(key="previous", translation_key="previous"),
    # Leaves the screen to its usual timeout: how a tablet goes to sleep at night.
    ButtonEntityDescription(key="close", translation_key="close"),
    # Turns the screen off and leaves it off, even on the charger (the tablet's former Tasker
    # HA_LOCK); the app must be a device admin.
    ButtonEntityDescription(key="screen_off", translation_key="screen_off"),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LauncherConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the buttons."""
    coordinator = entry.runtime_data.coordinator
    # A TV has no screen of its own to turn off
    tv = entry.data.get(CONF_TV, False)
    async_add_entities(
        LauncherButton(coordinator, description)
        for description in BUTTONS
        if not (tv and description.key == "screen_off")
    )


class LauncherButton(LauncherEntity, ButtonEntity):
    """A command sent to the frame."""

    def __init__(
        self, coordinator: LauncherCoordinator, description: ButtonEntityDescription
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @override
    async def async_press(self) -> None:
        """Send the command."""
        try:
            await self.coordinator.client.send_command(self.entity_description.key)
        except LauncherConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="cannot_connect"
            ) from err
        await self.coordinator.async_request_refresh()
