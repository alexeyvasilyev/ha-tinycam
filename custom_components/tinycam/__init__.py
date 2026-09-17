"""The tinyCam Monitor integration."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_PORT, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import TinyCamApiError, TinyCamClient
from .const import (
    ATTR_STATE,
    ATTR_TAG,
    CONF_SCAN_INTERVAL,
    CONF_USE_SSL,
    CONF_VERIFY_SSL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MANUFACTURER,
    MODEL_WEB_SERVER,
    SERVICE_SET_NOTIFICATIONS,
)
from .coordinator import TinyCamDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.CAMERA,
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.SELECT,
    Platform.BUTTON,
    Platform.EVENT,
]

SET_NOTIFICATIONS_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): vol.All(cv.ensure_list, [cv.string]),
        vol.Required(ATTR_STATE): cv.boolean,
        vol.Optional(ATTR_TAG): cv.string,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up tinyCam Monitor from a config entry."""
    session = async_get_clientsession(
        hass, verify_ssl=entry.data.get(CONF_VERIFY_SSL, True)
    )
    client = TinyCamClient(
        session,
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
        username=entry.data.get(CONF_USERNAME) or None,
        password=entry.data.get(CONF_PASSWORD) or None,
        use_ssl=entry.data.get(CONF_USE_SSL, False),
        verify_ssl=entry.data.get(CONF_VERIFY_SSL, True),
    )

    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = TinyCamDataUpdateCoordinator(hass, client, scan_interval)
    await coordinator.async_config_entry_first_refresh()

    # Create the hub before any platform registers its camera devices.
    hub = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer=MANUFACTURER,
        model=MODEL_WEB_SERVER,
    )
    coordinator.hub_device_id = hub.id

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _async_register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_SET_NOTIFICATIONS)
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change (e.g. polling interval)."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_register_services(hass: HomeAssistant) -> None:
    """Register domain-level services once."""
    if hass.services.has_service(DOMAIN, SERVICE_SET_NOTIFICATIONS):
        return

    async def _handle_set_notifications(call: ServiceCall) -> None:
        device_registry = dr.async_get(hass)
        state: bool = call.data[ATTR_STATE]
        tag: str | None = call.data.get(ATTR_TAG)

        for device_id in call.data["device_id"]:
            device = device_registry.async_get(device_id)
            if device is None:
                raise HomeAssistantError(f"Unknown device {device_id}")

            entry_id = next(iter(device.config_entries), None)
            entry_data = hass.data.get(DOMAIN, {}).get(entry_id)
            if entry_data is None:
                raise HomeAssistantError(f"Device {device_id} is not a tinyCam hub")

            client: TinyCamClient = entry_data["client"]
            try:
                await client.async_set_notifications(state, tag)
            except TinyCamApiError as err:
                raise HomeAssistantError(f"Could not update notifications: {err}") from err

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_NOTIFICATIONS,
        _handle_set_notifications,
        schema=SET_NOTIFICATIONS_SCHEMA,
    )
