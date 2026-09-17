"""Button platform for the tinyCam Monitor integration (reboot)."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import TinyCamApiError, TinyCamClient
from .const import DOMAIN, MANUFACTURER, MODEL_WEB_SERVER
from .coordinator import TinyCamDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    client: TinyCamClient = hass.data[DOMAIN][entry.entry_id]["client"]
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities([TinyCamRebootButton(coordinator, client, entry)])


class TinyCamRebootButton(
    CoordinatorEntity[TinyCamDataUpdateCoordinator], ButtonEntity
):
    """Reboots the Android device running tinyCam Monitor. Requires root."""

    _attr_has_entity_name = True
    _attr_translation_key = "reboot"
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: TinyCamDataUpdateCoordinator,
        client: TinyCamClient,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._client = client
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_reboot"

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.get("status_access", False)

    async def async_press(self) -> None:
        try:
            await self._client.async_reboot()
        except TinyCamApiError as err:
            raise HomeAssistantError(
                f"Reboot failed (requires root and admin access): {err}"
            ) from err

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer=MANUFACTURER,
            model=MODEL_WEB_SERVER,
        )
