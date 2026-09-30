"""Client for the API of the ImmichFrame fork."""

from typing import Any

import aiohttp

from homeassistant.util.json import json_loads


class ImmichFrameConnectionError(Exception):
    """The frame could not be reached or answered with an error."""


class ImmichFrameClient:
    """Talks to the endpoints the fork adds to ImmichFrame."""

    def __init__(
        self, session: aiohttp.ClientSession, url: str, secret: str | None = None
    ) -> None:
        """Initialize the client."""
        self._session = session
        self._url = url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {secret}"} if secret else {}

    async def _request(self, method: str, path: str, payload: Any = None) -> Any:
        try:
            async with self._session.request(
                method,
                f"{self._url}/{path}",
                json=payload,
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                response.raise_for_status()
                body = await response.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ImmichFrameConnectionError(str(err)) from err
        # DELETE answers 204 without a body; everything else is JSON.
        return json_loads(body) if body else None

    async def get_overlay(self) -> dict[str, Any]:
        """Return what the frame currently shows: memories, notifications, sensors."""
        return await self._request("GET", "api/Overlay")

    async def get_memories(self) -> bool:
        """Return whether memories are shown."""
        return bool((await self._request("GET", "api/Memories"))["enabled"])

    async def set_memories(self, enabled: bool) -> None:
        """Show or hide memories."""
        await self._request("PUT", "api/Memories", {"enabled": enabled})

    async def send_notification(
        self, message: str, link: str | None = None, duration: float | None = None
    ) -> None:
        """Put a notification on top of the ones shown; an empty message clears them all."""
        await self._request(
            "POST",
            "api/Notification",
            {"message": message, "link": link, "duration": duration},
        )

    async def set_sensors(self, sensors: list[dict[str, Any]]) -> None:
        """Replace the values shown under the clock."""
        await self._request("PUT", "api/Overlay/Sensors", {"sensors": sensors})
