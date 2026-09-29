"""Pushes the values of the chosen entities to the frame, like ESPHome imports them."""

from collections.abc import Callable
from datetime import datetime
import logging
from typing import Any

from homeassistant.components.climate import ATTR_CURRENT_TEMPERATURE
from homeassistant.const import (
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_ENTITY_ID,
    CONF_ICON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import (
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)

from .api import ImmichFrameConnectionError
from .const import CONF_SENSORS, PUSH_INTERVAL
from .coordinator import ImmichFrameConfigEntry

_LOGGER = logging.getLogger(__name__)


class SensorPusher:
    """Sends the configured entities to the frame on every change and on an interval."""

    def __init__(self, hass: HomeAssistant, entry: ImmichFrameConfigEntry) -> None:
        """Initialize the pusher from the entry options."""
        self._hass = hass
        self._entry = entry
        self._sensors: list[dict[str, str]] = entry.options.get(CONF_SENSORS, [])

    @callback
    def async_start(self) -> Callable[[], None]:
        """Push now, then on changes and on an interval. Return the unsubscriber."""
        unsubscribers = [
            async_track_time_interval(
                self._hass, self._async_on_interval, PUSH_INTERVAL
            )
        ]
        if entity_ids := [sensor[CONF_ENTITY_ID] for sensor in self._sensors]:
            unsubscribers.append(
                async_track_state_change_event(
                    self._hass, entity_ids, self._async_on_state_change
                )
            )
        self._async_schedule_push()

        @callback
        def _unsubscribe() -> None:
            for unsubscribe in unsubscribers:
                unsubscribe()

        return _unsubscribe

    @callback
    def _async_on_state_change(self, event: Event[EventStateChangedData]) -> None:
        self._async_schedule_push()

    @callback
    def _async_on_interval(self, now: datetime) -> None:
        self._async_schedule_push()

    @callback
    def _async_schedule_push(self) -> None:
        self._entry.async_create_background_task(
            self._hass, self.async_push(), "immichframe_push_sensors"
        )

    def payload(self) -> list[dict[str, Any]]:
        """Return what the frame should show, in the configured order."""
        return [
            _describe(self._hass, self._hass.states.get(sensor[CONF_ENTITY_ID]), sensor)
            for sensor in self._sensors
        ]

    async def async_push(self) -> None:
        """Send the current values; an unreachable frame gets them at the next push."""
        try:
            await self._entry.runtime_data.client.set_sensors(self.payload())
        except ImmichFrameConnectionError as err:
            _LOGGER.debug("Could not push sensors to the frame: %s", err)


def _describe(
    hass: HomeAssistant, state: State | None, sensor: dict[str, str]
) -> dict[str, Any]:
    """A climate entity shows its current temperature, anything else its state."""
    value: Any = None
    unit = ""
    if state is not None:
        if state.domain == "climate":
            value = state.attributes.get(ATTR_CURRENT_TEMPERATURE)
            unit = hass.config.units.temperature_unit
        else:
            value = state.state
            unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) or ""
    if value in (None, STATE_UNKNOWN, STATE_UNAVAILABLE):
        value = None
    return {
        "icon": sensor.get(CONF_ICON) or "",
        "value": None if value is None else str(value),
        "unit": unit,
    }
