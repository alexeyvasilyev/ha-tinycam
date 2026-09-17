"""Sensor platform for the tinyCam Monitor integration (server status)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfDataRate,
    UnitOfFrequency,
    UnitOfInformation,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER, MODEL_WEB_SERVER
from .coordinator import TinyCamDataUpdateCoordinator


@dataclass(frozen=True, kw_only=True)
class TinyCamSensorDescription(SensorEntityDescription):
    """Describes a tinyCam global status sensor."""

    value_fn: Callable[[dict[str, Any]], Any] = lambda data: None


SENSOR_DESCRIPTIONS: tuple[TinyCamSensorDescription, ...] = (
    TinyCamSensorDescription(
        key="cpu_usage",
        translation_key="cpu_usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("cpuUsagePercents"),
    ),
    TinyCamSensorDescription(
        key="cpu_frequency",
        translation_key="cpu_frequency",
        native_unit_of_measurement=UnitOfFrequency.MEGAHERTZ,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("cpuFrequencyMhz"),
    ),
    TinyCamSensorDescription(
        key="memory_used",
        translation_key="memory_used",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.MEBIBYTES,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("memoryUsed"),
    ),
    TinyCamSensorDescription(
        key="memory_available",
        translation_key="memory_available",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.MEBIBYTES,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.get("memoryAvailable"),
    ),
    TinyCamSensorDescription(
        key="battery_level",
        translation_key="battery_level",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("batteryLevel"),
    ),
    TinyCamSensorDescription(
        key="uptime",
        translation_key="uptime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: (d.get("uptime") or 0) / 1000,
    ),
    TinyCamSensorDescription(
        key="network_in",
        translation_key="network_in",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("networkInBps"),
    ),
    TinyCamSensorDescription(
        key="network_out",
        translation_key="network_out",
        device_class=SensorDeviceClass.DATA_RATE,
        native_unit_of_measurement=UnitOfDataRate.BYTES_PER_SECOND,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("networkOutBps"),
    ),
    TinyCamSensorDescription(
        key="space_used",
        translation_key="space_used",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("spaceUsed"),
    ),
    TinyCamSensorDescription(
        key="space_available",
        translation_key="space_available",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("spaceAvailable"),
    ),
    TinyCamSensorDescription(
        key="live_connections",
        translation_key="live_connections",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.get("liveConnections"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: TinyCamDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id][
        "coordinator"
    ]
    async_add_entities(
        TinyCamStatusSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    )


class TinyCamStatusSensor(
    CoordinatorEntity[TinyCamDataUpdateCoordinator], SensorEntity
):
    """A single global tinyCam server status metric."""

    _attr_has_entity_name = True
    entity_description: TinyCamSensorDescription

    def __init__(
        self,
        coordinator: TinyCamDataUpdateCoordinator,
        entry: ConfigEntry,
        description: TinyCamSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self.coordinator.data.get("system", {}))

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
