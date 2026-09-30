"""Notification entity of the ImmichFrame integration."""

from homeassistant.components.notify import NotifyEntity
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
    """Set up the notification entity."""
    async_add_entities([ImmichFrameNotifyEntity(entry.runtime_data.coordinator)])


class ImmichFrameNotifyEntity(ImmichFrameEntity, NotifyEntity):
    """Shows a message on top of the slideshow."""

    _attr_name = None

    def __init__(self, coordinator: ImmichFrameCoordinator) -> None:
        """Initialize the entity."""
        super().__init__(coordinator, "notification")

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """Show a message, the title on its own line above it."""
        await self.async_show_notification(f"{title}\n{message}" if title else message)

    async def async_show_notification(
        self, message: str, link: str | None = None, duration: float | None = None
    ) -> None:
        """Show a message with an optional link and end; an empty message clears them all."""
        try:
            await self.coordinator.client.send_notification(message, link, duration)
        except ImmichFrameConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="cannot_connect"
            ) from err
