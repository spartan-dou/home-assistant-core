"""Tests for the brightness of the Dou's Home Launcher integration."""

import pytest
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from homeassistant.components.number import (
    ATTR_VALUE,
    DOMAIN as NUMBER_DOMAIN,
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

from .conftest import STATE, URL

BRIGHTNESS = "number.tablette_frame_brightness"


@pytest.mark.usefixtures("setup_frame")
async def test_brightness_follows_and_sets_the_frame(
    hass: HomeAssistant, frame: AiohttpClientMocker
) -> None:
    """Unknown while the frame follows the device, then what the frame answers."""
    assert hass.states.get(BRIGHTNESS).state == STATE_UNKNOWN

    frame.clear_requests()
    frame.put(f"{URL}/api/settings", json={**STATE, "brightness": 20})
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {ATTR_ENTITY_ID: BRIGHTNESS, ATTR_VALUE: 20},
        blocking=True,
    )

    assert [call[2] for call in frame.mock_calls] == [{"brightness": 20}]
    assert float(hass.states.get(BRIGHTNESS).state) == 20
