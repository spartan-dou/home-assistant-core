"""What the watch shows: pages of tiles, and the actions each tile accepts."""

from collections import defaultdict
import math
from typing import Any

from homeassistant.components.climate import (
    ATTR_CURRENT_TEMPERATURE,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_TARGET_TEMP_STEP,
)
from homeassistant.components.conversation import DOMAIN as CONVERSATION_DOMAIN
from homeassistant.components.cover import ATTR_CURRENT_POSITION, CoverEntityFeature
from homeassistant.components.homeassistant.exposed_entities import async_should_expose
from homeassistant.components.media_player import MediaPlayerEntityFeature
from homeassistant.components.sensor import async_rounded_state
from homeassistant.components.vacuum import VacuumEntityFeature
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_SUPPORTED_FEATURES,
    ATTR_TEMPERATURE,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_ENTITIES,
    PERCENTAGE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    translation,
)

from .const import CONF_AREAS, CONF_FAVORITES, ZeppConfigEntry

type Actions = dict[str, tuple[str, dict[str, Any]]]
type Watched = tuple[State, er.RegistryEntry | None]

ACTIVE_STATES = {
    "auto",
    "cleaning",
    "closing",
    "cool",
    "dry",
    "fan_only",
    "heat",
    "heat_cool",
    "on",
    "open",
    "opening",
    "playing",
}

SIMPLE_ACTIONS: dict[str, tuple[str, str]] = {
    "button": ("press", "press"),
    "fan": ("toggle", "toggle"),
    "humidifier": ("toggle", "toggle"),
    "input_boolean": ("toggle", "toggle"),
    "input_button": ("press", "press"),
    "light": ("toggle", "toggle"),
    "scene": ("run", "turn_on"),
    "script": ("run", "turn_on"),
    "siren": ("toggle", "toggle"),
    "switch": ("toggle", "toggle"),
}

FEATURE_ACTIONS: dict[str, tuple[tuple[str, str, int], ...]] = {
    "cover": (
        ("open", "open_cover", CoverEntityFeature.OPEN),
        ("stop", "stop_cover", CoverEntityFeature.STOP),
        ("close", "close_cover", CoverEntityFeature.CLOSE),
    ),
    "media_player": (
        ("play_pause", "media_play_pause", MediaPlayerEntityFeature.PAUSE),
        ("next", "media_next_track", MediaPlayerEntityFeature.NEXT_TRACK),
    ),
    "vacuum": (
        ("start", "start", VacuumEntityFeature.START),
        ("return", "return_to_base", VacuumEntityFeature.RETURN_HOME),
    ),
}

# Their state is a timestamp or a run flag, nothing worth a line on the watch.
STATELESS_DOMAINS = {"button", "input_button", "scene", "script"}
NUMERIC_DOMAINS = {"input_number", "number", "sensor"}


def tile_actions(hass: HomeAssistant, state: State) -> Actions:
    """Map each action of a tile to the service it calls and its data, the entity aside.

    Locks and alarm panels stay read-only: the key of the watch is its only secret.
    """
    if state.state == STATE_UNAVAILABLE:
        return {}
    return _actions(hass, state)


def _actions(hass: HomeAssistant, state: State) -> Actions:
    if simple := SIMPLE_ACTIONS.get(state.domain):
        action, service = simple
        return {action: (service, {})}
    if state.domain == "climate":
        return _setpoint_actions(hass, state)
    features = state.attributes.get(ATTR_SUPPORTED_FEATURES, 0)
    return {
        action: (service, {})
        for action, service, feature in FEATURE_ACTIONS.get(state.domain, ())
        if features & feature
    }


def _setpoint_actions(hass: HomeAssistant, state: State) -> Actions:
    """Lower or raise a single setpoint by its step, within the entity's bounds."""
    attributes = state.attributes
    if (target := attributes.get(ATTR_TEMPERATURE)) is None:
        return {}
    step = attributes.get(ATTR_TARGET_TEMP_STEP) or (
        0.5 if hass.config.units.temperature_unit == UnitOfTemperature.CELSIUS else 1
    )
    low = attributes.get(ATTR_MIN_TEMP, -math.inf)
    high = attributes.get(ATTR_MAX_TEMP, math.inf)
    return {
        "down": (
            "set_temperature",
            {ATTR_TEMPERATURE: max(low, round(target - step, 2))},
        ),
        "up": (
            "set_temperature",
            {ATTR_TEMPERATURE: min(high, round(target + step, 2))},
        ),
    }


