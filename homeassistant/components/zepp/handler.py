"""The routes the phones call: pairing, then pages, actions, voice, and what to show."""

import base64
import binascii
from collections.abc import Awaitable, Callable
import hmac
from http import HTTPStatus
import logging
from typing import Any

from aiohttp import hdrs
from aiohttp.web import Request, Response, json_response
import probatio

from homeassistant.components.script import DOMAIN as SCRIPT_DOMAIN
from homeassistant.const import (
    ATTR_AREA_ID,
    ATTR_ENTITY_ID,
    ATTR_LABEL_ID,
    CONF_API_KEY,
    CONF_ENTITIES,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
)
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import (
    area_registry as ar,
    config_validation as cv,
    label_registry as lr,
)
from homeassistant.helpers.http import KEY_HASS, HomeAssistantView
from homeassistant.helpers.json import json_dumps

from .const import (
    CONF_FAVORITES,
    CONF_GROUPS,
    CONF_ORDER,
    CONF_SHORTCUTS,
    DOMAIN,
    GROUP_DOMAINS,
    MAX_AUDIO_LENGTH,
    MAX_NAME_LENGTH,
    MAX_ORDER,
    MAX_SELECTION,
    MAX_SHORTCUTS,
    PAIR_STATUS_URL,
    PAIR_URL,
    PAIRING_TIMEOUT,
    ROOM,
    URL,
    ZeppConfigEntry,
)
from .pairing import DATA_PAIRINGS
from .tiles import (
    async_catalog,
    async_exposed_entity_ids,
    async_group_members,
    async_group_tile,
    async_pages,
    async_script_fields,
    async_shortcut_tile,
    async_targets,
    async_tile,
    async_watched_entity_ids,
    tile_actions,
    tile_control,
)
from .voice import InvalidAudioError, async_ask, decode_opus

_LOGGER = logging.getLogger(__name__)

type Handler = Callable[
    [HomeAssistant, ZeppConfigEntry, dict[str, Any]], Awaitable[Response]
]

PAGES_SCHEMA = probatio.Schema(
    {probatio.Required("type"): "pages"}, extra=probatio.REMOVE_EXTRA
)
ACTION_SCHEMA = probatio.Schema(
    {
        probatio.Required("type"): "action",
        probatio.Required(ATTR_ENTITY_ID): cv.entity_id,
        probatio.Required("action"): str,
        probatio.Optional("value"): probatio.Coerce(float),
    },
    extra=probatio.REMOVE_EXTRA,
)
CATALOG_SCHEMA = probatio.Schema(
    {probatio.Required("type"): "catalog"}, extra=probatio.REMOVE_EXTRA
)
SELECT_SCHEMA = probatio.Schema(
    {
        probatio.Required("type"): "select",
        probatio.Required(CONF_FAVORITES): probatio.All(
            [cv.entity_id], probatio.Length(max=MAX_SELECTION)
        ),
        probatio.Required(CONF_ENTITIES): probatio.All(
            [cv.entity_id], probatio.Length(max=MAX_SELECTION)
        ),
    },
    extra=probatio.REMOVE_EXTRA,
)
SHORTCUT_ID = probatio.All(str, probatio.Match(r"^[a-z0-9]{1,16}$"))
NAME = probatio.All(str, probatio.Strip, probatio.Length(min=1, max=MAX_NAME_LENGTH))
VARIABLE = probatio.Any(str, int, float, bool)
SHORTCUT_SCHEMA = probatio.Schema(
    {
        probatio.Required("id"): SHORTCUT_ID,
        probatio.Required("name"): NAME,
        probatio.Required(ATTR_ENTITY_ID): cv.entity_domain(SCRIPT_DOMAIN),
        probatio.Optional("variables", default={}): {
            str: probatio.Any(VARIABLE, [VARIABLE])
        },
        probatio.Optional(ROOM): str,
    },
    extra=probatio.REMOVE_EXTRA,
)
SHORTCUTS_SCHEMA = probatio.Schema(
    {
        probatio.Required("type"): "shortcuts",
        probatio.Required(CONF_SHORTCUTS): probatio.All(
            [SHORTCUT_SCHEMA], probatio.Length(max=MAX_SHORTCUTS)
        ),
    },
    extra=probatio.REMOVE_EXTRA,
)
GROUP_SCHEMA = probatio.All(
    probatio.Schema(
        {
            probatio.Required("id"): SHORTCUT_ID,
            probatio.Required("name"): NAME,
            probatio.Required("domain"): probatio.In(GROUP_DOMAINS),
            probatio.Optional(ATTR_AREA_ID): str,
            probatio.Optional(ATTR_LABEL_ID): str,
            probatio.Optional(ROOM): str,
        },
        extra=probatio.REMOVE_EXTRA,
    ),
    probatio.AtLeastOne(ATTR_AREA_ID, ATTR_LABEL_ID),
)
GROUPS_SCHEMA = probatio.Schema(
    {
        probatio.Required("type"): "groups",
        probatio.Required(CONF_GROUPS): probatio.All(
            [GROUP_SCHEMA], probatio.Length(max=MAX_SHORTCUTS)
        ),
    },
    extra=probatio.REMOVE_EXTRA,
)
TILE_SCHEMA = probatio.Schema(
    {
        probatio.Required("type"): "tile",
        probatio.Required(ATTR_ENTITY_ID): cv.entity_id,
    },
    extra=probatio.REMOVE_EXTRA,
)
ORDER_SCHEMA = probatio.Schema(
    {
        probatio.Required("type"): "order",
        probatio.Required(CONF_ORDER): probatio.All(
            [probatio.All(str, probatio.Length(max=300))],
            probatio.Length(max=MAX_ORDER),
        ),
    },
    extra=probatio.REMOVE_EXTRA,
)
RUN_GROUP_SCHEMA = probatio.Schema(
    {probatio.Required("type"): "group", probatio.Required("id"): str},
    extra=probatio.REMOVE_EXTRA,
)
RUN_SHORTCUT_SCHEMA = probatio.Schema(
    {probatio.Required("type"): "shortcut", probatio.Required("id"): str},
    extra=probatio.REMOVE_EXTRA,
)
VOICE_SCHEMA = probatio.Schema(
    {
        probatio.Required("type"): "voice",
        probatio.Required("audio"): probatio.All(
            str, probatio.Length(min=1, max=MAX_AUDIO_LENGTH)
        ),
        probatio.Optional("conversation_id"): probatio.Any(str, None),
    },
    extra=probatio.REMOVE_EXTRA,
)

