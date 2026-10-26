"""Tests for the shortcuts: scripts with values fixed on the phone."""

from http import HTTPStatus
from typing import Any

import pytest

from homeassistant.components.conversation import DOMAIN as CONVERSATION_DOMAIN
from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
from homeassistant.components.zepp.const import CONF_FAVORITES, CONF_SHORTCUTS
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.service import async_set_service_schema
from homeassistant.setup import async_setup_component

from .conftest import Post

from tests.common import MockConfigEntry, async_mock_service

ARROSAGE = "script.arrosage"
FIELDS = {
    "duree": {
        "name": "Durée",
        "required": True,
        "default": 10,
        "selector": {"number": {"min": 1, "max": 60, "unit_of_measurement": "min"}},
    },
    "zone": {"selector": {"select": {"options": ["jardin", "potager"]}}},
}
SHORTCUT = {
    "id": "arrosage10",
    "name": "Arroser 10 min",
    "entity_id": ARROSAGE,
    "variables": {"duree": 10, "zone": "jardin"},
}


@pytest.fixture(autouse=True)
async def arrosage(hass: HomeAssistant, entity_registry: er.EntityRegistry) -> None:
    """A script with fields, exposed to Assist, whose key is not its object id."""
    assert await async_setup_component(hass, "homeassistant", {})
    entity_registry.async_get_or_create(
        "script", "script", "arroser", suggested_object_id="arrosage"
    )
    hass.states.async_set(ARROSAGE, "off", {"friendly_name": "Arrosage"})
    # Like the script integration: a service per script, named after its key.
    async_mock_service(hass, "script", "arroser")
    async_set_service_schema(
        hass, "script", "arroser", {"name": "Arrosage", "fields": FIELDS}
    )
    async_expose_entity(hass, CONVERSATION_DOMAIN, ARROSAGE, True)


async def _async_set(post: Post, shortcuts: list[dict[str, Any]]) -> Any:
    return await post({"type": "shortcuts", "shortcuts": shortcuts})


@pytest.mark.usefixtures("house")
async def test_catalog_describes_script_fields(post: Post) -> None:
    """The phone builds its form from the fields the script declares."""
    body = await (await post({"type": "catalog"})).json()

    [script] = [item for item in body["catalog"] if item["id"] == ARROSAGE]
    assert script["fields"] == [
        {
            "key": "duree",
            "name": "Durée",
            "required": True,
            "default": 10,
            "selector": FIELDS["duree"]["selector"],
        },
        {
            "key": "zone",
            "name": "zone",
            "required": False,
            "default": None,
            "selector": FIELDS["zone"]["selector"],
        },
    ]
    assert body["shortcuts"] == []


@pytest.mark.usefixtures("house")
async def test_shortcuts_come_after_favorites(
    hass: HomeAssistant, post: Post, mock_config_entry: MockConfigEntry
) -> None:
    """Saved shortcuts get their own page, right after the favorites."""
    response = await _async_set(post, [SHORTCUT])

    assert response.status == HTTPStatus.OK
    assert await response.json() == {"shortcuts": [SHORTCUT]}
    assert mock_config_entry.options[CONF_SHORTCUTS] == [SHORTCUT]
    assert mock_config_entry.options[CONF_FAVORITES]
    pages = (await (await post({"type": "pages"})).json())["pages"]
    assert [page["kind"] for page in pages[:2]] == ["favorites", "shortcuts"]
    assert pages[1]["tiles"] == [
        {
            "id": "shortcut:arrosage10",
            "shortcut": "arrosage10",
            "name": "Arroser 10 min",
            "domain": "script",
            "available": True,
            "on": False,
            "actions": ["run"],
        }
    ]


async def test_run_shortcut(
    hass: HomeAssistant, post: Post, mock_config_entry: MockConfigEntry
) -> None:
    """A touch starts the script with the values fixed on the phone."""
    calls = async_mock_service(hass, "script", "turn_on")
    await _async_set(post, [SHORTCUT])

    response = await post({"type": "shortcut", "id": "arrosage10"})

    assert response.status == HTTPStatus.OK
    assert (await response.json())["tile"]["shortcut"] == "arrosage10"
    assert [call.data for call in calls] == [
        {"entity_id": ARROSAGE, "variables": {"duree": 10, "zone": "jardin"}}
    ]


async def test_unknown_shortcut_is_refused(post: Post) -> None:
    """Only the shortcuts of this watch run."""
    response = await post({"type": "shortcut", "id": "inconnu"})

    assert response.status == HTTPStatus.FORBIDDEN
    assert (await response.json())["error"] == "not_watched"


async def test_unexposed_script_is_refused(hass: HomeAssistant, post: Post) -> None:
    """As for entities, a shortcut runs only a script exposed to Assist."""
    async_expose_entity(hass, CONVERSATION_DOMAIN, ARROSAGE, False)

    response = await _async_set(post, [SHORTCUT])

    assert response.status == HTTPStatus.FORBIDDEN
    assert await response.json() == {"error": "not_exposed", "message": ARROSAGE}


async def test_script_unexposed_later_may_stay(
    hass: HomeAssistant, post: Post, mock_config_entry: MockConfigEntry
) -> None:
    """A shortcut saved while its script was exposed survives a later change."""
    await _async_set(post, [SHORTCUT])
    async_expose_entity(hass, CONVERSATION_DOMAIN, ARROSAGE, False)
    renamed = {**SHORTCUT, "name": "Arroser"}

    response = await _async_set(post, [renamed])

    assert response.status == HTTPStatus.OK
    assert mock_config_entry.options[CONF_SHORTCUTS] == [renamed]


@pytest.mark.parametrize(
    ("shortcuts", "error"),
    [
        pytest.param(
            [{**SHORTCUT, "variables": {"pression": 3}}],
            "unknown_field",
            id="undeclared_field",
        ),
        pytest.param([SHORTCUT, SHORTCUT], "invalid_request", id="duplicate_id"),
        pytest.param(
            [{**SHORTCUT, "entity_id": "light.salon"}],
            "invalid_request",
            id="not_a_script",
        ),
        pytest.param([{**SHORTCUT, "id": "A B"}], "invalid_request", id="bad_id"),
        pytest.param([{**SHORTCUT, "name": " "}], "invalid_request", id="blank_name"),
        pytest.param(
            [{**SHORTCUT, "variables": {"duree": {"min": 1}}}],
            "invalid_request",
            id="nested_value",
        ),
        pytest.param(
            [{**SHORTCUT, "id": f"s{rank}"} for rank in range(51)],
            "invalid_request",
            id="too_many",
        ),
    ],
)
async def test_invalid_shortcuts(
    post: Post,
    mock_config_entry: MockConfigEntry,
    shortcuts: list[dict[str, Any]],
    error: str,
) -> None:
    """A shortcut the script cannot take is refused, and nothing changes."""
    response = await _async_set(post, shortcuts)

    assert response.status == HTTPStatus.BAD_REQUEST
    assert (await response.json())["error"] == error
    assert CONF_SHORTCUTS not in mock_config_entry.options
