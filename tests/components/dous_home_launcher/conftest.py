"""Fixtures for the Dou's Home Launcher integration tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest
from pytest_homeassistant.common import MockConfigEntry
from pytest_homeassistant.test_util.aiohttp import AiohttpClientMocker

from homeassistant.components.dous_home_launcher.const import CONF_SENSORS, DOMAIN
from homeassistant.const import CONF_API_KEY, CONF_ENTITY_ID, CONF_ICON, CONF_URL
from homeassistant.core import HomeAssistant

URL = "http://192.168.1.50:47915"
KEY = "ABCD2345"
DEVICE_ID = "0b1c9c55-6c0f-4f0e-9d8e-0a3a3f1f6a11"

STATE = {
    "id": DEVICE_ID,
    "name": "Tablette",
    "memories": True,
    "memories_only": False,
    "paused": False,
    "place": None,
    "date": None,
}


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Skip the setup of the entry in config flow tests."""
    with patch(
        "homeassistant.components.dous_home_launcher.async_setup_entry",
        return_value=True,
    ) as mock:
        yield mock


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """A frame showing a thermostat and a sensor."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Tablette",
        unique_id=DEVICE_ID,
        data={CONF_URL: URL, CONF_API_KEY: KEY},
        options={
            CONF_SENSORS: [
                {CONF_ENTITY_ID: "climate.salon", CONF_ICON: "🛋️"},
                {CONF_ENTITY_ID: "sensor.jardin", CONF_ICON: "🌳"},
            ]
        },
    )


@pytest.fixture
def frame(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """The API of a frame that is on screen."""
    aioclient_mock.get(f"{URL}/api/state", json=STATE)
    aioclient_mock.put(f"{URL}/api/settings", json={**STATE, "memories": False})
    aioclient_mock.post(f"{URL}/api/command", status=204)
    aioclient_mock.put(f"{URL}/api/sensors", status=204)
    aioclient_mock.post(f"{URL}/api/notifications", status=204)
    return aioclient_mock


@pytest.fixture
async def setup_frame(
    hass: HomeAssistant, frame: AiohttpClientMocker, mock_config_entry: MockConfigEntry
) -> None:
    """Set up a frame that is on screen."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
