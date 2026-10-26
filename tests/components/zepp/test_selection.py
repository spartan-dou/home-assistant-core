"""Tests for choosing, from the phone, what the watch shows."""

from http import HTTPStatus

import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.zepp.const import CONF_FAVORITES
from homeassistant.const import CONF_ENTITIES

from .conftest import ENTITIES, FAVORITES, Post

from tests.common import MockConfigEntry

pytestmark = pytest.mark.usefixtures("house")


async def test_catalog(post: Post, snapshot: SnapshotAssertion) -> None:
    """The entities exposed to Assist, by area then name, and what is chosen."""
    response = await post({"type": "catalog"})

    assert response.status == HTTPStatus.OK
    assert await response.json() == snapshot


async def test_select(post: Post, mock_config_entry: MockConfigEntry) -> None:
    """An exposed entity comes in; one chosen in Home Assistant may stay, once."""
    selection = {
        CONF_FAVORITES: ["switch.garage_prise"],
        CONF_ENTITIES: [
            "lock.entree_porte",
            "switch.garage_prise",
            "lock.entree_porte",
        ],
    }

    response = await post({"type": "select", **selection})

    expected = {
        CONF_FAVORITES: ["switch.garage_prise"],
        CONF_ENTITIES: ["lock.entree_porte", "switch.garage_prise"],
    }
    assert response.status == HTTPStatus.OK
    assert await response.json() == {"selection": expected}
    assert {key: mock_config_entry.options[key] for key in expected} == expected


async def test_select_refuses_unexposed(
    post: Post, mock_config_entry: MockConfigEntry
) -> None:
    """An entity Assist cannot reach cannot be added from the phone."""
    response = await post(
        {
            "type": "select",
            CONF_FAVORITES: FAVORITES,
            CONF_ENTITIES: [*ENTITIES, "fan.chambre_ventilateur"],
        }
    )

    assert response.status == HTTPStatus.FORBIDDEN
    assert await response.json() == {
        "error": "not_exposed",
        "message": "fan.chambre_ventilateur",
    }
    assert mock_config_entry.options[CONF_ENTITIES] == ENTITIES
