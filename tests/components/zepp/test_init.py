"""Tests for the setup of the Zepp OS integration."""

from http import HTTPStatus
from typing import Any

from aiohttp.test_utils import TestClient
import pytest

from homeassistant.components.zepp.const import DOMAIN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .conftest import WEBHOOK_PATH, Post

from tests.common import MockConfigEntry


async def test_setup_creates_the_watch_device(
    hass: HomeAssistant,
    post: Post,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    """A watch is a device named like its entry."""
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, mock_config_entry.entry_id), mock_config_entry.entry_id
    )
    assert device is not None
    assert mock_config_entry.runtime_data == device.id
    assert device.name == "Balance"
    assert device.manufacturer == "Zepp Health"


async def test_unload_removes_the_webhook(
    hass: HomeAssistant, post: Post, mock_config_entry: MockConfigEntry
) -> None:
    """Once unloaded, the webhook answers like an unknown one: empty."""
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED

    response = await post({"type": "pages"})

    assert response.status == HTTPStatus.OK
    assert await response.text() == ""


@pytest.mark.parametrize(
    ("body", "error"),
    [
        pytest.param({"type": "unknown"}, "unknown_type", id="unknown_type"),
        pytest.param(["pages"], "unknown_type", id="not_an_object"),
        pytest.param({"type": "action"}, "invalid_request", id="missing_fields"),
        pytest.param(
            {"type": "action", "entity_id": "not an id", "action": "toggle"},
            "invalid_request",
            id="invalid_entity_id",
        ),
    ],
)
async def test_invalid_requests(post: Post, body: Any, error: str) -> None:
    """A malformed request is refused before reaching anything."""
    response = await post(body)

    assert response.status == HTTPStatus.BAD_REQUEST
    assert (await response.json())["error"] == error


async def test_invalid_json(client: TestClient) -> None:
    """A body that is not JSON is refused."""
    response = await client.post(WEBHOOK_PATH, data="{")

    assert response.status == HTTPStatus.BAD_REQUEST
    assert (await response.json())["error"] == "invalid_json"
