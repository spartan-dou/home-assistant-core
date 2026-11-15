"""Base entity for the Dou's Home Launcher integration."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LauncherCoordinator


class LauncherEntity(CoordinatorEntity[LauncherCoordinator]):
    """An entity of the frame device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: LauncherCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        device_id = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{device_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=entry.title,
            manufacturer="Dou's Home Launcher",
        )
