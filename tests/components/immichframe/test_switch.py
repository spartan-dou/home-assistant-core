"""Tests for the memories switch of the ImmichFrame integration."""

import aiohttp
import pytest

from homeassistant.components.switch import (
    DOMAIN as SWITCH_DOMAIN,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .conftest import URL

from tests.common import MockConfigEntry
from tests.test_util.aiohttp import AiohttpClientMocker

ENTITY_ID = "switch.immichframe_memories"


async def test_switch_follows_and_sets_the_frame(
    hass: HomeAssistant, frame: AiohttpClientMocker, mock_config_entry: MockConfigEntry
) -> None:
    """The switch shows the state of the frame, and turning it off hides memories."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get(ENTITY_ID).state == STATE_ON

    await hass.services.async_call(
        SWITCH_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
    )

    assert hass.states.get(ENTITY_ID).state == STATE_OFF
    put = [call for call in frame.mock_calls if str(call[1]) == f"{URL}/api/Memories"]
    assert put[-1][0].lower() == "put"
    assert put[-1][2] == {"enabled": False}


async def test_switch_error_is_reported(
    hass: HomeAssistant, frame: AiohttpClientMocker, mock_config_entry: MockConfigEntry
) -> None:
    """A frame that refuses the change raises, and the state stays as it was."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    frame.clear_requests()
    frame.put(f"{URL}/api/Memories", exc=aiohttp.ClientError())

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: ENTITY_ID}, blocking=True
        )

    assert hass.states.get(ENTITY_ID).state == STATE_ON
