"""Client for the API of the photo frame of Dou's Home Launcher."""

from http import HTTPStatus
from typing import Any

import aiohttp

from homeassistant.util.json import json_loads


class LauncherConnectionError(Exception):
    """The frame could not be reached or answered with an error."""


class LauncherAuthError(LauncherConnectionError):
    """The frame refused the key."""


class LauncherClient:
    """Talks to the frame, which only answers while it is on screen."""

    def __init__(self, session: aiohttp.ClientSession, url: str, key: str) -> None:
        """Initialize the client."""
        self._session = session
        self._url = url.rstrip("/")
        self._headers = {"Authorization": f"Bearer {key}"}

    async def _request(self, method: str, path: str, payload: Any = None) -> Any:
        try:
            async with self._session.request(
                method,
                f"{self._url}/api/{path}",
                json=payload,
                headers=self._headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == HTTPStatus.UNAUTHORIZED:
                    raise LauncherAuthError("wrong key")
                response.raise_for_status()
                body = await response.text()
        except (aiohttp.ClientError, TimeoutError) as err:
            raise LauncherConnectionError(str(err)) from err
        # Commands answer 204 without a body; everything else is JSON.
        return json_loads(body) if body else None

    async def get_state(self) -> dict[str, Any]:
        """Return what the frame shows and how it is set."""
        return await self._request("GET", "state")

    async def set_settings(self, **settings: bool) -> dict[str, Any]:
        """Change some settings, and return the state that results."""
        return await self._request("PUT", "settings", settings)

    async def send_command(self, command: str) -> None:
        """Change the photo, or close the frame."""
        await self._request("POST", "command", {"command": command})

    async def send_notification(
        self,
        message: str,
        link: str | None = None,
        duration: float | None = None,
        tag: str | None = None,
    ) -> None:
        """Put a notification on top; an empty message clears the tagged one, or all."""
        await self._request(
            "POST",
            "notifications",
            {"message": message, "link": link, "duration": duration, "tag": tag},
        )

    async def set_sensors(self, sensors: list[dict[str, Any]]) -> None:
        """Replace the values shown under the clock."""
        await self._request("PUT", "sensors", {"sensors": sensors})
