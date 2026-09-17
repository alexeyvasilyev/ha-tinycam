"""Binary sensor platform for the tinyCam Monitor integration (motion)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL_CAMERA
from .coordinator import TinyCamCameraData, TinyCamDataUpdateCoordinator
from .discovery import async_track_cameras


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: TinyCamDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    async_track_cameras(
        entry,
        coordinator,
        async_add_entities,
        lambda cam_id: TinyCamMotionBinarySensor(coordinator, entry, cam_id),
    )


class TinyCamMotionBinarySensor(
    CoordinatorEntity[TinyCamDataUpdateCoordinator], BinarySensorEntity
):
    """Motion detection state for a single camera."""

    _attr_has_entity_name = True
    _attr_translation_key = "motion"
    _attr_device_class = BinarySensorDeviceClass.MOTION

    def __init__(
        self, coordinator: TinyCamDataUpdateCoordinator, entry: ConfigEntry, cam_id: int
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._cam_id = cam_id
        self._last_cam = coordinator.data["cameras"][cam_id]
        self._attr_unique_id = f"{entry.entry_id}_{cam_id}_motion"

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
            and self._cam.motion is not None
        )

    @property
    def is_on(self) -> bool | None:
        return self._cam.motion

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_{self._cam_id}")},
            name=self._cam.name,
            manufacturer=MANUFACTURER,
            model=MODEL_CAMERA,
            via_device_id=self.coordinator.hub_device_id,
        )
