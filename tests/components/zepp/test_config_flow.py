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
from homeassistant.const import CONF_ENTITIES, CONF_WEBHOOK_ID
from homeassistant.core import HomeAssistant
from homeassistant.core_config import async_process_ha_core_config
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component

from .conftest import WEBHOOK_ID

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
    """A watch gets a webhook of its own, whose address is shown."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    with patch(
        "homeassistant.components.zepp.config_flow.webhook.async_generate_id",
        return_value=WEBHOOK_ID,
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Zepp OS"
    assert result["data"] == {CONF_WEBHOOK_ID: WEBHOOK_ID}
    assert result["description_placeholders"] == {
        "url": f"https://ha.example.com/api/webhook/{WEBHOOK_ID}"
    }


async def test_two_watches_get_two_webhooks(hass: HomeAssistant) -> None:
    """Each watch can be removed without the other losing its access."""
    for _ in range(2):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        await hass.config_entries.flow.async_configure(result["flow_id"], {})

    webhook_ids = {
        entry.data[CONF_WEBHOOK_ID]
        for entry in hass.config_entries.async_entries(DOMAIN)
    }
    assert len(webhook_ids) == 2


async def test_options_flow(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """The options show the address again, and keep what the watch shows."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["description_placeholders"] == {
        "url": f"https://ha.example.com/api/webhook/{WEBHOOK_ID}"
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
