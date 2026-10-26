"""Config flow for the Zepp OS integration."""

from typing import Any, override

import probatio

from homeassistant.components import webhook
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_ENTITIES, CONF_WEBHOOK_ID
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.network import NoURLAvailableError
from homeassistant.helpers.selector import (
    AreaSelector,
    AreaSelectorConfig,
    AssistPipelineSelector,
    EntitySelector,
    EntitySelectorConfig,
)

from .const import CONF_AREAS, CONF_FAVORITES, CONF_PIPELINE, DOMAIN

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


def _webhook_url(hass: HomeAssistant, webhook_id: str) -> str:
    """The address to paste in the watch app: the phone calls it from anywhere."""
    try:
        return webhook.async_generate_url(hass, webhook_id)
    except NoURLAvailableError:
        return webhook.async_generate_path(webhook_id)


class ZeppConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a watch; each one gets its own webhook."""

    VERSION = 1

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm, then show the address the watch app calls."""
        if user_input is None:
            return self.async_show_form(step_id="user")
        webhook_id = webhook.async_generate_id()
        return self.async_create_entry(
            title=TITLE,
            data={CONF_WEBHOOK_ID: webhook_id},
            description_placeholders={"url": _webhook_url(self.hass, webhook_id)},
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
            description_placeholders={
                "url": _webhook_url(self.hass, self.config_entry.data[CONF_WEBHOOK_ID])
            },
        )
