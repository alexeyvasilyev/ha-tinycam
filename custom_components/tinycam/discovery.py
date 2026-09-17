"""Discover camera entities as the coordinator's camera list changes."""

from collections.abc import Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import TinyCamDataUpdateCoordinator


def async_track_cameras(
    entry: ConfigEntry,
    coordinator: TinyCamDataUpdateCoordinator,
    async_add_entities: AddEntitiesCallback,
    factory: Callable[[int], Entity],
) -> None:
    """Add each camera once; retain removed entities for rediscovery."""
    known: set[int] = set()

    @callback
    def discover() -> None:
        if not coordinator.last_update_success:
            return
        new_ids = coordinator.data["cameras"].keys() - known
        entities = [factory(cam_id) for cam_id in sorted(new_ids)]
        if entities:
            async_add_entities(entities)
            known.update(new_ids)

    entry.async_on_unload(coordinator.async_add_listener(discover))
    discover()
