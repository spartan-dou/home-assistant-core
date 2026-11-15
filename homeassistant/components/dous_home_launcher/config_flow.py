"""Config flow for the Dou's Home Launcher integration."""

import logging
from typing import Any, override

import probatio

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_API_KEY, CONF_ENTITY_ID, CONF_ICON, CONF_URL
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    ObjectSelector,
    ObjectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import LauncherAuthError, LauncherClient, LauncherConnectionError
from .const import CONF_SENSORS, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_URL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        ),
        probatio.Required(CONF_API_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)

OPTIONS_SCHEMA = probatio.Schema(
    {
        probatio.Optional(CONF_SENSORS, default=[]): ObjectSelector(
            ObjectSelectorConfig(
                multiple=True,
                label_field=CONF_ENTITY_ID,
                fields={
                    CONF_ENTITY_ID: {
                        "label": "Entity",
                        "required": True,
                        "selector": {"entity": {}},
                    },
                    CONF_ICON: {"label": "Emoji", "selector": {"text": {}}},
                },
            )
        ),
    }
)


class LauncherConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a frame by its address and key, both shown in its settings."""

    VERSION = 1

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the address and the key, and check them with the frame."""
        errors: dict[str, str] = {}
        if user_input is not None:
            url = user_input[CONF_URL].rstrip("/")
            key = user_input[CONF_API_KEY].strip().upper()
            client = LauncherClient(async_get_clientsession(self.hass), url, key)
            try:
                state = await client.get_state()
            except LauncherAuthError:
                errors["base"] = "invalid_auth"
            except LauncherConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error while reaching the frame")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(state["id"])
                self._abort_if_unique_id_configured(updates={CONF_URL: url})
                return self.async_create_entry(
                    title=state["name"], data={CONF_URL: url, CONF_API_KEY: key}
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    @override
    def async_get_options_flow(config_entry: ConfigEntry) -> LauncherOptionsFlow:
        """Return the options flow."""
        return LauncherOptionsFlow()


class LauncherOptionsFlow(OptionsFlowWithReload):
    """Choose the entities shown under the clock."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the list of entities and their emoji; the selector validates the entities."""
        if user_input is not None:
            sensors = [
                {
                    CONF_ENTITY_ID: sensor[CONF_ENTITY_ID],
                    CONF_ICON: str(sensor.get(CONF_ICON) or "").strip(),
                }
                for sensor in user_input.get(CONF_SENSORS, [])
            ]
            return self.async_create_entry(data={CONF_SENSORS: sensors})

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
