"""Tests for the pages the watch shows."""

from http import HTTPStatus

import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.const import CONF_ENTITIES
from homeassistant.core import HomeAssistant

from .conftest import Post

from tests.common import MockConfigEntry


@pytest.mark.usefixtures("house")
async def test_pages(post: Post, snapshot: SnapshotAssertion) -> None:
    """Favorites, the kitchen as chosen, then the living room, then the rest.

    Entities keep their order within a page, names on an area page drop the area,
    a disabled entity stays out, a lock has no action.
    """
    response = await post({"type": "pages"})

    assert response.status == HTTPStatus.OK
    assert await response.json() == snapshot


@pytest.mark.usefixtures("house")
async def test_pages_without_entities(
    hass: HomeAssistant, post: Post, mock_config_entry: MockConfigEntry
) -> None:
    """Without entities, the watch only gets its favorites."""
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={
            key: value
            for key, value in mock_config_entry.options.items()
            if key != CONF_ENTITIES
        },
    )

    response = await post({"type": "pages"})

    assert [page["kind"] for page in (await response.json())["pages"]] == ["favorites"]
