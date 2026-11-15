"""Tests for the switches of the Dou's Home Launcher integration."""

import aiohttp
import pytest
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from homeassistant.components.switch import (
    DOMAIN as SWITCH_DOMAIN,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .conftest import STATE, URL

MEMORIES = "switch.tablette_memories"
MEMORIES_ONLY = "switch.tablette_memories_only"
PAUSE = "switch.tablette_pause"


def settings_updates(frame: AiohttpClientMocker) -> list[dict]:
    """Payloads sent to change the settings, oldest first."""
    return [
        call[2] for call in frame.mock_calls if str(call[1]) == f"{URL}/api/settings"
    ]


@pytest.mark.usefixtures("setup_frame")
async def test_switch_follows_and_sets_the_frame(
    hass: HomeAssistant, frame: AiohttpClientMocker
) -> None:
    """A switch shows the frame's setting, and takes the state the frame answers."""
    assert hass.states.get(MEMORIES).state == STATE_ON
    assert hass.states.get(MEMORIES_ONLY).state == STATE_OFF
    assert hass.states.get(PAUSE).state == STATE_OFF

    await hass.services.async_call(
        SWITCH_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: MEMORIES}, blocking=True
    )

    assert settings_updates(frame)[-1] == {"memories": False}
    assert hass.states.get(MEMORIES).state == STATE_OFF


@pytest.mark.usefixtures("setup_frame")
@pytest.mark.parametrize(
    ("entity_id", "setting"),
    [
        pytest.param(MEMORIES_ONLY, "memories_only", id="memories_only"),
        pytest.param(PAUSE, "paused", id="pause"),
    ],
)
async def test_switch_sends_its_own_setting(
    hass: HomeAssistant, frame: AiohttpClientMocker, entity_id: str, setting: str
) -> None:
    """Each switch sends its setting alone: the others keep theirs on the frame."""
    frame.clear_requests()
    frame.put(f"{URL}/api/settings", json={**STATE, setting: True})

    await hass.services.async_call(
        SWITCH_DOMAIN, SERVICE_TURN_ON, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )

    assert settings_updates(frame)[-1] == {setting: True}
    assert hass.states.get(entity_id).state == STATE_ON
    assert hass.states.get(MEMORIES).state == STATE_ON


@pytest.mark.usefixtures("setup_frame")
async def test_switch_error_is_reported(
    hass: HomeAssistant, frame: AiohttpClientMocker
) -> None:
    """A frame that does not take the change raises, and the state stays as it was."""
    frame.clear_requests()
    frame.put(f"{URL}/api/settings", exc=aiohttp.ClientError())

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            SWITCH_DOMAIN, SERVICE_TURN_OFF, {ATTR_ENTITY_ID: MEMORIES}, blocking=True
        )

    assert hass.states.get(MEMORIES).state == STATE_ON