PAIR_SCHEMA = probatio.Schema(
    {
        # Anyone may ask, and the name lands in Markdown: no room for a link.
        probatio.Required("name"): probatio.All(
            str,
            probatio.Strip,
            probatio.Length(min=1, max=MAX_NAME_LENGTH),
            probatio.Match(r"^[\w '()-]+$"),
        )
    },
    extra=probatio.REMOVE_EXTRA,
)
PAIR_STATUS_SCHEMA = probatio.Schema(
    {probatio.Required("request"): probatio.All(str, probatio.Length(max=100))},
    extra=probatio.REMOVE_EXTRA,
)


class ZeppPairView(HomeAssistantView):
    """Where a watch asks to be added: anyone may ask, only its code gets it in."""

    url = PAIR_URL
    name = "api:zepp:pair"
    requires_auth = False

    async def post(self, request: Request) -> Response:
        """Show the watch as discovered; the code goes to the watch, never to the UI."""
        if isinstance(data := await _async_validate(request, PAIR_SCHEMA), Response):
            return data
        pairings = request.app[KEY_HASS].data[DATA_PAIRINGS]
        if (pairing := await pairings.async_start(data["name"])) is None:
            return _error(HTTPStatus.TOO_MANY_REQUESTS, "too_many_requests")
        return _json(
            {
                "request": pairing.request,
                "code": pairing.code,
                "expires_in": PAIRING_TIMEOUT,
            }
        )


class ZeppPairStatusView(HomeAssistantView):
    """Where the phone waits for the key of its watch."""

    url = PAIR_STATUS_URL
    name = "api:zepp:pair:status"
    requires_auth = False

    async def post(self, request: Request) -> Response:
        """Answer pending, or the key once the code was entered."""
        if isinstance(
            data := await _async_validate(request, PAIR_STATUS_SCHEMA), Response
        ):
            return data
        pairings = request.app[KEY_HASS].data[DATA_PAIRINGS]
        if (pairing := pairings.async_get(data["request"])) is None:
            return _error(HTTPStatus.NOT_FOUND, "unknown_request")
        if pairing.key is None:
            return _json({"status": "pending"})
        return _json({"status": "paired", "key": pairing.key})


