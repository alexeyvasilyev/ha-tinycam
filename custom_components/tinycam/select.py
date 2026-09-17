"""Select platform for the tinyCam Monitor integration.

The API does not report back the currently active stream profile or LED
mode, so these entities are optimistic: they show the last value set from
Home Assistant (defaulting to "auto") rather than a value read from the
device.
"""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import TinyCamApiError, TinyCamClient
from .const import (
    DOMAIN,
    LED_MODE_AUTO,
    LED_MODE_TO_ACTION,
    LED_MODES,
    MANUFACTURER,
    MODEL_CAMERA,
    MODEL_WEB_SERVER,
    STREAM_PROFILE_AUTO,
    STREAM_PROFILES,
)
from .coordinator import TinyCamCameraData, TinyCamDataUpdateCoordinator
from .discovery import async_track_cameras

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: TinyCamDataUpdateCoordinator = entry_data["coordinator"]
    client: TinyCamClient = entry_data["client"]

    async_add_entities([TinyCamStreamProfileSelect(coordinator, client, entry)])
    async_track_cameras(
        entry,
        coordinator,
        async_add_entities,
        lambda cam_id: TinyCamLedModeSelect(coordinator, client, entry, cam_id),
    )


class TinyCamStreamProfileSelect(
    RestoreEntity, CoordinatorEntity[TinyCamDataUpdateCoordinator], SelectEntity
):
    """Global stream profile (main/sub/auto)."""

    _attr_has_entity_name = True
    _attr_translation_key = "stream_profile"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = STREAM_PROFILES
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: TinyCamDataUpdateCoordinator,
        client: TinyCamClient,
        entry: ConfigEntry,
    ) -> None:
        CoordinatorEntity.__init__(self, coordinator)
        self._client = client
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_stream_profile"
        self._attr_current_option = STREAM_PROFILE_AUTO

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in STREAM_PROFILES:
            self._attr_current_option = last_state.state

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.get("status_access", False)

    async def async_select_option(self, option: str) -> None:
        try:
            await self._client.async_set_stream_profile(option)
        except TinyCamApiError as err:
            raise HomeAssistantError(f"Could not set stream profile: {err}") from err
        self._attr_current_option = option
        self.async_write_ha_state()

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer=MANUFACTURER,
            model=MODEL_WEB_SERVER,
        )


class TinyCamLedModeSelect(
    RestoreEntity, CoordinatorEntity[TinyCamDataUpdateCoordinator], SelectEntity
):
    """LED / IR light mode for a single camera (on/off/auto)."""

    _attr_has_entity_name = True
    _attr_translation_key = "led_mode"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = LED_MODES
    _attr_should_poll = False

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
        self._attr_unique_id = f"{entry.entry_id}_{cam_id}_led_mode"
        self._attr_current_option = LED_MODE_AUTO

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last_state = await self.async_get_last_state()
        if last_state is not None and last_state.state in LED_MODES:
            self._attr_current_option = last_state.state

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
            and self.coordinator.data.get("status_access", False)
            and self._cam_id in self.coordinator.data.get("cameras", {})
        )

    async def async_select_option(self, option: str) -> None:
        try:
            await self._client.async_led_control(
                self._cam.id, LED_MODE_TO_ACTION[option]
            )
        except TinyCamApiError as err:
            raise HomeAssistantError(f"Could not set LED mode: {err}") from err
        self._attr_current_option = option
        self.async_write_ha_state()

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._entry.entry_id}_{self._cam_id}")},
            name=self._cam.name,
            manufacturer=MANUFACTURER,
            model=MODEL_CAMERA,
            via_device_id=self.coordinator.hub_device_id,
        )
