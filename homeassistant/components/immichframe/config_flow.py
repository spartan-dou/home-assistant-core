"""Config flow for the ImmichFrame integration."""

import logging
from typing import Any

import voluptuous as vol

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

from .api import ImmichFrameClient, ImmichFrameConnectionError
from .const import CONF_SENSORS, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_URL): TextSelector(
            TextSelectorConfig(type=TextSelectorType.URL)
        ),
        vol.Optional(CONF_API_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_SENSORS, default=[]): ObjectSelector(
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


class ImmichFrameConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a frame by its address."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the address of the frame and check that it answers."""
        errors: dict[str, str] = {}
        if user_input is not None:
            url = user_input[CONF_URL].rstrip("/")
            self._async_abort_entries_match({CONF_URL: url})
            client = ImmichFrameClient(
                async_get_clientsession(self.hass), url, user_input.get(CONF_API_KEY)
            )
            try:
                await client.get_memories()
            except ImmichFrameConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error while reaching the frame")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title="ImmichFrame", data={**user_input, CONF_URL: url}
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
    def async_get_options_flow(config_entry: ConfigEntry) -> ImmichFrameOptionsFlow:
        """Return the options flow."""
        return ImmichFrameOptionsFlow()


class ImmichFrameOptionsFlow(OptionsFlowWithReload):
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
