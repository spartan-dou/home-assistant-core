"""Tests for the ImmichFrame config flow."""

from unittest.mock import AsyncMock

import aiohttp
import pytest

from homeassistant.components.immichframe.const import CONF_SENSORS, DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_API_KEY, CONF_ENTITY_ID, CONF_ICON, CONF_URL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData

from .conftest import URL

from tests.common import MockConfigEntry
from tests.test_util.aiohttp import AiohttpClientMocker


@pytest.mark.usefixtures("mock_setup_entry")
async def test_user_flow(hass: HomeAssistant, frame: AiohttpClientMocker) -> None:
    """A frame that answers is added, its address without trailing slash."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: f"{URL}/", CONF_API_KEY: "secret"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "ImmichFrame"
    assert result["data"] == {CONF_URL: URL, CONF_API_KEY: "secret"}
    assert frame.mock_calls[0][3] == {"Authorization": "Bearer secret"}


@pytest.mark.usefixtures("mock_setup_entry")
async def test_user_flow_cannot_connect(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    """An unreachable frame shows an error, then can be retried."""
    aioclient_mock.get(f"{URL}/api/Memories", exc=aiohttp.ClientError())
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: URL}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    aioclient_mock.clear_requests()
    aioclient_mock.get(f"{URL}/api/Memories", json={"enabled": False})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: URL}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


@pytest.mark.usefixtures("mock_setup_entry")
async def test_user_flow_already_configured(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The same frame cannot be added twice."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_URL: f"{URL}/"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow(
    hass: HomeAssistant,
    frame: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    mock_setup_entry: AsyncMock,
) -> None:
    """The entities and their emoji are stored in order, trimmed."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_SENSORS: [
                {CONF_ENTITY_ID: "sensor.jardin", CONF_ICON: " 🌳 "},
                {CONF_ENTITY_ID: "climate.chambre"},
            ]
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options == {
        CONF_SENSORS: [
            {CONF_ENTITY_ID: "sensor.jardin", CONF_ICON: "🌳"},
            {CONF_ENTITY_ID: "climate.chambre", CONF_ICON: ""},
        ]
    }


@pytest.mark.usefixtures("mock_setup_entry")
async def test_options_flow_invalid_entity(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The selector refuses a line without a valid entity id."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)

    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SENSORS: [{CONF_ENTITY_ID: "not an entity"}]}
        )
