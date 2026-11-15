"""Notification entity of the Dou's Home Launcher integration."""

from typing import override

from homeassistant.components.notify import NotifyEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import LauncherConnectionError
from .const import DOMAIN
from .coordinator import LauncherConfigEntry, LauncherCoordinator
from .entity import LauncherEntity

PARALLEL_UPDATES = 1


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LauncherConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the notification entity."""
    async_add_entities([LauncherNotifyEntity(entry.runtime_data.coordinator)])


class LauncherNotifyEntity(LauncherEntity, NotifyEntity):
    """Shows a message on top of the slideshow."""

    _attr_name = None

    def __init__(self, coordinator: LauncherCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, "notification")

    @override
    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """Show a message, the title on its own line above it."""
        await self.async_show_notification(f"{title}\n{message}" if title else message)

    async def async_show_notification(
        self,
        message: str,
        link: str | None = None,
        duration: float | None = None,
        tag: str | None = None,
    ) -> None:
        """Show a message with an optional link, end and tag.

        A message replaces the one shown with the same tag; an empty message clears
        the tagged one, or all of them without a tag.
        """
        try:
            await self.coordinator.client.send_notification(
                message, link, duration, tag
            )
        except LauncherConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="cannot_connect"
            ) from err
