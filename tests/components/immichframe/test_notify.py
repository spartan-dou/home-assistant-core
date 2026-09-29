"""Tests for the notifications of the ImmichFrame integration."""

import pytest

from homeassistant.components.immichframe.const import DOMAIN, SERVICE_SHOW_NOTIFICATION
from homeassistant.components.notify import (
    ATTR_MESSAGE,
    ATTR_TITLE,
    DOMAIN as NOTIFY_DOMAIN,
    SERVICE_SEND_MESSAGE,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant

from .conftest import URL

from tests.common import MockConfigEntry
from tests.test_util.aiohttp import AiohttpClientMocker

ENTITY_ID = "notify.immichframe"


def notifications(frame: AiohttpClientMocker) -> list[dict]:
    """Payloads sent to the notification endpoint, oldest first."""
    return [
        call[2]
        for call in frame.mock_calls
        if str(call[1]) == f"{URL}/api/Notification"
    ]


@pytest.fixture
async def setup_frame(
    hass: HomeAssistant, frame: AiohttpClientMocker, mock_config_entry: MockConfigEntry
) -> None:
    """Set up the frame."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.usefixtures("setup_frame")
async def test_send_message(hass: HomeAssistant, frame: AiohttpClientMocker) -> None:
    """notify.send_message shows the title on its own line above the message."""
    await hass.services.async_call(
        NOTIFY_DOMAIN,
        SERVICE_SEND_MESSAGE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_MESSAGE: "Colis déposé", ATTR_TITLE: "📦"},
        blocking=True,
    )

    assert notifications(frame)[-1] == {
        "message": "📦\nColis déposé",
        "link": None,
        "duration": None,
        "replace": True,
    }


@pytest.mark.usefixtures("setup_frame")
async def test_show_notification(
    hass: HomeAssistant, frame: AiohttpClientMocker
) -> None:
    """The action passes the link, the duration and the replace flag."""
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SHOW_NOTIFICATION,
        {
            ATTR_ENTITY_ID: ENTITY_ID,
            "message": "Colis",
            "link": "/lovelace/cameras",
            "duration": 30,
            "replace": False,
        },
        blocking=True,
    )

    assert notifications(frame)[-1] == {
        "message": "Colis",
        "link": "/lovelace/cameras",
        "duration": 30.0,
        "replace": False,
    }


@pytest.mark.usefixtures("setup_frame")
async def test_show_notification_empty_message_clears(
    hass: HomeAssistant, frame: AiohttpClientMocker
) -> None:
    """An empty message is accepted: it is how a notification is cleared."""
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SHOW_NOTIFICATION,
        {ATTR_ENTITY_ID: ENTITY_ID, "message": ""},
        blocking=True,
    )

    assert notifications(frame)[-1]["message"] == ""
