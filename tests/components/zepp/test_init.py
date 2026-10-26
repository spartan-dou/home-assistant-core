"""Tests for the setup of the Zepp OS integration."""

from http import HTTPStatus
from typing import Any

from aiohttp.test_utils import TestClient
import pytest

from homeassistant.components.zepp.const import CONF_FAVORITES, DOMAIN, URL
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_API_KEY, CONF_WEBHOOK_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component

from .conftest import HEADERS, KEY, Post

from tests.common import MockConfigEntry
from tests.typing import ClientSessionGenerator


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


async def test_unloaded_watch_is_refused(
    hass: HomeAssistant, post: Post, mock_config_entry: MockConfigEntry
) -> None:
    """Once its entry is unloaded, the key of a watch opens nothing."""
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED

    response = await post({"type": "pages"})

    assert response.status == HTTPStatus.UNAUTHORIZED
    assert (await response.json())["error"] == "unauthorized"


@pytest.mark.parametrize(
    "headers",
    [
        pytest.param({}, id="no_key"),
        pytest.param({"Authorization": f"Bearer {KEY[:-1]}0"}, id="wrong_key"),
        pytest.param({"Authorization": f"Bearer {KEY}{KEY}"}, id="longer_key"),
        pytest.param({"Authorization": "Bearer "}, id="empty_key"),
        pytest.param({"Authorization": f"Basic {KEY}"}, id="not_bearer"),
        pytest.param({"X-Zepp-Key": KEY}, id="other_header"),
    ],
)
async def test_wrong_key_is_refused(
    client: TestClient, headers: dict[str, str]
) -> None:
    """Without the key of a watch, the route says nothing more than no."""
    response = await client.post(URL, json={"type": "pages"}, headers=headers)

    assert response.status == HTTPStatus.UNAUTHORIZED
    assert await response.json() == {"error": "unauthorized", "message": None}


async def test_migrate_webhook_id_to_key(
    hass: HomeAssistant, hass_client_no_auth: ClientSessionGenerator
) -> None:
    """A watch added with a webhook keeps its secret, now sent as its key."""
    assert await async_setup_component(hass, "homeassistant", {})
    entry = MockConfigEntry(
        domain=DOMAIN, title="Balance", data={CONF_WEBHOOK_ID: KEY}, version=1
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)

    assert entry.version == 2
    assert entry.data == {CONF_API_KEY: KEY}
    client = await hass_client_no_auth()
    response = await client.post(URL, json={"type": "pages"}, headers=HEADERS)
    assert response.status == HTTPStatus.OK


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
    response = await client.post(URL, data="{", headers=HEADERS)

    assert response.status == HTTPStatus.BAD_REQUEST
    assert (await response.json())["error"] == "invalid_json"


@pytest.mark.usefixtures("house")
async def test_each_key_opens_its_own_watch(
    hass: HomeAssistant, post: Post, client: TestClient
) -> None:
    """With two watches, a key answers with the favorites of its own watch."""
    other = MockConfigEntry(
        domain=DOMAIN,
        title="GTR 4",
        data={CONF_API_KEY: "f" * 64},
        options={CONF_FAVORITES: ["switch.garage_prise"]},
        version=2,
    )
    other.add_to_hass(hass)
    assert await hass.config_entries.async_setup(other.entry_id)

    balance = await (await post({"type": "pages"})).json()
    gtr = await (
        await client.post(
            URL, json={"type": "pages"}, headers={"Authorization": f"Bearer {'f' * 64}"}
        )
    ).json()

    assert balance["pages"][0]["tiles"][0]["id"] == "script.maison_bonne_nuit"
    assert [tile["id"] for tile in gtr["pages"][0]["tiles"]] == ["switch.garage_prise"]


async def test_get_answers_method_not_allowed(client: TestClient) -> None:
    """Opening the address in a browser shows it exists, without any key."""
    response = await client.get(URL)

    assert response.status == HTTPStatus.METHOD_NOT_ALLOWED
