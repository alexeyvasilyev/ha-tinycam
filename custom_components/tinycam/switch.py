"""Switch platform for the tinyCam Monitor integration (global toggles)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
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


@dataclass(frozen=True, kw_only=True)
class TinyCamSwitchDescription(SwitchEntityDescription):
    is_on_fn: Callable[[dict[str, Any]], bool] = lambda data: False
    turn_on_fn: Callable[[TinyCamClient], Awaitable[None]] | None = None
    turn_off_fn: Callable[[TinyCamClient], Awaitable[None]] | None = None


SWITCH_DESCRIPTIONS: tuple[TinyCamSwitchDescription, ...] = (
    TinyCamSwitchDescription(
        key="background_mode",
        translation_key="background_mode",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda d: bool(d.get("backgroundMode")),
        turn_on_fn=lambda c: c.async_set_background_mode(True),
        turn_off_fn=lambda c: c.async_set_background_mode(False),
    ),
    TinyCamSwitchDescription(
        key="power_safe_mode",
        translation_key="power_safe_mode",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda d: bool(d.get("powerSafeMode")),
        turn_on_fn=lambda c: c.async_set_power_safe_mode(True),
        turn_off_fn=lambda c: c.async_set_power_safe_mode(False),
    ),
    TinyCamSwitchDescription(
        key="notifications",
        translation_key="notifications",
        entity_category=EntityCategory.CONFIG,
        is_on_fn=lambda d: bool(d.get("notifications")),
        turn_on_fn=lambda c: c.async_set_notifications(True),
        turn_off_fn=lambda c: c.async_set_notifications(False),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinator: TinyCamDataUpdateCoordinator = entry_data["coordinator"]
    client: TinyCamClient = entry_data["client"]
    async_add_entities(
        TinyCamSwitch(coordinator, client, entry, description)
        for description in SWITCH_DESCRIPTIONS
    )


class TinyCamSwitch(CoordinatorEntity[TinyCamDataUpdateCoordinator], SwitchEntity):
    """A global tinyCam Monitor toggle backed by param.cgi."""

    _attr_has_entity_name = True
    entity_description: TinyCamSwitchDescription

    def __init__(
        self,
        coordinator: TinyCamDataUpdateCoordinator,
        client: TinyCamClient,
        entry: ConfigEntry,
        description: TinyCamSwitchDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._client = client
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def is_on(self) -> bool:
        return self.entity_description.is_on_fn(self.coordinator.data.get("system", {}))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._async_call(self.entity_description.turn_on_fn)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._async_call(self.entity_description.turn_off_fn)

    async def _async_call(
        self, func: Callable[[TinyCamClient], Awaitable[None]]
    ) -> None:
        try:
            await func(self._client)
        except TinyCamApiError as err:
            raise HomeAssistantError(f"tinyCam command failed: {err}") from err
        await self.coordinator.async_request_refresh()

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.data.get("status_access", False)

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer=MANUFACTURER,
            model=MODEL_WEB_SERVER,
        )
