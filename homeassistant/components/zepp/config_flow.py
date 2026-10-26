"""Config flow for the Zepp OS integration."""

import secrets
from typing import Any, override

import probatio

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_API_KEY, CONF_ENTITIES
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.selector import (
    AreaSelector,
    AreaSelectorConfig,
    AssistPipelineSelector,
    EntitySelector,
    EntitySelectorConfig,
)

from .const import CONF_AREAS, CONF_FAVORITES, CONF_PIPELINE, DOMAIN, URL

TITLE = "Zepp OS"

OPTIONS_SCHEMA = probatio.Schema(
    {
        probatio.Optional(CONF_FAVORITES, default=[]): EntitySelector(
            EntitySelectorConfig(multiple=True, reorder=True)
        ),
        probatio.Optional(CONF_ENTITIES, default=[]): EntitySelector(
            EntitySelectorConfig(multiple=True, reorder=True)
        ),
        probatio.Optional(CONF_AREAS, default=[]): AreaSelector(
            AreaSelectorConfig(multiple=True, reorder=True)
        ),
        probatio.Optional(CONF_PIPELINE): AssistPipelineSelector(),
    }
)


def _placeholders(hass: HomeAssistant, key: str) -> dict[str, str]:
    """The address and the key to paste in the watch app; the phone calls from anywhere."""
    try:
        base = get_url(hass, allow_cloud=False, prefer_external=True)
    except NoURLAvailableError:
        base = ""
    return {"url": f"{base}{URL}", "key": key}


class ZeppConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a watch; each one gets its own key."""

    VERSION = 2

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm, then show the address and the key the watch app needs."""
        if user_input is None:
            return self.async_show_form(step_id="user")
        key = secrets.token_hex(32)
        return self.async_create_entry(
            title=TITLE,
            data={CONF_API_KEY: key},
            description_placeholders=_placeholders(self.hass, key),
        )

    @staticmethod
    @callback
    @override
    def async_get_options_flow(config_entry: ConfigEntry) -> ZeppOptionsFlow:
        """Return the options flow."""
        return ZeppOptionsFlow()


class ZeppOptionsFlow(OptionsFlow):
    """Choose what the watch shows; read on every request, so no reload."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit the favorites, the entities, the order of the areas and the pipeline."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
            description_placeholders=_placeholders(
                self.hass, self.config_entry.data[CONF_API_KEY]
            ),
        )
