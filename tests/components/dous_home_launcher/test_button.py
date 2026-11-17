"""Tests for the buttons of the Dou's Home Launcher integration."""

import aiohttp
import pytest
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from homeassistant.components.button import DOMAIN as BUTTON_DOMAIN, SERVICE_PRESS
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .conftest import URL


def commands(frame: AiohttpClientMocker) -> list[dict]:
    """Commands sent to the frame, oldest first."""
    return [
        call[2] for call in frame.mock_calls if str(call[1]) == f"{URL}/api/command"
    ]


@pytest.mark.usefixtures("setup_frame")
@pytest.mark.parametrize(
    ("entity_id", "command"),
    [
        pytest.param("button.tablette_next_photo", "next", id="next"),
        pytest.param("button.tablette_previous_photo", "previous", id="previous"),
        pytest.param("button.tablette_close", "close", id="close"),
        pytest.param("button.tablette_turn_off_screen", "screen_off", id="screen_off"),
    ],
)
async def test_button_sends_its_command(
    hass: HomeAssistant, frame: AiohttpClientMocker, entity_id: str, command: str
) -> None:
    """Each button sends the command the frame knows it by."""
    await hass.services.async_call(
        BUTTON_DOMAIN, SERVICE_PRESS, {ATTR_ENTITY_ID: entity_id}, blocking=True
    )

    assert commands(frame) == [{"command": command}]


@pytest.mark.usefixtures("setup_frame")
async def test_button_error_is_reported(
    hass: HomeAssistant, frame: AiohttpClientMocker
) -> None:
    """A frame that has left the screen meanwhile raises."""
    frame.clear_requests()
    frame.post(f"{URL}/api/command", exc=aiohttp.ClientError())

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            BUTTON_DOMAIN,
            SERVICE_PRESS,
            {ATTR_ENTITY_ID: "button.tablette_close"},
            blocking=True,
        )