def async_watched_entity_ids(entry: ZeppConfigEntry) -> set[str]:
    """Return the entities the watch shows, and may act on."""
    return {
        *entry.options.get(CONF_FAVORITES, []),
        *entry.options.get(CONF_ENTITIES, []),
    }


def async_exposed_entity_ids(hass: HomeAssistant) -> set[str]:
    """Return the entities exposed to Assist: those the phone may add to the watch.

    Voice messages already reach them with the same key.
    """
    return {state.entity_id for state in _exposed_states(hass)}


async def async_catalog(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Describe the entities exposed to Assist, by area then name, those without last.

    Each says what it is in the language of Home Assistant, and whether the watch
    can act on it, even while unavailable.
    """
    entity_registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    area_registry = ar.async_get(hass)
    states = _exposed_states(hass)
    domains = {state.domain for state in states}
    language = hass.config.language
    kinds = {
        **await translation.async_get_translations(hass, language, "title", domains),
        **await translation.async_get_translations(
            hass, language, "entity_component", domains
        ),
    }
    catalog = []
    for state in states:
        area_id = _area_id(device_registry, entity_registry.async_get(state.entity_id))
        area = None if area_id is None else area_registry.async_get_area(area_id)
        area_name = None if area is None else area.name
        catalog.append(
            {
                "id": state.entity_id,
                "name": _short_name(state.name, area_name),
                "domain": state.domain,
                "device_class": state.attributes.get(ATTR_DEVICE_CLASS),
                "kind": _kind(state, kinds),
                "actionable": bool(_actions(hass, state)),
                "area": area_name,
            }
        )
    return sorted(
        catalog,
        key=lambda item: (
            item["area"] is None,
            (item["area"] or "").casefold(),
            item["name"].casefold(),
        ),
    )


async def async_pages(
    hass: HomeAssistant, entry: ZeppConfigEntry
) -> list[dict[str, Any]]:
    """Favorites first, then a page per area: the chosen ones in order, then by name.

    Within a page, entities keep the order of the options; those without an area
    end on a last page.
    """
    entity_registry = er.async_get(hass)
    favorites: list[Watched] = [
        (state, entity_registry.async_get(entity_id))
        for entity_id in entry.options.get(CONF_FAVORITES, [])
        if (state := hass.states.get(entity_id)) is not None
    ]
    area_registry = ar.async_get(hass)
    device_registry = dr.async_get(hass)
    by_area: defaultdict[str | None, list[Watched]] = defaultdict(list)
    for entity_id in entry.options.get(CONF_ENTITIES, []):
        if (state := hass.states.get(entity_id)) is not None:
            registry_entry = entity_registry.async_get(entity_id)
            by_area[_area_id(device_registry, registry_entry)].append(
                (state, registry_entry)
            )

    translations = await _async_translations(
        hass,
        [*favorites, *(watched for group in by_area.values() for watched in group)],
    )
    pages: list[dict[str, Any]] = []
    if favorites:
        pages.append(
            {
                "kind": "favorites",
                "tiles": [
                    _tile(hass, state, registry_entry, translations, state.name)
                    for state, registry_entry in favorites
                ],
            }
        )
    chosen = entry.options.get(CONF_AREAS, [])
    areas = sorted(
        (
            area
            for area_id in by_area
            if area_id is not None
            and (area := area_registry.async_get_area(area_id)) is not None
        ),
        key=lambda area: (
            chosen.index(area.id) if area.id in chosen else len(chosen),
            area.name.casefold(),
        ),
    )
    pages.extend(
        {
            "kind": "area",
            "name": area.name,
            "tiles": _area_tiles(hass, by_area[area.id], translations, area.name),
        }
        for area in areas
    )
    if None in by_area:
        pages.append(
            {
                "kind": "other",
                "tiles": _area_tiles(hass, by_area[None], translations, None),
            }
        )
    return pages


async def async_tile(hass: HomeAssistant, entity_id: str) -> dict[str, Any] | None:
    """Return a single tile, named in full: the watch keeps the name it shows."""
    if (state := hass.states.get(entity_id)) is None:
        return None
    watched = (state, er.async_get(hass).async_get(entity_id))
    translations = await _async_translations(hass, [watched])
    return _tile(hass, state, watched[1], translations, state.name)


def _exposed_states(hass: HomeAssistant) -> list[State]:
    return [
        state
        for state in hass.states.async_all()
        if async_should_expose(hass, CONVERSATION_DOMAIN, state.entity_id)
    ]


def _area_id(
    device_registry: dr.DeviceRegistry, registry_entry: er.RegistryEntry | None
) -> str | None:
    if registry_entry is None:
        return None
    if registry_entry.area_id is not None or registry_entry.device_id is None:
        return registry_entry.area_id
    device = device_registry.async_get(registry_entry.device_id)
    return None if device is None else device.area_id


async def _async_translations(
    hass: HomeAssistant, watched: list[Watched]
) -> dict[str, str]:
    language = hass.config.language
    translations = await translation.async_get_translations(
        hass, language, "entity_component", {state.domain for state, _ in watched}
    )
    if platforms := {
        registry_entry.platform
        for _, registry_entry in watched
        if registry_entry is not None and registry_entry.translation_key
    }:
        translations = {
            **translations,
            **await translation.async_get_translations(
                hass, language, "entity", platforms
            ),
        }
    return translations


def _area_tiles(
    hass: HomeAssistant,
    watched: list[Watched],
    translations: dict[str, str],
    area_name: str | None,
) -> list[dict[str, Any]]:
    return [
        _tile(
            hass,
            state,
            registry_entry,
            translations,
            _short_name(state.name, area_name),
        )
        for state, registry_entry in watched
    ]


def _kind(state: State, translations: dict[str, str]) -> str:
    """Name what an entity is as the frontend does: device class, then domain."""
    keys = [
        f"component.{state.domain}.entity_component._.name",
        f"component.{state.domain}.title",
    ]
    if device_class := state.attributes.get(ATTR_DEVICE_CLASS):
        keys.insert(0, f"component.{state.domain}.entity_component.{device_class}.name")
    return next(
        (translations[key] for key in keys if key in translations), state.domain
    )


def _short_name(name: str, area_name: str | None) -> str:
    """Drop the area the page already names: « Salon Poêle » reads « Poêle »."""
    if area_name and name.casefold().startswith(f"{area_name.casefold()} "):
        return name[len(area_name) + 1 :]
    return name


def _tile(
    hass: HomeAssistant,
    state: State,
    registry_entry: er.RegistryEntry | None,
    translations: dict[str, str],
    name: str,
) -> dict[str, Any]:
    """Describe an entity as the watch draws it; absent keys have nothing to show.

    Numbers travel as Home Assistant rounds them, the watch adds its decimal mark.
    """
    attributes = state.attributes
    tile: dict[str, Any] = {
        "id": state.entity_id,
        "name": name,
        "domain": state.domain,
        "device_class": attributes.get(ATTR_DEVICE_CLASS),
        "available": state.state != STATE_UNAVAILABLE,
        "on": state.state in ACTIVE_STATES,
        "actions": list(tile_actions(hass, state)),
    }
    if state.domain in NUMERIC_DOMAINS and _is_number(
        value := async_rounded_state(hass, state.entity_id, state)
    ):
        tile["value"] = value
        tile["unit"] = attributes.get(ATTR_UNIT_OF_MEASUREMENT)
    elif state.domain not in STATELESS_DOMAINS:
        tile["state"] = _state_text(state, registry_entry, translations)
    if state.domain == "climate":
        tile["value"] = _number(attributes.get(ATTR_CURRENT_TEMPERATURE))
        tile["target"] = _number(attributes.get(ATTR_TEMPERATURE))
        tile["unit"] = hass.config.units.temperature_unit
    elif state.domain == "cover" and ATTR_CURRENT_POSITION in attributes:
        tile["value"] = _number(attributes[ATTR_CURRENT_POSITION])
        tile["unit"] = PERCENTAGE
    return {key: value for key, value in tile.items() if value is not None}


def _state_text(
    state: State, registry_entry: er.RegistryEntry | None, translations: dict[str, str]
) -> str | None:
    """Translate a state as the frontend does: entity, then device class, then domain."""
    if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return None
    keys = []
    if registry_entry is not None and registry_entry.translation_key:
        keys.append(
            f"component.{registry_entry.platform}.entity.{state.domain}"
            f".{registry_entry.translation_key}.state.{state.state}"
        )
    if device_class := state.attributes.get(ATTR_DEVICE_CLASS):
        keys.append(
            f"component.{state.domain}.entity_component.{device_class}.state.{state.state}"
        )
    keys.append(f"component.{state.domain}.entity_component._.state.{state.state}")
    return next((translations[key] for key in keys if key in translations), state.state)


def _is_number(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


def _number(value: Any) -> str | None:
    """Show a number as Home Assistant writes it, without a trailing .0 on integers."""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)
