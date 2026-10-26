"""Tests for pairing a watch from its phone."""

from http import HTTPStatus
import re
from typing import Any

from aiohttp.test_utils import TestClient
from freezegun.api import FrozenDateTimeFactory
import pytest

from homeassistant.components.zepp.const import (
    DOMAIN,
    PAIR_STATUS_URL,
    PAIR_URL,
    PAIRING_LIMIT,
    PAIRING_TIMEOUT,
    PAIRING_WINDOW,
    URL,
)
from homeassistant.components.zepp.pairing import Pairing
from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY
from homeassistant.const import CONF_API_KEY, CONF_CODE
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component

from tests.common import async_fire_time_changed
from tests.typing import ClientSessionGenerator

NAME = "Amazfit Balance"


@pytest.fixture
async def client(
    hass: HomeAssistant, hass_client_no_auth: ClientSessionGenerator
) -> TestClient:
    """No watch yet: `zepp:` in the configuration opens the pairing route."""
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {}})
    return await hass_client_no_auth()


async def _async_pair(client: TestClient, name: str = NAME) -> dict[str, Any]:
    response = await client.post(PAIR_URL, json={"name": name})
    assert response.status == HTTPStatus.OK
    return await response.json()


async def _async_status(client: TestClient, request: str) -> tuple[int, Any]:
    response = await client.post(PAIR_STATUS_URL, json={"request": request})
    return response.status, await response.json()


async def test_pairing(hass: HomeAssistant, client: TestClient) -> None:
    """The watch shows a code, entered in Home Assistant; the phone gets the key."""
    pairing = await _async_pair(client, f"  {NAME} ")
    assert re.fullmatch(r"\d{6}", pairing["code"])
    assert pairing["expires_in"] == PAIRING_TIMEOUT
    [flow] = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flow["context"]["source"] == SOURCE_INTEGRATION_DISCOVERY
    assert flow["context"]["title_placeholders"] == {"name": NAME}
    assert flow["step_id"] == "confirm"
    assert await _async_status(client, pairing["request"]) == (
        HTTPStatus.OK,
        {"status": "pending"},
    )

    wrong = f"{(int(pairing['code']) + 1) % 1_000_000:06d}"
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_CODE: wrong}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_CODE: "invalid_code"}
    # The code goes to the watch only: the form never shows it.
    assert result["description_placeholders"] == {"name": NAME}
    assert await _async_status(client, pairing["request"]) == (
        HTTPStatus.OK,
        {"status": "pending"},
    )

    code = pairing["code"]
    result = await hass.config_entries.flow.async_configure(
        flow["flow_id"], {CONF_CODE: f"{code[:3]} {code[3:]}"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    key = result["data"][CONF_API_KEY]
    assert re.fullmatch(r"[0-9a-f]{64}", key)
    assert await _async_status(client, pairing["request"]) == (
        HTTPStatus.OK,
        {"status": "paired", "key": key},
    )

    await hass.async_block_till_done()
    response = await client.post(
        URL, json={"type": "pages"}, headers={"Authorization": f"Bearer {key}"}
    )
    assert response.status == HTTPStatus.OK


async def test_new_request_replaces_the_pending_one(
    hass: HomeAssistant, client: TestClient
) -> None:
    """Whoever asks, Home Assistant shows one discovered watch at most."""
    first = await _async_pair(client)
    [first_flow] = hass.config_entries.flow.async_progress_by_handler(DOMAIN)

    second = await _async_pair(client, "Amazfit GTR 4")

    [flow] = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flow["flow_id"] != first_flow["flow_id"]
    assert flow["context"]["title_placeholders"] == {"name": "Amazfit GTR 4"}
    assert await _async_status(client, first["request"]) == (
        HTTPStatus.NOT_FOUND,
        {"error": "unknown_request", "message": None},
    )
    assert await _async_status(client, second["request"]) == (
        HTTPStatus.OK,
        {"status": "pending"},
    )


async def test_pairing_expires(
    hass: HomeAssistant, client: TestClient, freezer: FrozenDateTimeFactory
) -> None:
    """Without its code, a request goes away, and so does the discovered watch."""
    pairing = await _async_pair(client)

    freezer.tick(PAIRING_TIMEOUT)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert (await _async_status(client, pairing["request"]))[0] == HTTPStatus.NOT_FOUND


async def test_requests_are_limited(
    hass: HomeAssistant, client: TestClient, freezer: FrozenDateTimeFactory
) -> None:
    """The route is open to anyone: past the limit, it refuses for a while."""
    for _ in range(PAIRING_LIMIT):
        last = await _async_pair(client)

    response = await client.post(PAIR_URL, json={"name": NAME})

    assert response.status == HTTPStatus.TOO_MANY_REQUESTS
    assert (await response.json())["error"] == "too_many_requests"
    # The refused request leaves the pending one alone.
    assert len(hass.config_entries.flow.async_progress_by_handler(DOMAIN)) == 1
    assert (await _async_status(client, last["request"]))[0] == HTTPStatus.OK

    freezer.tick(PAIRING_WINDOW)
    async_fire_time_changed(hass)
    await _async_pair(client)


@pytest.mark.parametrize(
    ("url", "body"),
    [
        pytest.param(PAIR_URL, {}, id="no_name"),
        pytest.param(PAIR_URL, {"name": "   "}, id="blank_name"),
        pytest.param(PAIR_URL, {"name": "x" * 65}, id="long_name"),
        pytest.param(PAIR_URL, {"name": 4}, id="not_a_name"),
        pytest.param(PAIR_URL, {"name": "[Ouvrir](https://x.y)"}, id="link_name"),
        pytest.param(PAIR_URL, {"name": "www.example.com"}, id="domain_name"),
        pytest.param(PAIR_STATUS_URL, {}, id="no_request"),
        pytest.param(PAIR_STATUS_URL, {"request": "x" * 101}, id="long_request"),
    ],
)
async def test_invalid_requests(
    hass: HomeAssistant, client: TestClient, url: str, body: dict[str, Any]
) -> None:
    """A malformed request is refused, and shows nothing in Home Assistant."""
    response = await client.post(url, json=body)

    assert response.status == HTTPStatus.BAD_REQUEST
    assert (await response.json())["error"] == "invalid_request"
    assert not hass.config_entries.flow.async_progress_by_handler(DOMAIN)


@pytest.mark.parametrize("url", [PAIR_URL, PAIR_STATUS_URL])
async def test_invalid_json(client: TestClient, url: str) -> None:
    """A body that is not JSON is refused."""
    response = await client.post(url, data="{")

    assert response.status == HTTPStatus.BAD_REQUEST
    assert (await response.json())["error"] == "invalid_json"


async def test_unknown_request(client: TestClient) -> None:
    """Without a pairing in progress, no request is known."""
    assert await _async_status(client, "made-up") == (
        HTTPStatus.NOT_FOUND,
        {"error": "unknown_request", "message": None},
    )


@pytest.mark.usefixtures("client")
async def test_flow_of_a_replaced_request_aborts(hass: HomeAssistant) -> None:
    """A request replaced before its flow started shows nothing."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_INTEGRATION_DISCOVERY},
        data={"pairing": Pairing(name=NAME, code="123456", request="stale")},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "expired"