async def _async_validate(
    request: Request, schema: probatio.Schema
) -> dict[str, Any] | Response:
    """Return the validated body, or the response refusing it."""
    try:
        body = await request.json()
    except ValueError:
        return _error(HTTPStatus.BAD_REQUEST, "invalid_json")
    try:
        return schema(body)
    except probatio.Invalid as err:
        return _error(HTTPStatus.BAD_REQUEST, "invalid_request", str(err))


class ZeppView(HomeAssistantView):
    """The route of all the watches; the key in the request tells which one."""

    url = URL
    name = "api:zepp"
    # The key of a watch takes the place of Home Assistant credentials: it travels
    # in a header, never in the address, so no access log keeps it.
    requires_auth = False

    async def post(self, request: Request) -> Response:
        """Answer the watch whose key comes as a bearer token."""
        hass = request.app[KEY_HASS]
        if (entry := _async_watch(hass, request)) is None:
            return _error(HTTPStatus.UNAUTHORIZED, "unauthorized")
        try:
            body = await request.json()
        except ValueError:
            return _error(HTTPStatus.BAD_REQUEST, "invalid_json")
        if not isinstance(body, dict) or body.get("type") not in COMMANDS:
            return _error(HTTPStatus.BAD_REQUEST, "unknown_type")
        schema, command = COMMANDS[body["type"]]
        try:
            data = schema(body)
        except probatio.Invalid as err:
            return _error(HTTPStatus.BAD_REQUEST, "invalid_request", str(err))
        return await command(hass, entry, data)


def _async_watch(hass: HomeAssistant, request: Request) -> ZeppConfigEntry | None:
    """Return the loaded watch with this key, comparing every key in constant time."""
    scheme, _, key = request.headers.get(hdrs.AUTHORIZATION, "").partition(" ")
    if scheme != "Bearer" or not key:
        return None
    found = None
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        if hmac.compare_digest(entry.data[CONF_API_KEY].encode(), key.encode()):
            found = entry
    return found


async def _async_pages(
    hass: HomeAssistant, entry: ZeppConfigEntry, data: dict[str, Any]
) -> Response:
    return _json({"pages": await async_pages(hass, entry)})


async def _async_action(
    hass: HomeAssistant, entry: ZeppConfigEntry, data: dict[str, Any]
) -> Response:
    """Run an action of a tile; the answer is the tile as it stands right after."""
    entity_id = data[ATTR_ENTITY_ID]
    state = hass.states.get(entity_id)
    if state is None or entity_id not in async_watched_entity_ids(entry):
        return _error(HTTPStatus.FORBIDDEN, "not_watched")
    control = tile_control(hass, state)
    if control is not None and data["action"] == control.action:
        if "value" not in data or (value := control.snap(data["value"])) is None:
            return _error(HTTPStatus.BAD_REQUEST, "out_of_range")
        service, service_data = control.service, control.data(value)
    elif (call := tile_actions(hass, state).get(data["action"])) is None:
        return _error(HTTPStatus.BAD_REQUEST, "unsupported_action")
    else:
        service, service_data = call
    try:
        await hass.services.async_call(
            state.domain,
            service,
            {ATTR_ENTITY_ID: entity_id, **service_data},
            blocking=True,
            context=Context(),
        )
    except (HomeAssistantError, probatio.Invalid) as err:
        _LOGGER.warning("Action %s of %s failed: %s", data["action"], entity_id, err)
        return _error(HTTPStatus.UNPROCESSABLE_ENTITY, "action_failed", str(err))
    return _json({"tile": await async_tile(hass, entity_id)})


async def _async_tile(
    hass: HomeAssistant, entry: ZeppConfigEntry, data: dict[str, Any]
) -> Response:
    """One tile, for the watch to follow a cover while it moves."""
    entity_id = data[ATTR_ENTITY_ID]
    if (
        entity_id not in async_watched_entity_ids(entry)
        or (tile := await async_tile(hass, entity_id)) is None
    ):
        return _error(HTTPStatus.FORBIDDEN, "not_watched")
    return _json({"tile": tile})


async def _async_catalog(
    hass: HomeAssistant, entry: ZeppConfigEntry, data: dict[str, Any]
) -> Response:
    """What the phone may choose from, and what is chosen."""
    return _json(
        {
            "catalog": await async_catalog(hass),
            "selection": _selection(entry),
            CONF_SHORTCUTS: entry.options.get(CONF_SHORTCUTS, []),
            CONF_GROUPS: entry.options.get(CONF_GROUPS, []),
            "members": _group_members(hass, entry.options.get(CONF_GROUPS, [])),
            CONF_ORDER: entry.options.get(CONF_ORDER, []),
            **async_targets(hass),
        }
    )


