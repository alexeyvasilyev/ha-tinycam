"""Event platform for the tinyCam Monitor integration (recorded detections)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import TinyCamApiError, TinyCamClient
from .const import DOMAIN, EVENT_TYPES, MANUFACTURER, MODEL_CAMERA
from .coordinator import TinyCamCameraData, TinyCamDataUpdateCoordinator
from .discovery import async_track_cameras

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: TinyCamDataUpdateCoordinator = entry_data["coordinator"]
    client: TinyCamClient = entry_data["client"]
    async_track_cameras(
        entry,
        coordinator,
        async_add_entities,
        lambda cam_id: TinyCamDetectionEvent(coordinator, client, entry, cam_id),
    )


class TinyCamDetectionEvent(
    CoordinatorEntity[TinyCamDataUpdateCoordinator], EventEntity
):
    """Fires when tinyCam records a new detection event for a camera."""

    _attr_has_entity_name = True
    _attr_translation_key = "detection"
    _attr_event_types = EVENT_TYPES

    def __init__(
        self,
        coordinator: TinyCamDataUpdateCoordinator,
        client: TinyCamClient,
        entry: ConfigEntry,
        cam_id: int,
    ) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        self._client = client
        self._entry = entry
        self._cam_id = cam_id
        self._last_cam = coordinator.data["cameras"][cam_id]
        self._attr_unique_id = f"{entry.entry_id}_{cam_id}_detection"
        self._last_time: int | None = None
        self._seen_at_last_time: set[tuple] = set()
        self._event_task: asyncio.Task | None = None
        self._event_lock = asyncio.Lock()

    @property
    def _cam(self) -> TinyCamCameraData:
        self._last_cam = self.coordinator.data["cameras"].get(
            self._cam_id, self._last_cam
        )
        return self._last_cam

    @property
    def available(self) -> bool:
        return super().available and self._cam_id in self.coordinator.data.get(
            "cameras", {}
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self._async_check_new_events()

    async def async_will_remove_from_hass(self) -> None:
        if self._event_task is not None:
            self._event_task.cancel()
            try:
                await self._event_task
            except asyncio.CancelledError:
                pass
        await super().async_will_remove_from_hass()

    def _handle_coordinator_update(self) -> None:
        if self.available and (self._event_task is None or self._event_task.done()):
            self._event_task = self.hass.async_create_task(
                self._async_check_new_events()
            )
        super()._handle_coordinator_update()

    @staticmethod
    def _event_key(event: dict[str, Any]) -> tuple:
        return (
            event["time"],
            event.get("video"),
            event.get("image"),
            event.get("motion"),
        )

    async def _async_read_event_window(self, since: int | None) -> list[dict[str, Any]]:
        """Read back to the cursor, including all events sharing its timestamp."""
        count = 10
        endtime = None
        while True:
            events = await self._client.async_get_cam_event_list(
                camera_id=self._cam_id, count=count, endtime=endtime
            )
            if not events:
                return events
            if since is None:
                since = events[0]["time"]
            if len(events) < count or events[-1]["time"] < since:
                return events
            # Expand a fixed history window until we reach the cursor.
            # Keeping timestamp ties together avoids losing events at a page boundary.
            if endtime is None:
                endtime = events[0]["time"] + 1
            count *= 2

    async def _async_check_new_events(self) -> None:
        async with self._event_lock:
            if not self.available:
                return
            try:
                events = await self._async_read_event_window(self._last_time)
                if not self.available:
                    return
                if self._last_time is None:
                    # Retry priming after errors; never replay old history as new events.
                    self._last_time = events[0]["time"] if events else 0
                    self._seen_at_last_time = {
                        self._event_key(e)
                        for e in events
                        if e["time"] == self._last_time
                    }
                    return
            except TinyCamApiError as err:
                _LOGGER.debug(
                    "Could not fetch events for camera %s: %s", self._cam_id, err
                )
                return

            new_events = {
                self._event_key(event): event
                for event in events
                if event["time"] > self._last_time
                or (
                    event["time"] == self._last_time
                    and self._event_key(event) not in self._seen_at_last_time
                )
            }
            for event in sorted(new_events.values(), key=lambda item: item["time"]):
                event_type = event.get("motion", "motion")
                if event_type in EVENT_TYPES:
                    self._trigger_event(
                        event_type,
                        {
                            "video": event.get("video"),
                            "image": event.get("image"),
                            "duration": event.get("duration"),
                        },
                    )
                    self.async_write_ha_state()
                else:
                    _LOGGER.debug("Ignoring unsupported event type %s", event_type)
                if event["time"] > self._last_time:
                    self._last_time = event["time"]
                    self._seen_at_last_time.clear()
                self._seen_at_last_time.add(self._event_key(event))

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_{self._cam_id}")},
            name=self._cam.name,
            manufacturer=MANUFACTURER,
            model=MODEL_CAMERA,
            via_device_id=self.coordinator.hub_device_id,
        )
