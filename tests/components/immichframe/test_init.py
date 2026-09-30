"""Tests for the setup of the ImmichFrame integration and its sensor pusher."""

from datetime import timedelta

import aiohttp
from freezegun.api import FrozenDateTimeFactory

from homeassistant.components.immichframe.const import PUSH_COOLDOWN, PUSH_INTERVAL
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import URL

from tests.common import MockConfigEntry, async_fire_time_changed
from tests.test_util.aiohttp import AiohttpClientMocker

SENSORS_URL = f"{URL}/api/Overlay/Sensors"


def pushes(frame: AiohttpClientMocker) -> list[list[dict]]:
    """Payloads sent to the frame, oldest first."""
    return [
        call[2]["sensors"]
        for call in frame.mock_calls
        if call[0].lower() == "put" and str(call[1]) == SENSORS_URL
    ]


async def test_setup_pushes_values_in_order(
    hass: HomeAssistant, frame: AiohttpClientMocker, mock_config_entry: MockConfigEntry
) -> None:
    """A climate shows its current temperature, a sensor its state and unit."""
    hass.states.async_set("climate.salon", "heat", {"current_temperature": 20.5})
    hass.states.async_set("sensor.jardin", "12.5", {"unit_of_measurement": "°C"})
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert pushes(frame)[-1] == [
        {"icon": "🛋️", "value": "20.5", "unit": UnitOfTemperature.CELSIUS},
        {"icon": "🌳", "value": "12.5", "unit": "°C"},
    ]


async def test_state_change_is_pushed(
    hass: HomeAssistant,
    frame: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A change of a chosen entity reaches the frame; others do not."""
    hass.states.async_set("sensor.jardin", "12.5", {"unit_of_measurement": "°C"})
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    freezer.tick(timedelta(seconds=PUSH_COOLDOWN))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)
    count = len(pushes(frame))

    hass.states.async_set("sensor.ailleurs", "1")
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(pushes(frame)) == count

    hass.states.async_set("sensor.jardin", "13.0", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(pushes(frame)) == count + 1
    assert pushes(frame)[-1][1]["value"] == "13.0"


async def test_burst_of_changes_is_one_push_with_the_last_value(
    hass: HomeAssistant,
    frame: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Changes during a push's cooldown are sent once it ends, as they stand then."""
    hass.states.async_set("sensor.jardin", "12.5", {"unit_of_measurement": "°C"})
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    count = len(pushes(frame))

    for value in ("13.0", "13.5", "14.0"):
        hass.states.async_set("sensor.jardin", value, {"unit_of_measurement": "°C"})
    await hass.async_block_till_done(wait_background_tasks=True)
    assert len(pushes(frame)) == count

    freezer.tick(timedelta(seconds=PUSH_COOLDOWN))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert len(pushes(frame)) == count + 1
    assert pushes(frame)[-1][1]["value"] == "14.0"


async def test_sensor_is_rounded_to_its_display_precision(
    hass: HomeAssistant,
    frame: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """The frame shows a sensor as Home Assistant does, not its raw state."""
    entry = entity_registry.async_get_or_create(
        "sensor", "test", "jardin", suggested_object_id="jardin"
    )
    entity_registry.async_update_entity_options(
        entry.entity_id, "sensor", {"display_precision": 1}
    )
    hass.states.async_set("sensor.jardin", "12.3456", {"unit_of_measurement": "°C"})
    mock_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert pushes(frame)[-1][1]["value"] == "12.3"


async def test_unknown_values_are_sent_empty(
    hass: HomeAssistant, frame: AiohttpClientMocker, mock_config_entry: MockConfigEntry
) -> None:
    """Missing or unavailable entities keep their place, without a value."""
    hass.states.async_set("sensor.jardin", STATE_UNAVAILABLE)
    mock_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert [sensor["value"] for sensor in pushes(frame)[-1]] == [None, None]


async def test_values_are_pushed_again_on_an_interval(
    hass: HomeAssistant,
    frame: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A restarted frame gets the values back without waiting for a change."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    count = len(pushes(frame))

    freezer.tick(PUSH_INTERVAL + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert len(pushes(frame)) > count


async def test_unreachable_frame_retries_setup(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A frame that does not answer at startup is retried, not failed."""
    aioclient_mock.get(f"{URL}/api/Overlay", exc=aiohttp.ClientError())
    mock_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload(
    hass: HomeAssistant, frame: AiohttpClientMocker, mock_config_entry: MockConfigEntry
) -> None:
    """Unloading stops the pushes."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    count = len(pushes(frame))
    hass.states.async_set("sensor.jardin", "14.0")
    await hass.async_block_till_done(wait_background_tasks=True)

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
    assert len(pushes(frame)) == count