async def _async_select(
    hass: HomeAssistant, entry: ZeppConfigEntry, data: dict[str, Any]
) -> Response:
    """Replace what the watch shows, as chosen on the phone.

    Only entities exposed to Assist may come in; those already shown may stay, so
    that what was chosen in Home Assistant survives a change made on the phone.
    """
    favorites = list(dict.fromkeys(data[CONF_FAVORITES]))
    entities = list(dict.fromkeys(data[CONF_ENTITIES]))
    allowed = async_exposed_entity_ids(hass) | async_watched_entity_ids(entry)
    if refused := sorted({*favorites, *entities} - allowed):
        return _error(HTTPStatus.FORBIDDEN, "not_exposed", ", ".join(refused))
    hass.config_entries.async_update_entry(
        entry,
        options={**entry.options, CONF_FAVORITES: favorites, CONF_ENTITIES: entities},
    )
    return _json({"selection": _selection(entry)})


async def _async_shortcuts(
    hass: HomeAssistant, entry: ZeppConfigEntry, data: dict[str, Any]
) -> Response:
    """Replace the shortcuts: scripts exposed to Assist, with values for their fields.

    As with entities, a script already in a shortcut may stay once unexposed.
    """
    shortcuts = data[CONF_SHORTCUTS]
    if len({shortcut["id"] for shortcut in shortcuts}) != len(shortcuts):
        return _error(HTTPStatus.BAD_REQUEST, "invalid_request", "duplicate id")
    allowed = async_exposed_entity_ids(hass) | {
        shortcut[ATTR_ENTITY_ID] for shortcut in entry.options.get(CONF_SHORTCUTS, [])
    }
    scripts = {shortcut[ATTR_ENTITY_ID] for shortcut in shortcuts}
    if refused := sorted(scripts - allowed):
        return _error(HTTPStatus.FORBIDDEN, "not_exposed", ", ".join(refused))
    areas = {area.id for area in ar.async_get(hass).async_list_areas()}
    for shortcut in shortcuts:
        if shortcut.get(ROOM) not in {*areas, None}:
            return _error(HTTPStatus.BAD_REQUEST, "unknown_target", shortcut["name"])
        fields = async_script_fields(hass, shortcut[ATTR_ENTITY_ID])
        if unknown := sorted(set(shortcut["variables"]) - set(fields)):
            return _error(
                HTTPStatus.BAD_REQUEST,
                "unknown_field",
                f"{shortcut[ATTR_ENTITY_ID]}: {', '.join(unknown)}",
            )
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_SHORTCUTS: shortcuts}
    )
    return _json({CONF_SHORTCUTS: shortcuts})


async def _async_run_shortcut(
    hass: HomeAssistant, entry: ZeppConfigEntry, data: dict[str, Any]
) -> Response:
    """Start the script of a shortcut with its values."""
    shortcut = next(
        (
            shortcut
            for shortcut in entry.options.get(CONF_SHORTCUTS, [])
            if shortcut["id"] == data["id"]
        ),
        None,
    )
    if shortcut is None:
        return _error(HTTPStatus.FORBIDDEN, "not_watched")
    try:
        await hass.services.async_call(
            SCRIPT_DOMAIN,
            SERVICE_TURN_ON,
            {
                ATTR_ENTITY_ID: shortcut[ATTR_ENTITY_ID],
                "variables": shortcut["variables"],
            },
            blocking=True,
            context=Context(),
        )
    except (HomeAssistantError, probatio.Invalid) as err:
        _LOGGER.warning("Shortcut %s failed: %s", shortcut["name"], err)
        return _error(HTTPStatus.UNPROCESSABLE_ENTITY, "action_failed", str(err))
    return _json({"tile": async_shortcut_tile(hass, shortcut)})


