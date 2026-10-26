"""Pairing: a watch asks from its phone, a user approves it with the code it shows."""

from collections import deque
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
import hmac
import secrets
import time

from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.data_entry_flow import UnknownFlow
from homeassistant.helpers.event import async_call_later
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN, PAIRING_LIMIT, PAIRING_TIMEOUT, PAIRING_WINDOW

DATA_PAIRINGS: HassKey[Pairings] = HassKey(f"{DOMAIN}_pairings")


@dataclass(slots=True)
class Pairing:
    """A watch waiting for its code to be entered in Home Assistant."""

    name: str
    code: str
    # What the phone polls with; the key comes back only to it.
    request: str
    key: str | None = None


class Pairings:
    """The one pairing in progress: a new request replaces it, so one flow at most."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize with no pairing."""
        self._hass = hass
        self.pending: Pairing | None = None
        self._flow_id: str | None = None
        self._cancel_expiry: CALLBACK_TYPE | None = None
        self._requests: deque[float] = deque(maxlen=PAIRING_LIMIT)

    async def async_start(self, name: str) -> Pairing | None:
        """Show a discovered watch until its code is entered; None if asked too often."""
        now = time.monotonic()
        if (
            len(self._requests) == PAIRING_LIMIT
            and now - self._requests[0] < PAIRING_WINDOW
        ):
            return None
        self._requests.append(now)
        self.async_cancel()
        pairing = self.pending = Pairing(
            name=name,
            code=f"{secrets.randbelow(1_000_000):06d}",
            request=secrets.token_urlsafe(32),
        )
        self._cancel_expiry = async_call_later(
            self._hass, PAIRING_TIMEOUT, self._async_expire
        )
        await self._hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": SOURCE_INTEGRATION_DISCOVERY},
            data={"pairing": pairing},
        )
        return pairing

    @callback
    def async_attach(self, pairing: Pairing, flow_id: str) -> bool:
        """Tie the flow to its pairing, unless a newer request replaced it meanwhile."""
        if pairing is not self.pending:
            return False
        self._flow_id = flow_id
        return True

    @callback
    def async_get(self, request: str) -> Pairing | None:
        """Return the pairing the phone polls for, comparing in constant time."""
        if (pairing := self.pending) is None or not hmac.compare_digest(
            pairing.request.encode(), request.encode()
        ):
            return None
        return pairing

    @callback
    def async_cancel(self) -> None:
        """Forget the pairing in progress, and drop its flow if still shown."""
        if self._cancel_expiry is not None:
            self._cancel_expiry()
            self._cancel_expiry = None
        if self._flow_id is not None:
            with suppress(UnknownFlow):
                self._hass.config_entries.flow.async_abort(self._flow_id)
        self.pending = self._flow_id = None

    @callback
    def _async_expire(self, _now: datetime) -> None:
        self._cancel_expiry = None
        self.async_cancel()
