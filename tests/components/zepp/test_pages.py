"""Tests for the pages the watch shows."""

from http import HTTPStatus

import pytest
from syrupy.assertion import SnapshotAssertion

from homeassistant.components.zepp.const import CONF_LABEL
from homeassistant.core import HomeAssistant

from .conftest import Post

from tests.common import MockConfigEntry


@pytest.mark.usefixtures("house")
async def test_pages(post: Post, snapshot: SnapshotAssertion) -> None:
    """Favorites in their order, the kitchen as chosen, then the living room, then the rest.

    Names on an area page drop the area, disabled and unlabelled entities stay out,
    a lock has no action.
    """
    response = await post({"type": "pages"})

    assert response.status == HTTPStatus.OK
    assert await response.json() == snapshot


@pytest.mark.usefixtures("house")
async def test_pages_without_label(
    hass: HomeAssistant, post: Post, mock_config_entry: MockConfigEntry
) -> None:
    """Without a label, the watch only gets its favorites."""
    hass.config_entries.async_update_entry(
        mock_config_entry,
        options={
            key: value
            for key, value in mock_config_entry.options.items()
            if key != CONF_LABEL
        },
    )

    response = await post({"type": "pages"})

    assert [page["kind"] for page in (await response.json())["pages"]] == ["favorites"]
