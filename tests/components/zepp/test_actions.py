"""Tests for the actions the watch runs."""

from http import HTTPStatus
from typing import Any

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .conftest import Post

from tests.common import async_mock_service

pytestmark = pytest.mark.usefixtures("house")


@pytest.mark.parametrize(
    ("entity_id", "action", "service", "data"),
    [
        pytest.param("light.salon_plafonnier", "toggle", "toggle", {}, id="toggle"),
        pytest.param("cover.salon_volet", "stop", "stop_cover", {}, id="cover"),
        pytest.param(
            "climate.salon_poele_thermostat",
            "down",
            "set_temperature",
            {"temperature": 20.5},
            id="setpoint_down",
        ),
        pytest.param(
            "climate.salon_poele_thermostat",
            "up",
            "set_temperature",
            {"temperature": 21.2},
            id="setpoint_up_to_max",
        ),
        pytest.param("script.maison_bonne_nuit", "run", "turn_on", {}, id="favorite"),
    ],
)
async def test_action(
    hass: HomeAssistant,
    post: Post,
    entity_id: str,
    action: str,
    service: str,
    data: dict[str, Any],
) -> None:
    """An action calls its service on the entity, and answers with the tile."""
    calls = async_mock_service(hass, entity_id.split(".", maxsplit=1)[0], service)

    response = await post({"type": "action", "entity_id": entity_id, "action": action})

    assert response.status == HTTPStatus.OK
    assert (await response.json())["tile"]["id"] == entity_id
    assert len(calls) == 1
    assert calls[0].data == {"entity_id": entity_id, **data}


@pytest.mark.parametrize(
    ("entity_id", "action", "status", "error"),
    [
        pytest.param(
            "switch.garage_prise",
            "toggle",
            HTTPStatus.FORBIDDEN,
            "not_watched",
            id="not_shown",
        ),
        pytest.param(
            "light.salon_lampe",
            "toggle",
            HTTPStatus.FORBIDDEN,
            "not_watched",
            id="disabled",
        ),
        pytest.param(
            "light.absente", "toggle", HTTPStatus.FORBIDDEN, "not_watched", id="absent"
        ),
        pytest.param(
            "lock.entree_porte",
            "unlock",
            HTTPStatus.BAD_REQUEST,
            "unsupported_action",
            id="lock_read_only",
        ),
        pytest.param(
            "media_player.salon_tv",
            "play_pause",
            HTTPStatus.BAD_REQUEST,
            "unsupported_action",
            id="unavailable",
        ),
    ],
)
async def test_action_refused(
    hass: HomeAssistant,
    post: Post,
    entity_id: str,
    action: str,
    status: HTTPStatus,
    error: str,
) -> None:
    """Only the actions of watched tiles run: nothing else is called."""
    calls = async_mock_service(hass, entity_id.split(".", maxsplit=1)[0], action)

    response = await post({"type": "action", "entity_id": entity_id, "action": action})

    assert response.status == status
    assert (await response.json())["error"] == error
    assert calls == []


async def test_action_failed(hass: HomeAssistant, post: Post) -> None:
    """A service that fails tells the watch why."""
    async_mock_service(
        hass, "light", "toggle", raise_exception=HomeAssistantError("Zigbee timeout")
    )

    response = await post(
        {"type": "action", "entity_id": "light.salon_plafonnier", "action": "toggle"}
    )

    assert response.status == HTTPStatus.UNPROCESSABLE_ENTITY
    assert await response.json() == {
        "error": "action_failed",
        "message": "Zigbee timeout",
    }


@pytest.mark.parametrize(
    ("entity_id", "action", "value", "service", "data"),
    [
        pytest.param(
            "cover.salon_volet",
            "position",
            65,
            "set_cover_position",
            {"position": 65},
            id="cover_position",
        ),
        pytest.param(
            "climate.salon_poele_thermostat",
            "temperature",
            19.7,
            "set_temperature",
            {"temperature": 19.5},
            id="setpoint_snapped_to_step",
        ),
    ],
)
async def test_control(
    hass: HomeAssistant,
    post: Post,
    entity_id: str,
    action: str,
    value: float,
    service: str,
    data: dict[str, Any],
) -> None:
    """The crown sets a value, rounded to the step the entity takes."""
    calls = async_mock_service(hass, entity_id.split(".", maxsplit=1)[0], service)

    response = await post(
        {"type": "action", "entity_id": entity_id, "action": action, "value": value}
    )

    assert response.status == HTTPStatus.OK
    assert [call.data for call in calls] == [{"entity_id": entity_id, **data}]


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"action": "temperature", "value": 30}, id="above_max"),
        pytest.param({"action": "temperature", "value": 2}, id="below_min"),
        pytest.param({"action": "temperature"}, id="no_value"),
    ],
)
async def test_control_out_of_range(
    hass: HomeAssistant, post: Post, body: dict[str, Any]
) -> None:
    """A value the entity does not take is refused, nothing is called."""
    calls = async_mock_service(hass, "climate", "set_temperature")

    response = await post(
        {"type": "action", "entity_id": "climate.salon_poele_thermostat", **body}
    )

    assert response.status == HTTPStatus.BAD_REQUEST
    assert (await response.json())["error"] == "out_of_range"
    assert not calls
