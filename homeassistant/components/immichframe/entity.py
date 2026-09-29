"""Base entity for the ImmichFrame integration."""

from homeassistant.const import CONF_URL
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ImmichFrameCoordinator


class ImmichFrameEntity(CoordinatorEntity[ImmichFrameCoordinator]):
    """An entity of the frame device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: ImmichFrameCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="ImmichFrame",
            configuration_url=entry.data[CONF_URL],
        )
