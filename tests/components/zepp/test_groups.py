"""Tests for the groups: all the lights or switches of an area, a label, or both."""

from http import HTTPStatus
from typing import Any

import pytest

from homeassistant.components.zepp.const import CONF_GROUPS
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er, label_registry as lr

from .conftest import Post

from tests.common import MockConfigEntry, async_mock_service

pytestmark = pytest.mark.usefixtures("house")

SALON = {
    "id": "salon",
    "name": "Lumières du salon",
    "domain": "light",
    "area_id": "salon",
}


@pytest.fixture
def noel(label_registry: lr.LabelRegistry, entity_registry: er.EntityRegistry) -> str:
    """A label on the garage socket only."""
    label = label_registry.async_create("Noël")
    entity_registry.async_update_entity("switch.garage_prise", labels={label.label_id})
    return label.label_id


async def _async_set(post: Post, groups: list[dict[str, Any]]) -> Any:
    return await post({"type": "groups", "groups": groups})


async def test_group_of_an_area(post: Post, mock_config_entry: MockConfigEntry) -> None:
    """A group of an area shows on the shortcuts page, on if any member is."""
    response = await _async_set(post, [SALON])

    assert response.status == HTTPStatus.OK
    assert mock_config_entry.options[CONF_GROUPS] == [SALON]
    pages = (await (await post({"type": "pages"})).json())["pages"]
    [shortcuts] = [page for page in pages if page["kind"] == "shortcuts"]
    # The disabled lamp of the living room has no state: only the ceiling light.
    assert shortcuts["tiles"] == [
        {
            "id": "group:salon",
            "group": "salon",
            "name": "Lumières du salon",
            "domain": "light",
            "available": True,
            "on": True,
            "members": 1,
            "members_on": 1,
            "actions": ["toggle"],
        }
    ]


async def test_run_group_turns_all_off_when_any_is_on(
    hass: HomeAssistant, post: Post
) -> None:
    """A touch turns everything off when anything is on."""
    calls = async_mock_service(hass, "light", "turn_off")
    await _async_set(post, [SALON])

    response = await post({"type": "group", "id": "salon"})

    assert response.status == HTTPStatus.OK
    assert [call.data for call in calls] == [{"entity_id": ["light.salon_plafonnier"]}]


async def test_group_of_a_label(hass: HomeAssistant, post: Post, noel: str) -> None:
    """A label gathers what carries it, whatever its area, here turned on."""
    calls = async_mock_service(hass, "switch", "turn_on")
    await _async_set(
        post, [{"id": "noel", "name": "Noël", "domain": "switch", "label_id": noel}]
    )

    response = await post({"type": "group", "id": "noel"})

    assert response.status == HTTPStatus.OK
    assert [call.data for call in calls] == [{"entity_id": ["switch.garage_prise"]}]


async def test_area_and_label_meet(post: Post, noel: str) -> None:
    """With both, a member is in the area and carries the label: here none."""
    await _async_set(post, [{**SALON, "label_id": noel}])

    response = await post({"type": "group", "id": "salon"})

    assert response.status == HTTPStatus.UNPROCESSABLE_ENTITY
    assert (await response.json())["error"] == "empty_group"


@pytest.mark.parametrize(
    ("groups", "error"),
    [
        pytest.param([{**SALON, "area_id": "grenier"}], "unknown_target", id="area"),
        pytest.param([{**SALON, "label_id": "inconnue"}], "unknown_target", id="label"),
        pytest.param(
            [{key: value for key, value in SALON.items() if key != "area_id"}],
            "invalid_request",
            id="no_target",
        ),
        pytest.param([{**SALON, "domain": "cover"}], "invalid_request", id="domain"),
        pytest.param([SALON, SALON], "invalid_request", id="duplicate_id"),
    ],
)
async def test_invalid_groups(
    post: Post,
    mock_config_entry: MockConfigEntry,
    groups: list[dict[str, Any]],
    error: str,
) -> None:
    """A group without a known target is refused, and nothing changes."""
    response = await _async_set(post, groups)

    assert response.status == HTTPStatus.BAD_REQUEST
    assert (await response.json())["error"] == error
    assert CONF_GROUPS not in mock_config_entry.options


async def test_unknown_group_is_refused(post: Post) -> None:
    """Only the groups of this watch run."""
    response = await post({"type": "group", "id": "inconnu"})

    assert response.status == HTTPStatus.FORBIDDEN
    assert (await response.json())["error"] == "not_watched"


@pytest.mark.parametrize(
    ("entity_id", "status"),
    [
        pytest.param("cover.salon_volet", HTTPStatus.OK, id="watched"),
        pytest.param("switch.garage_prise", HTTPStatus.FORBIDDEN, id="not_watched"),
    ],
)
async def test_single_tile(post: Post, entity_id: str, status: HTTPStatus) -> None:
    """The watch follows a moving cover tile by tile, only those it shows."""
    response = await post({"type": "tile", "entity_id": entity_id})

    assert response.status == status


async def test_group_placed_in_an_area_and_ordered(
    post: Post, mock_config_entry: MockConfigEntry
) -> None:
    """Placed in its area, a group mixes with its entities, in the phone's order."""
    await _async_set(post, [{**SALON, "room": "salon"}])
    response = await post(
        {"type": "order", "order": ["cover.salon_volet", "group:salon"]}
    )
    assert response.status == HTTPStatus.OK

    pages = (await (await post({"type": "pages"})).json())["pages"]

    assert "shortcuts" not in [page["kind"] for page in pages]
    [salon] = [page for page in pages if page.get("name") == "Salon"]
    # Ordered first, then the others as the options list them.
    assert [tile["id"] for tile in salon["tiles"]] == [
        "cover.salon_volet",
        "group:salon",
        "climate.salon_poele_thermostat",
        "light.salon_plafonnier",
        "media_player.salon_tv",
    ]
    catalog = await (await post({"type": "catalog"})).json()
    assert catalog["order"] == ["cover.salon_volet", "group:salon"]


async def test_group_in_an_unknown_room_is_refused(post: Post) -> None:
    """A group shows in an area that exists, or on the shortcuts page."""
    response = await _async_set(post, [{**SALON, "room": "grenier"}])

    assert response.status == HTTPStatus.BAD_REQUEST
    assert (await response.json())["error"] == "unknown_target"
