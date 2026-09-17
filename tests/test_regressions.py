"""Regression tests using real Home Assistant entities and a simulated tinyCam API."""

from __future__ import annotations

import asyncio
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import frame
from homeassistant.helpers.entity import EntityPlatformState
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.tinycam.api import (
    TinyCamApiError,
    TinyCamAuthError,
    TinyCamClient,
)
from custom_components.tinycam.binary_sensor import TinyCamMotionBinarySensor
from custom_components.tinycam.coordinator import (
    TinyCamCameraData,
    TinyCamDataUpdateCoordinator,
)
from custom_components.tinycam.event import TinyCamDetectionEvent


@pytest_asyncio.fixture
async def hass(tmp_path):
    instance = HomeAssistant(str(tmp_path))
    frame.async_setup(instance)
    yield instance
    await instance.async_stop()


@pytest.fixture
def entry():
    callbacks = []
    return SimpleNamespace(
        entry_id="test",
        title="tinyCam",
        async_on_unload=callbacks.append,
        unload_callbacks=callbacks,
    )


def camera(camera_id=1):
    return TinyCamCameraData(camera_id, f"Camera {camera_id}", True, 0, False, False)


def coordinator(hass, client=None):
    result = TinyCamDataUpdateCoordinator(hass, client or Mock(), 30)
    result.async_set_updated_data(
        {"cameras": {1: camera()}, "system": {}, "status_access": True}
    )
    return result


def api_client(body=b'{"data": []}', status=200):
    response = SimpleNamespace(status=status, read=AsyncMock(return_value=body))
    context = AsyncMock()
    context.__aenter__.return_value = response
    session = Mock()
    session.get.return_value = context
    return TinyCamClient(session, "localhost", 8083, "admin", None), session


@pytest.mark.asyncio
async def test_empty_password_is_sent():
    client, session = api_client()
    assert await client.async_get_cam_list() == []
    assert session.get.call_args.kwargs["params"] == {"user": "admin", "pwd": ""}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body,status", [(b"HTTP 403. Invalid token.", 200), (b"Denied", 401)]
)
async def test_auth_errors_are_normalized(body, status):
    client, _ = api_client(body, status)
    with pytest.raises(TinyCamAuthError):
        await client.async_get_cam_list()
    with pytest.raises(TinyCamAuthError):
        await client.async_get_still_image(1)
    with pytest.raises(TinyCamAuthError):
        await client.async_set_notifications(True)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [b"", b"OK"])
async def test_commands_accept_non_json_success(body):
    client, _ = api_client(body)
    await client.async_set_notifications(True)
    await client.async_ptz_stop(1)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [b"invalid", b"[]", b"{}"])
async def test_invalid_json_api_responses_raise_api_error(body):
    client, _ = api_client(body)
    with pytest.raises(TinyCamApiError):
        await client.async_get_cam_list()


@pytest.mark.asyncio
async def test_guest_loads_cameras_without_status(hass):
    client = Mock(
        async_get_cam_list=AsyncMock(return_value=[{"id": 1}]),
        async_get_status=AsyncMock(side_effect=TinyCamAuthError()),
    )
    data = await TinyCamDataUpdateCoordinator(hass, client, 30)._async_update_data()
    assert 1 in data["cameras"]
    assert data["system"] == {}
    assert not data["status_access"]
    assert data["cameras"][1].motion is None
    client.async_get_status.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_invalid_camera_list_auth_still_fails(hass):
    client = Mock(async_get_cam_list=AsyncMock(side_effect=TinyCamAuthError()))
    with pytest.raises(UpdateFailed):
        await TinyCamDataUpdateCoordinator(hass, client, 30)._async_update_data()


@pytest.mark.asyncio
async def test_motion_failure_is_unavailable_and_recovers(hass, entry):
    client = Mock(
        async_get_cam_list=AsyncMock(return_value=[{"id": 1}]),
        async_get_status=AsyncMock(
            side_effect=[{}, TinyCamApiError(), {}, {"motion": False}]
        ),
    )
    coord = coordinator(hass, client)
    entity = TinyCamMotionBinarySensor(coord, entry, 1)
    coord.async_set_updated_data(await coord._async_update_data())
    assert not entity.available
    assert entity.is_on is None
    coord.async_set_updated_data(await coord._async_update_data())
    assert entity.available
    assert entity.is_on is False


