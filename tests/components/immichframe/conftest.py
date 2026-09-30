"""Fixtures for the ImmichFrame integration tests."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.immichframe.const import CONF_SENSORS, DOMAIN
from homeassistant.const import CONF_ENTITY_ID, CONF_ICON, CONF_URL

from tests.common import MockConfigEntry
from tests.test_util.aiohttp import AiohttpClientMocker

URL = "http://192.168.1.166:8080"

OVERLAY = {
    "sensors": [],
    "notifications": [],
    "memoriesEnabled": True,
    "memoriesOnly": False,
}


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Skip the setup of the entry in config flow tests."""
    with patch(
        "homeassistant.components.immichframe.async_setup_entry", return_value=True
    ) as mock:
        yield mock


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """A frame showing a thermostat and a sensor."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="ImmichFrame",
        data={CONF_URL: URL},
        options={
            CONF_SENSORS: [
                {CONF_ENTITY_ID: "climate.salon", CONF_ICON: "🛋️"},
                {CONF_ENTITY_ID: "sensor.jardin", CONF_ICON: "🌳"},
            ]
        },
    )


@pytest.fixture
def frame(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """The frame API, answering like the fork does."""
    aioclient_mock.get(f"{URL}/api/Overlay", json=OVERLAY)
    aioclient_mock.get(f"{URL}/api/Memories", json={"enabled": True})
    aioclient_mock.put(f"{URL}/api/Memories", json={"enabled": False})
    aioclient_mock.put(f"{URL}/api/Overlay/Sensors", status=204)
    aioclient_mock.post(f"{URL}/api/Notification", status=204)
    return aioclient_mock
