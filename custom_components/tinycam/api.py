"""Minimal async client for the tinyCam Monitor PRO web server API.

API reference: https://github.com/alexeyvasilyev/tinycam-api
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any
from urllib.parse import quote, urlencode

import aiohttp

_LOGGER = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10


class TinyCamApiError(Exception):
    """Generic tinyCam API error."""


class TinyCamAuthError(TinyCamApiError):
    """Raised when authentication fails (HTTP 401/403)."""


class TinyCamConnectionError(TinyCamApiError):
    """Raised when the server cannot be reached."""


class TinyCamClient:
    """Thin async wrapper around the tinyCam Monitor PRO REST API."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        port: int,
        username: str | None = None,
        password: str | None = None,
        use_ssl: bool = False,
        verify_ssl: bool = True,
    ) -> None:
        self._session = session
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_ssl = use_ssl
        self._verify_ssl = verify_ssl

    @property
    def base_url(self) -> str:
        scheme = "https" if self._use_ssl else "http"
        return f"{scheme}://{self._host}:{self._port}"

    def _auth_params(self) -> dict[str, str]:
        params: dict[str, str] = {}
        if self._username:
            params["user"] = self._username
            params["pwd"] = self._password or ""
        return params

    def _ssl_arg(self) -> bool | None:
        if self._use_ssl and not self._verify_ssl:
            return False
        return None

    @staticmethod
    def _check_response(status: int, body: bytes) -> None:
        # Some tinyCam versions return errors as text with HTTP status 200.
        error = re.match(rb"HTTP (\d{3})\b", body)
        effective_status = int(error[1]) if error else status
        if effective_status in (401, 403):
            raise TinyCamAuthError(f"Authentication failed ({effective_status})")
        if effective_status >= 400:
            raise TinyCamApiError(f"Unexpected status {effective_status}")

    async def _request(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        expect_json: bool = True,
    ) -> Any:
        url = f"{self.base_url}{path}"
        all_params = {**self._auth_params(), **(params or {})}
        try:
            async with self._session.get(
                url,
                params=all_params,
                ssl=self._ssl_arg(),
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                body = await resp.read()
                self._check_response(resp.status, body)
                if not expect_json:
                    return None
                try:
                    data = json.loads(body)
                except (ValueError, UnicodeError) as err:
                    raise TinyCamApiError(f"Invalid JSON response from {path}") from err
                if not isinstance(data, dict) or "data" not in data:
                    raise TinyCamApiError(f"Invalid API response from {path}")
                return data
        except TinyCamApiError:
            raise
        except asyncio.TimeoutError as err:
            raise TinyCamConnectionError(f"Timeout calling {path}") from err
        except aiohttp.ClientError as err:
            raise TinyCamConnectionError(str(err)) from err

    # -- JSON API -----------------------------------------------------

    async def async_get_cam_list(self) -> list[dict[str, Any]]:
        """Return the list of cameras known to tinyCam."""
        data = await self._request("/api/v1/get_cam_list")
        return data.get("data", []) or []

    async def async_get_status(self, camera_id: int | None = None) -> dict[str, Any]:
        """Return global status, or per-camera status when camera_id is given."""
        params: dict[str, Any] = {}
        if camera_id is not None:
            params["cameraId"] = camera_id
        data = await self._request("/api/v1/get_status", params)
        return data.get("data", {}) or {}

    async def async_get_cam_event_list(
        self,
        camera_id: int | None = None,
        endtime: int | None = None,
        count: int | None = None,
        event_type: str | None = None,
        detection_filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return recorded events, newest first."""
        params: dict[str, Any] = {}
        if camera_id is not None:
            params["cameraId"] = camera_id
        if endtime is not None:
            params["endtime"] = endtime
        if count is not None:
            params["count"] = count
        if event_type is not None:
            params["type"] = event_type
        if detection_filter is not None:
            params["filter"] = detection_filter
        data = await self._request("/api/v1/get_cam_event_list", params)
        return data.get("data", []) or []

    # -- Still image / streams -----------------------------------------

    async def async_get_still_image(
        self,
        camera_id: int,
        compression: int | None = None,
        resolution: str | None = None,
    ) -> bytes:
        """Fetch a single JPEG frame for the given camera ID."""
        params: dict[str, Any] = {**self._auth_params(), "cameraId": camera_id}
        if compression is not None:
            params["compression"] = compression
        if resolution is not None:
            params["resolution"] = resolution
        url = f"{self.base_url}/axis-cgi/jpg/image.cgi"
        try:
            async with self._session.get(
                url,
                params=params,
                ssl=self._ssl_arg(),
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as resp:
                body = await resp.read()
                self._check_response(resp.status, body)
                return body
        except TinyCamApiError:
            raise
        except asyncio.TimeoutError as err:
            raise TinyCamConnectionError("Timeout fetching still image") from err
        except aiohttp.ClientError as err:
            raise TinyCamConnectionError(str(err)) from err

    def rtsp_stream_url(self, camera_id: int) -> str:
        """Build the RTSP stream URL for the given camera ID."""
        scheme = "rtsps" if self._use_ssl else "rtsp"
        auth = ""
        if self._username:
            auth = f"{quote(self._username, safe='')}:{quote(self._password or '', safe='')}@"
        return f"{scheme}://{auth}{self._host}:{self._port}/axis-media/media.amp?cameraId={camera_id}"

    def get_file_url(self, file_path: str) -> str:
        """Build the URL to download a recorded file returned by get_cam_event_list."""
        params = {**self._auth_params(), "file": file_path}
        return f"{self.base_url}/api/v1/get_file?{urlencode(params)}"

    # -- PTZ / lighting --------------------------------------------------

    async def async_ptz(self, camera_id: int, **kwargs: Any) -> None:
        params: dict[str, Any] = {"cameraId": camera_id, **kwargs}
        await self._request("/axis-cgi/com/ptz.cgi", params, expect_json=False)

    async def async_ptz_continuous_move(
        self, camera_id: int, pan: int = 0, tilt: int = 0, zoom: int = 0
    ) -> None:
        await self.async_ptz(
            camera_id,
            continuouspantiltmove=f"{pan},{tilt}",
            continuouszoommove=zoom,
        )

    async def async_ptz_stop(self, camera_id: int) -> None:
        await self.async_ptz_continuous_move(camera_id, 0, 0, 0)

    async def async_ptz_home(self, camera_id: int) -> None:
        await self.async_ptz(camera_id, move="home")

    async def async_ptz_goto_preset(self, camera_id: int, preset: int) -> None:
        await self.async_ptz(camera_id, gotoserverpresetno=preset)

    async def async_ptz_save_preset(self, camera_id: int, preset: int) -> None:
        await self.async_ptz(camera_id, setserverpresetno=preset)

    async def async_led_control(self, camera_id: int, action: str) -> None:
        await self._request(
            "/axis-cgi/io/lightcontrol.cgi",
            {"cameraId": camera_id, "action": action},
            expect_json=False,
        )

    # -- Global parameters -------------------------------------------------

    async def async_set_background_mode(self, enabled: bool) -> None:
        await self._request(
            "/param.cgi",
            {"action": "update", "root.BackgroundMode": "on" if enabled else "off"},
            expect_json=False,
        )

    async def async_set_power_safe_mode(self, enabled: bool) -> None:
        await self._request(
            "/param.cgi",
            {"action": "update", "root.PowerSafeMode": "on" if enabled else "off"},
            expect_json=False,
        )

    async def async_set_notifications(
        self, enabled: bool, tag: str | None = None
    ) -> None:
        params: dict[str, Any] = {
            "action": "update",
            "root.Notifications": "on" if enabled else "off",
        }
        if tag:
            params["tag"] = tag
        await self._request("/param.cgi", params, expect_json=False)

    async def async_set_stream_profile(self, profile: str) -> None:
        await self._request(
            "/param.cgi",
            {"action": "update", "root.StreamProfile": profile},
            expect_json=False,
        )

    async def async_reboot(self) -> None:
        await self._request("/axis-cgi/admin/restart.cgi", expect_json=False)