class History:
    def __init__(self, events=()):
        self.events = list(events)
        self.calls = []
        self.fail_on_count = None

    async def async_get_cam_event_list(self, *, camera_id, count, endtime=None):
        self.calls.append(count)
        if count == self.fail_on_count:
            raise TinyCamApiError("Temporary failure")
        return sorted(
            (e for e in self.events if endtime is None or e["time"] <= endtime),
            key=lambda e: e["time"],
            reverse=True,
        )[:count]


def event(time, kind="motion", suffix=""):
    return {"time": time, "motion": kind, "video": f"/{time}{suffix}.mp4"}


def detection(hass, entry, history):
    entity = TinyCamDetectionEvent(coordinator(hass), history, entry, 1)
    entity.hass = hass
    entity.entity_id = "event.test_detection"
    entity._attr_name = "Detection"
    entity.platform = Mock(platform_name="tinycam", config_entry=None)
    entity._platform_state = EntityPlatformState.ADDED
    entity._last_time = 0
    return entity


@pytest.mark.asyncio
async def test_all_events_published_individually_without_replay(hass, entry):
    history = History([event(i) for i in range(1, 26)])
    entity = detection(hass, entry, history)
    states = []

    @callback
    def collect(update):
        states.append(update.data["new_state"])

    hass.bus.async_listen("state_changed", collect)
    await entity._async_check_new_events()
    await hass.async_block_till_done()
    assert [state.attributes["video"] for state in states] == [
        f"/{i}.mp4" for i in range(1, 26)
    ]
    assert history.calls == [10, 20, 40]
    await entity._async_check_new_events()
    await hass.async_block_till_done()
    assert len(states) == 25


@pytest.mark.asyncio
async def test_equal_timestamps_and_late_arrival(hass, entry):
    history = History([event(1, suffix=str(i)) for i in range(15)])
    entity = detection(hass, entry, history)
    entity.async_write_ha_state = Mock()
    await entity._async_check_new_events()
    assert entity.async_write_ha_state.call_count == 15
    history.events.append(event(1, "person", "late"))
    await entity._async_check_new_events()
    assert entity.async_write_ha_state.call_count == 16
    assert entity.state_attributes["event_type"] == "person"


@pytest.mark.asyncio
async def test_history_failure_does_not_advance_cursor(hass, entry):
    history = History([event(i) for i in range(1, 26)])
    history.fail_on_count = 20
    entity = detection(hass, entry, history)
    entity.async_write_ha_state = Mock()
    await entity._async_check_new_events()
    assert entity._last_time == 0
    entity.async_write_ha_state.assert_not_called()
    history.fail_on_count = None
    await entity._async_check_new_events()
    assert entity.async_write_ha_state.call_count == 25


@pytest.mark.asyncio
async def test_failed_prime_retries_without_replaying_history(hass, entry):
    history = History([event(10)])
    history.fail_on_count = 10
    entity = detection(hass, entry, history)
    entity._last_time = None
    entity.async_write_ha_state = Mock()
    await entity._async_check_new_events()
    assert entity._last_time is None
    history.fail_on_count = None
    await entity._async_check_new_events()
    assert entity._last_time == 10
    entity.async_write_ha_state.assert_not_called()
    history.events.append(event(11))
    await entity._async_check_new_events()
    entity.async_write_ha_state.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["camera", "binary_sensor", "event", "select"])