async def _async_groups(
    hass: HomeAssistant, entry: ZeppConfigEntry, data: dict[str, Any]
) -> Response:
    """Replace the groups: all the lights or switches of an area, a label, or both."""
    groups = data[CONF_GROUPS]
    if len({group["id"] for group in groups}) != len(groups):
        return _error(HTTPStatus.BAD_REQUEST, "invalid_request", "duplicate id")
    areas = {area.id for area in ar.async_get(hass).async_list_areas()}
    labels = {label.label_id for label in lr.async_get(hass).async_list_labels()}
    for group in groups:
        # Absent, a target is None: the other one alone decides.
        if (
            group.get(ATTR_AREA_ID) not in {*areas, None}
            or group.get(ATTR_LABEL_ID) not in {*labels, None}
            or group.get(ROOM) not in {*areas, None}
        ):
            return _error(HTTPStatus.BAD_REQUEST, "unknown_target", group["name"])
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_GROUPS: groups}
    )
    return _json({CONF_GROUPS: groups, "members": _group_members(hass, groups)})


async def _async_order(
    hass: HomeAssistant, entry: ZeppConfigEntry, data: dict[str, Any]
) -> Response:
    """Replace the order of the tiles within their pages, as arranged on the phone.

    Only ranks: what a page shows is chosen elsewhere, an unknown key is ignored.
    """
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_ORDER: data[CONF_ORDER]}
    )
    return _json({CONF_ORDER: data[CONF_ORDER]})


async def _async_run_group(
    hass: HomeAssistant, entry: ZeppConfigEntry, data: dict[str, Any]
) -> Response:
    """Turn all the group off if any is on, else all on."""
    group = next(
        (
            group
            for group in entry.options.get(CONF_GROUPS, [])
            if group["id"] == data["id"]
        ),
        None,
    )
    if group is None:
        return _error(HTTPStatus.FORBIDDEN, "not_watched")
    if not (members := async_group_members(hass, group)):
        return _error(HTTPStatus.UNPROCESSABLE_ENTITY, "empty_group")
    tile = async_group_tile(hass, group)
    try:
        await hass.services.async_call(
            group["domain"],
            SERVICE_TURN_OFF if tile["on"] else SERVICE_TURN_ON,
            {ATTR_ENTITY_ID: members},
            blocking=True,
            context=Context(),
        )
    except (HomeAssistantError, probatio.Invalid) as err:
        _LOGGER.warning("Group %s failed: %s", group["name"], err)
        return _error(HTTPStatus.UNPROCESSABLE_ENTITY, "action_failed", str(err))
    return _json({"tile": async_group_tile(hass, group)})


def _group_members(
    hass: HomeAssistant, groups: list[dict[str, Any]]
) -> dict[str, list[str]]:
    """What each group finds, for the phone to show: a label may match nothing."""
    return {group["id"]: async_group_members(hass, group) for group in groups}


def _selection(entry: ZeppConfigEntry) -> dict[str, list[str]]:
    return {
        CONF_FAVORITES: entry.options.get(CONF_FAVORITES, []),
        CONF_ENTITIES: entry.options.get(CONF_ENTITIES, []),
    }


async def _async_voice(
    hass: HomeAssistant, entry: ZeppConfigEntry, data: dict[str, Any]
) -> Response:
    try:
        opus = base64.b64decode(data["audio"], validate=True)
    except binascii.Error:
        return _error(HTTPStatus.BAD_REQUEST, "invalid_audio")
    try:
        pcm = await hass.async_add_executor_job(decode_opus, opus)
    except InvalidAudioError as err:
        return _error(HTTPStatus.UNPROCESSABLE_ENTITY, "invalid_audio", str(err))
    return _json(await async_ask(hass, entry, pcm, data.get("conversation_id")))


COMMANDS: dict[str, tuple[probatio.Schema, Handler]] = {
    "action": (ACTION_SCHEMA, _async_action),
    "catalog": (CATALOG_SCHEMA, _async_catalog),
    "group": (RUN_GROUP_SCHEMA, _async_run_group),
    "groups": (GROUPS_SCHEMA, _async_groups),
    "order": (ORDER_SCHEMA, _async_order),
    "pages": (PAGES_SCHEMA, _async_pages),
    "select": (SELECT_SCHEMA, _async_select),
    "shortcut": (RUN_SHORTCUT_SCHEMA, _async_run_shortcut),
    "shortcuts": (SHORTCUTS_SCHEMA, _async_shortcuts),
    "tile": (TILE_SCHEMA, _async_tile),
    "voice": (VOICE_SCHEMA, _async_voice),
}


def _json(data: dict[str, Any]) -> Response:
    return json_response(data, dumps=json_dumps)


def _error(status: HTTPStatus, code: str, message: str | None = None) -> Response:
    return json_response(
        {"error": code, "message": message}, status=status, dumps=json_dumps
    )
