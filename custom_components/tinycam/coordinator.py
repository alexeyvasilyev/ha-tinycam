"""Data update coordinator for the tinyCam Monitor integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TinyCamApiError, TinyCamAuthError, TinyCamClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class TinyCamCameraData:
    """State for a single camera known to tinyCam."""

    id: int
    name: str
    enabled: bool
    ptz_capabilities: int
    audio_listening: bool
    cloud_access: bool
    motion: bool | None = None


class TinyCamDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll tinyCam for the camera list, global status and per-camera motion state."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: TinyCamClient,
        update_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )
        self.client = client
        self.hub_device_id: str | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            cam_list = await self.client.async_get_cam_list()
            # Camera listing is available to guests; status is admin-only.
            status_access = True
            try:
                system_status = await self.client.async_get_status()
            except TinyCamAuthError:
                system_status = {}
                status_access = False

            cameras: dict[int, TinyCamCameraData] = {}
            for cam in cam_list:
                cam_id = cam["id"]
                motion = None
                if status_access:
                    try:
                        cam_status = await self.client.async_get_status(cam_id)
                        motion = cam_status.get("motion")
                    except TinyCamApiError as err:
                        _LOGGER.debug(
                            "Could not fetch status for camera %s: %s", cam_id, err
                        )

                cameras[cam_id] = TinyCamCameraData(
                    id=cam_id,
                    name=cam.get("name", f"Camera {cam_id}"),
                    enabled=cam.get("enabled", True),
                    ptz_capabilities=cam.get("ptzCapabilities", 0),
                    audio_listening=cam.get("audioListening", False),
                    cloud_access=cam.get("cloudAccess", False),
                    motion=motion,
                )

            return {
                "cameras": cameras,
                "system": system_status,
                "status_access": status_access,
            }
        except TinyCamAuthError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except TinyCamApiError as err:
            raise UpdateFailed(f"Error communicating with tinyCam: {err}") from err
