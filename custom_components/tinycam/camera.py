"""Camera platform for the tinyCam Monitor integration."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import voluptuous as vol
from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_platform
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import TinyCamApiError, TinyCamClient
from .const import (
    ATTR_PAN,
    ATTR_PRESET,
    ATTR_TILT,
    ATTR_ZOOM,
    DOMAIN,
    MANUFACTURER,
    MODEL_CAMERA,
    SERVICE_PTZ_GOTO_PRESET,
    SERVICE_PTZ_HOME,
    SERVICE_PTZ_MOVE,
    SERVICE_PTZ_SAVE_PRESET,
    SERVICE_PTZ_STOP,
)
from .coordinator import TinyCamCameraData, TinyCamDataUpdateCoordinator
from .discovery import async_track_cameras

_LOGGER = logging.getLogger(__name__)

PTZ_SPEED = vol.All(vol.Coerce(int), vol.Range(min=-100, max=100))


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up tinyCam cameras from a config entry."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: TinyCamDataUpdateCoordinator = entry_data["coordinator"]
    client: TinyCamClient = entry_data["client"]

    fallback_image = await hass.async_add_executor_job(
        (Path(__file__).parent / "brand" / "icon.png").read_bytes
    )

    async_track_cameras(
        entry,
        coordinator,
        async_add_entities,
        lambda cam_id: TinyCamCamera(
            coordinator, client, entry, cam_id, fallback_image
        ),
    )

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_PTZ_MOVE,
        {
            vol.Optional(ATTR_PAN, default=0): PTZ_SPEED,
            vol.Optional(ATTR_TILT, default=0): PTZ_SPEED,
            vol.Optional(ATTR_ZOOM, default=0): PTZ_SPEED,
        },
        "async_ptz_move",
    )
    platform.async_register_entity_service(SERVICE_PTZ_STOP, {}, "async_ptz_stop")
    platform.async_register_entity_service(SERVICE_PTZ_HOME, {}, "async_ptz_home")
    platform.async_register_entity_service(
        SERVICE_PTZ_GOTO_PRESET,
        {vol.Required(ATTR_PRESET): vol.All(vol.Coerce(int), vol.Range(min=1))},
        "async_ptz_goto_preset",
    )
    platform.async_register_entity_service(
        SERVICE_PTZ_SAVE_PRESET,
        {vol.Required(ATTR_PRESET): vol.All(vol.Coerce(int), vol.Range(min=1))},
        "async_ptz_save_preset",
    )


class TinyCamCamera(CoordinatorEntity[TinyCamDataUpdateCoordinator], Camera):
    """Representation of a single camera exposed by tinyCam Monitor."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self,
        coordinator: TinyCamDataUpdateCoordinator,
        client: TinyCamClient,
        entry: ConfigEntry,
        cam_id: int,
        fallback_image: bytes | None = None,
    ) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        Camera.__init__(self)
        self._client = client
        self._fallback_image = fallback_image
        self._entry = entry
        self._cam_id = cam_id
        self._last_cam = coordinator.data["cameras"][cam_id]
        self._attr_unique_id = f"{entry.entry_id}_{cam_id}_camera"
        self._attr_supported_features = CameraEntityFeature.STREAM

    @property
    def _cam(self) -> TinyCamCameraData:
        self._last_cam = self.coordinator.data["cameras"].get(
            self._cam_id, self._last_cam
        )
        return self._last_cam

    @property
    def available(self) -> bool:
        return (
            super().available
            and self._cam_id in self.coordinator.data.get("cameras", {})
            and self._cam.enabled
        )

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_{self._cam_id}")},
            name=self._cam.name,
            manufacturer=MANUFACTURER,
            model=MODEL_CAMERA,
            via_device_id=self.coordinator.hub_device_id,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        cam = self._cam
        return {
            "camera_id": cam.id,
            "ptz_capabilities": cam.ptz_capabilities,
            "audio_listening": cam.audio_listening,
            "cloud_access": cam.cloud_access,
        }

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        resolution = f"{width}x{height}" if width and height else None
        try:
            # Return the placeholder before HA's image request times out (10s).
            async with asyncio.timeout(8):
                image = await self._client.async_get_still_image(
                    self._cam.id, resolution=resolution
                )
            if image:
                self.content_type = "image/jpeg"
                return image
        except (TinyCamApiError, TimeoutError) as err:
            _LOGGER.warning("Could not fetch snapshot for %s: %s", self._cam.name, err)
        self.content_type = "image/png"
        return self._fallback_image

    async def stream_source(self) -> str | None:
        return self._client.rtsp_stream_url(self._cam.id)

    # -- PTZ services ---------------------------------------------------

    async def async_ptz_move(self, pan: int = 0, tilt: int = 0, zoom: int = 0) -> None:
        await self._async_call(
            self._client.async_ptz_continuous_move, self._cam.id, pan, tilt, zoom
        )

    async def async_ptz_stop(self) -> None:
        await self._async_call(self._client.async_ptz_stop, self._cam.id)

    async def async_ptz_home(self) -> None:
        await self._async_call(self._client.async_ptz_home, self._cam.id)

    async def async_ptz_goto_preset(self, preset: int) -> None:
        await self._async_call(self._client.async_ptz_goto_preset, self._cam.id, preset)

    async def async_ptz_save_preset(self, preset: int) -> None:
        await self._async_call(self._client.async_ptz_save_preset, self._cam.id, preset)

    async def _async_call(self, func, *args: Any) -> None:
        try:
            await func(*args)
        except TinyCamApiError as err:
            raise HomeAssistantError(f"tinyCam PTZ command failed: {err}") from err
