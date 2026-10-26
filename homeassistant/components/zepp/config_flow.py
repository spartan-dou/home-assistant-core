"""Config flow for the Zepp OS integration."""

import hmac
import secrets
from typing import Any, override

import probatio

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_API_KEY, CONF_CODE, CONF_ENTITIES
from homeassistant.core import callback
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.helpers.selector import (
    AreaSelector,
    AreaSelectorConfig,
    AssistPipelineSelector,
    EntitySelector,
    EntitySelectorConfig,
)
from homeassistant.helpers.typing import DiscoveryInfoType

from .const import CONF_AREAS, CONF_FAVORITES, CONF_PIPELINE, DOMAIN, PHONE_OPTIONS
from .pairing import DATA_PAIRINGS, Pairing

CONFIRM_SCHEMA = probatio.Schema({probatio.Required(CONF_CODE): str})

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


class ZeppConfigFlow(ConfigFlow, domain=DOMAIN):
    """A watch asks from its phone; the code it shows approves it."""

    VERSION = 2

    _pairing: Pairing

    @override
    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Watches are added from their app: say how."""
        try:
            url = get_url(self.hass, allow_cloud=False, prefer_external=True)
        except NoURLAvailableError:
            url = "https://…"
        return self.async_abort(
            reason="pair_from_watch", description_placeholders={"url": url}
        )

    @override
    async def async_step_integration_discovery(
        self, discovery_info: DiscoveryInfoType
    ) -> ConfigFlowResult:
        """A watch asked to be added from its phone."""
        pairing: Pairing = discovery_info["pairing"]
        if not self.hass.data[DATA_PAIRINGS].async_attach(pairing, self.flow_id):
            return self.async_abort(reason="expired")
        self._pairing = pairing
        self.context["title_placeholders"] = {"name": pairing.name}
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Enter the code the watch shows: a request from anyone else cannot pass."""
        errors: dict[str, str] = {}
        if user_input is not None:
            code = user_input[CONF_CODE].replace(" ", "").encode()
            if hmac.compare_digest(code, self._pairing.code.encode()):
                key = self._pairing.key = secrets.token_hex(32)
                return self.async_create_entry(
                    title=self._pairing.name, data={CONF_API_KEY: key}
                )
            errors[CONF_CODE] = "invalid_code"
        return self.async_show_form(
            step_id="confirm",
            data_schema=CONFIRM_SCHEMA,
            errors=errors,
            description_placeholders={"name": self._pairing.name},
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
            options = self.config_entry.options
            return self.async_create_entry(
                data={
                    **user_input,
                    **{key: options.get(key, []) for key in PHONE_OPTIONS},
                }
            )
        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, self.config_entry.options
            ),
        )
