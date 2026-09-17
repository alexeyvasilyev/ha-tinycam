"""Constants for the tinyCam Monitor integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "tinycam"

CONF_USE_SSL = "use_ssl"
CONF_VERIFY_SSL = "verify_ssl"

DEFAULT_PORT = 8083
DEFAULT_USE_SSL = False
DEFAULT_VERIFY_SSL = True
DEFAULT_SCAN_INTERVAL = 10

CONF_SCAN_INTERVAL = "scan_interval"
MIN_SCAN_INTERVAL = 10

DEFAULT_UPDATE_INTERVAL = timedelta(seconds=DEFAULT_SCAN_INTERVAL)

MANUFACTURER = "Tiny Solutions LLC"
MODEL_WEB_SERVER = "Web Server"
MODEL_CAMERA = "Camera"

# LED / light control modes, see /axis-cgi/io/lightcontrol.cgi
LED_MODE_ON = "on"
LED_MODE_OFF = "off"
LED_MODE_AUTO = "auto"
LED_MODES = [LED_MODE_ON, LED_MODE_OFF, LED_MODE_AUTO]
LED_MODE_TO_ACTION = {
    LED_MODE_ON: "L1:-100",
    LED_MODE_OFF: "L1:-0",
    LED_MODE_AUTO: "L1:-50",
}

# Stream profile, see root.StreamProfile
STREAM_PROFILE_MAIN = "main"
STREAM_PROFILE_SUB = "sub"
STREAM_PROFILE_AUTO = "auto"
STREAM_PROFILES = [STREAM_PROFILE_MAIN, STREAM_PROFILE_SUB, STREAM_PROFILE_AUTO]

# Event types tinyCam reports via get_cam_event_list
EVENT_TYPES = ["motion", "person", "vehicle", "pet", "face", "audio", "pin"]

ATTR_PRESET = "preset"
ATTR_PAN = "pan"
ATTR_TILT = "tilt"
ATTR_ZOOM = "zoom"
ATTR_TAG = "tag"
ATTR_STATE = "state"

SERVICE_PTZ_MOVE = "ptz_move"
SERVICE_PTZ_STOP = "ptz_stop"
SERVICE_PTZ_HOME = "ptz_home"
SERVICE_PTZ_GOTO_PRESET = "ptz_goto_preset"
SERVICE_PTZ_SAVE_PRESET = "ptz_save_preset"
SERVICE_SET_NOTIFICATIONS = "set_notifications"
