"""Fixtures for the Zepp OS integration tests."""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from aiohttp import ClientResponse
from aiohttp.test_utils import TestClient
import pytest

from homeassistant.components.conversation import DOMAIN as CONVERSATION_DOMAIN
from homeassistant.components.cover import CoverEntityFeature
from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
from homeassistant.components.zepp.const import CONF_AREAS, CONF_FAVORITES, DOMAIN
from homeassistant.const import CONF_ENTITIES, CONF_WEBHOOK_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.setup import async_setup_component

from tests.common import MockConfigEntry
from tests.typing import ClientSessionGenerator

WEBHOOK_ID = "0123456789abcdef" * 4
WEBHOOK_PATH = f"/api/webhook/{WEBHOOK_ID}"
FAVORITES = ["script.maison_bonne_nuit", "light.salon_plafonnier"]
ENTITIES = [
    "climate.salon_poele_thermostat",
    "light.salon_plafonnier",
    "cover.salon_volet",
    "media_player.salon_tv",
    "light.salon_lampe",
    "sensor.cuisine_temperature",
    "binary_sensor.cuisine_fenetre",
    "lock.entree_porte",
]

type Post = Callable[[Any], Awaitable[ClientResponse]]


@pytest.fixture(autouse=True)
def mock_tts_cache_dir_autouse(mock_tts_cache_dir: Path) -> None:
    """Keep the cache of tts, a dependency of assist_pipeline, out of the config dir."""


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """A watch with two favorites, then its entities by area, the kitchen first."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Balance",
        data={CONF_WEBHOOK_ID: WEBHOOK_ID},
        options={
            CONF_FAVORITES: FAVORITES,
            CONF_ENTITIES: ENTITIES,
            CONF_AREAS: ["cuisine"],
        },
    )


@pytest.fixture
async def client(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    mock_config_entry: MockConfigEntry,
) -> TestClient:
    """Set the watch up; the phone calls without Home Assistant credentials."""
    assert await async_setup_component(hass, "homeassistant", {})
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    return await hass_client_no_auth()


@pytest.fixture
def post(client: TestClient) -> Post:
    """Return what the phone calls to post a request to the webhook."""

    async def _post(body: Any) -> ClientResponse:
        return await client.post(WEBHOOK_PATH, json=body)

    return _post


@pytest.fixture
async def house(
    hass: HomeAssistant,
    area_registry: ar.AreaRegistry,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """A living room and a kitchen; what is exposed to Assist is set explicitly."""
    assert await async_setup_component(hass, "homeassistant", {})
    devices_entry = MockConfigEntry(domain="test")
    devices_entry.add_to_hass(hass)
    salon = area_registry.async_create("Salon")
    cuisine = area_registry.async_create("Cuisine")

    def add(
        entity_id: str,
        state: str,
        attributes: dict[str, Any],
        *,
        exposed: bool = True,
        area_id: str | None = None,
        device_area_id: str | None = None,
        **registry: Any,
    ) -> None:
        domain, object_id = entity_id.split(".")
        device_id = None
        if device_area_id is not None:
            device = device_registry.async_get_or_create(
                config_entry_id=devices_entry.entry_id,
                identifiers={("test", object_id)},
            )
            device_registry.async_update_device(device.id, area_id=device_area_id)
            device_id = device.id
        entity_registry.async_get_or_create(
            domain,
            "test",
            object_id,
            suggested_object_id=object_id,
            device_id=device_id,
            **registry,
        )
        registry_entry = entity_registry.async_update_entity(entity_id, area_id=area_id)
        # A disabled entity has no state, like in Home Assistant.
        if registry_entry.disabled_by is None:
            hass.states.async_set(entity_id, state, attributes)
        async_expose_entity(hass, CONVERSATION_DOMAIN, entity_id, exposed)

    add(
        "light.salon_plafonnier",
        "on",
        {"friendly_name": "Salon Plafonnier"},
        device_area_id=salon.id,
    )
    add(
        "cover.salon_volet",
        "open",
        {
            "friendly_name": "Salon Volet",
            "current_position": 40,
            "supported_features": CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION,
        },
        area_id=salon.id,
    )
    add(
        "climate.salon_poele_thermostat",
        "heat",
        {
            "friendly_name": "Salon Poêle Thermostat",
            "current_temperature": 20.5,
            "temperature": 21.0,
            "min_temp": 7,
            "max_temp": 21.2,
        },
        device_area_id=salon.id,
    )
    add(
        "media_player.salon_tv",
        "unavailable",
        {"friendly_name": "Salon TV"},
        area_id=salon.id,
    )
    add(
        "light.salon_lampe",
        "off",
        {"friendly_name": "Salon Lampe"},
        area_id=salon.id,
        disabled_by=er.RegistryEntryDisabler.USER,
    )
    add(
        "sensor.cuisine_temperature",
        "19.456",
        {
            "friendly_name": "Cuisine Température",
            "device_class": "temperature",
            "unit_of_measurement": "°C",
        },
        area_id=cuisine.id,
    )
    entity_registry.async_update_entity_options(
        "sensor.cuisine_temperature", "sensor", {"suggested_display_precision": 1}
    )
    add(
        "binary_sensor.cuisine_fenetre",
        "on",
        {"friendly_name": "Cuisine Fenêtre", "device_class": "window"},
        area_id=cuisine.id,
    )
    # Chosen in Home Assistant, though not exposed to Assist.
    add(
        "lock.entree_porte",
        "locked",
        {"friendly_name": "Entrée Porte"},
        exposed=False,
    )
    add("switch.garage_prise", "off", {"friendly_name": "Garage Prise"})
    add(
        "fan.chambre_ventilateur",
        "off",
        {"friendly_name": "Chambre Ventilateur"},
        exposed=False,
    )
    hass.states.async_set(
        "script.maison_bonne_nuit", "off", {"friendly_name": "Maison Bonne nuit"}
    )
    async_expose_entity(hass, CONVERSATION_DOMAIN, "script.maison_bonne_nuit", True)
