"""Tests for the Zepp OS config flow."""

from collections.abc import Generator
from unittest.mock import AsyncMock, patch

import pytest

from homeassistant.components.zepp.const import (
    CONF_AREAS,
    CONF_FAVORITES,
    CONF_PIPELINE,
    DOMAIN,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_API_KEY, CONF_ENTITIES
from homeassistant.core import HomeAssistant
from homeassistant.core_config import async_process_ha_core_config
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component

from .conftest import KEY

from tests.common import MockConfigEntry


@pytest.fixture(autouse=True)
def mock_setup_entry() -> Generator[AsyncMock]:
    """Skip the setup of the entry."""
    with patch(
        "homeassistant.components.zepp.async_setup_entry", return_value=True
    ) as mock:
        yield mock


@pytest.fixture(autouse=True)
async def external_url(hass: HomeAssistant) -> None:
    """Home Assistant as the phone reaches it from outside.

    The flow sets up assist_pipeline, whose conversation needs the core integration.
    """
    assert await async_setup_component(hass, "homeassistant", {})
    await async_process_ha_core_config(hass, {"external_url": "https://ha.example.com"})


async def test_user_flow(hass: HomeAssistant) -> None:
    """A watch gets a key of its own, shown with the address of the route."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    with patch(
        "homeassistant.components.zepp.config_flow.secrets.token_hex",
        return_value=KEY,
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Zepp OS"
    assert result["data"] == {CONF_API_KEY: KEY}
    assert result["description_placeholders"] == {
        "url": "https://ha.example.com/api/zepp",
        "key": KEY,
    }


async def test_two_watches_get_two_keys(hass: HomeAssistant) -> None:
    """Each watch can be removed without the other losing its access."""
    for _ in range(2):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        await hass.config_entries.flow.async_configure(result["flow_id"], {})

    keys = {
        entry.data[CONF_API_KEY] for entry in hass.config_entries.async_entries(DOMAIN)
    }
    assert len(keys) == 2


async def test_options_flow(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The options show the address and the key again, and keep what the watch shows."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["description_placeholders"] == {
        "url": "https://ha.example.com/api/zepp",
        "key": KEY,
    }

    options = {
        CONF_FAVORITES: ["light.salon_plafonnier", "script.maison_bonne_nuit"],
        CONF_ENTITIES: ["cover.salon_volet", "sensor.cuisine_temperature"],
        CONF_AREAS: ["salon", "cuisine"],
        CONF_PIPELINE: "01JPIPELINE",
    }
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], options
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert mock_config_entry.options == options
