"""Number of the Dou's Home Launcher integration: the frame's own brightness."""

from typing import override

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import LauncherConnectionError
from .const import DOMAIN
from .coordinator import LauncherConfigEntry, LauncherCoordinator
from .entity import LauncherEntity

PARALLEL_UPDATES = 1

# Only the frame's window, as ImmichFrame's brightness: the rest of the device keeps its
# own. The frame fades to it, and 0 % stays faintly lit, never black.
BRIGHTNESS = NumberEntityDescription(
    key="brightness",
    translation_key="brightness",
    native_min_value=0,
    native_max_value=100,
    native_step=1,
    native_unit_of_measurement=PERCENTAGE,
    mode=NumberMode.SLIDER,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LauncherConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the brightness."""
    async_add_entities([LauncherBrightness(entry.runtime_data.coordinator)])


class LauncherBrightness(LauncherEntity, NumberEntity):
    """The frame's brightness; unknown while it follows the device's."""

    entity_description = BRIGHTNESS

    def __init__(self, coordinator: LauncherCoordinator) -> None:
        """Initialize the brightness."""
        super().__init__(coordinator, BRIGHTNESS.key)

    @property
    @override
    def native_value(self) -> float | None:
        """Return the brightness as the frame last reported it."""
        return self.coordinator.data.get(BRIGHTNESS.key)

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Fade the frame to this brightness."""
        try:
            state = await self.coordinator.client.set_settings(
                **{BRIGHTNESS.key: round(value)}
            )
        except LauncherConnectionError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="cannot_connect"
            ) from err
        self.coordinator.async_set_updated_data(state)
