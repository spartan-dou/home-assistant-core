"""The route the phones call: pages, actions, voice, and what to show."""

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

from homeassistant.const import ATTR_ENTITY_ID, CONF_API_KEY, CONF_ENTITIES
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.http import KEY_HASS, HomeAssistantView
from homeassistant.helpers.json import json_dumps

from .const import (
    CONF_FAVORITES,
    DOMAIN,
    MAX_AUDIO_LENGTH,
    MAX_SELECTION,
    URL,
    ZeppConfigEntry,
)
from .tiles import (
    async_catalog,
    async_exposed_entity_ids,
    async_pages,
    async_tile,
    async_watched_entity_ids,
    tile_actions,
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
    if (call := tile_actions(hass, state).get(data["action"])) is None:
        return _error(HTTPStatus.BAD_REQUEST, "unsupported_action")
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


async def _async_catalog(
    hass: HomeAssistant, entry: ZeppConfigEntry, data: dict[str, Any]
) -> Response:
    """What the phone may choose from, and what is chosen."""
    return _json({"catalog": async_catalog(hass), "selection": _selection(entry)})


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
    "pages": (PAGES_SCHEMA, _async_pages),
    "select": (SELECT_SCHEMA, _async_select),
    "voice": (VOICE_SCHEMA, _async_voice),
}


def _json(data: dict[str, Any]) -> Response:
    return json_response(data, dumps=json_dumps)


def _error(status: HTTPStatus, code: str, message: str | None = None) -> Response:
    return json_response(
        {"error": code, "message": message}, status=status, dumps=json_dumps
    )