async def test_dynamic_camera_discovery_and_removal(hass, entry, platform):
    coord = coordinator(hass)
    coord.hub_device_id = "ha-hub-device-id"
    hass.data["tinycam"] = {entry.entry_id: {"coordinator": coord, "client": Mock()}}
    entities = []
    module = import_module(f"custom_components.tinycam.{platform}")
    with patch(
        "homeassistant.helpers.entity_platform.async_get_current_platform",
        return_value=Mock(),
    ):
        await module.async_setup_entry(
            hass, entry, lambda items: entities.extend(items)
        )
    initial_count = len(entities)
    coord.async_set_updated_data({**coord.data, "cameras": {1: camera(), 2: camera(2)}})
    assert len(entities) == initial_count + 1
    coord.async_set_updated_data({**coord.data, "cameras": {2: camera(2)}})
    first = next(e for e in entities if getattr(e, "_cam_id", None) == 1)
    assert not first.available
    assert first.device_info["name"] == "Camera 1"
    assert first.device_info["via_device_id"] == "ha-hub-device-id"
    assert "via_device" not in first.device_info
    if platform == "camera":
        assert first.extra_state_attributes["camera_id"] == 1
    coord.async_set_updated_data({**coord.data, "cameras": {1: camera(), 2: camera(2)}})
    assert len(entities) == initial_count + 1
    for unsubscribe in entry.unload_callbacks:
        unsubscribe()
    coord.async_set_updated_data({**coord.data, "cameras": {3: camera(3)}})
    assert len(entities) == initial_count + 1


@pytest.mark.asyncio
@pytest.mark.parametrize("platform", ["sensor", "switch", "select", "button"])
async def test_admin_entities_unavailable_to_guests(hass, entry, platform):
    coord = coordinator(hass)
    hass.data["tinycam"] = {entry.entry_id: {"coordinator": coord, "client": Mock()}}
    entities = []
    await import_module(f"custom_components.tinycam.{platform}").async_setup_entry(
        hass, entry, lambda items: entities.extend(items)
    )
    coord.async_set_updated_data({**coord.data, "status_access": False})
    assert entities and all(not entity.available for entity in entities)
    coord.async_set_updated_data({**coord.data, "status_access": True})
    assert all(entity.available for entity in entities)
    for unsubscribe in entry.unload_callbacks:
        unsubscribe()


@pytest.mark.asyncio
async def test_prime_does_not_replay_timestamp_ties(hass, entry):
    history = History([event(10, suffix=str(i)) for i in range(15)])
    entity = detection(hass, entry, history)
    entity._last_time = None
    entity.async_write_ha_state = Mock()
    await entity._async_check_new_events()
    await entity._async_check_new_events()
    entity.async_write_ha_state.assert_not_called()
    history.events.append(event(10, "person", "new"))
    await entity._async_check_new_events()
    entity.async_write_ha_state.assert_called_once()


@pytest.mark.asyncio
async def test_removal_cancels_pending_event_request(hass, entry):
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def pending_request(**kwargs):
        started.set()
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    client = Mock(async_get_cam_event_list=pending_request)
    entity = detection(hass, entry, client)
    entity.async_write_ha_state = Mock()
    entity._handle_coordinator_update()
    await started.wait()
    task = entity._event_task
    entity._handle_coordinator_update()
    assert entity._event_task is task
    entity.async_write_ha_state.reset_mock()
    await entity.async_will_remove_from_hass()
    assert task.cancelled()
    assert cancelled.is_set()
    entity.async_write_ha_state.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [TinyCamApiError("Offline"), TimeoutError(), b""])
async def test_camera_placeholder_and_recovery(hass, entry, failure):
    from pathlib import Path

    from custom_components.tinycam.camera import TinyCamCamera

    placeholder = (
        Path(__file__).parents[1]
        / "custom_components/tinycam/brand/icon.png"
    ).read_bytes()
    client = Mock()
    client.async_get_still_image = AsyncMock(side_effect=[failure, b"jpeg-frame"])
    entity = TinyCamCamera(coordinator(hass), client, entry, 1, placeholder)

    assert await entity.async_camera_image() == placeholder
    assert entity.content_type == "image/png"
    assert await entity.async_camera_image(640, 480) == b"jpeg-frame"
    assert entity.content_type == "image/jpeg"
    client.async_get_still_image.assert_called_with(1, resolution="640x480")
