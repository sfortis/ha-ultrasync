"""Constants the Interlogix/Hills ComNav UltraSync Hub."""

DOMAIN = "ultrasync"

# Scan Time (in seconds)
DEFAULT_SCAN_INTERVAL = 1

DEFAULT_NAME = "UltraSync"

# Services
SERVICE_AWAY = "away"
SERVICE_STAY = "stay"
SERVICE_DISARM = "disarm"
SERVICE_BYPASS = "bypass"
SERVICE_UNBYPASS = "unbypass"
SERVICE_SWITCH = "switch"
SERVICE_PANIC = "panic"
SERVICE_MEDICAL = "medical"
SERVICE_FIRE = "fire"

SENSOR_UPDATE_LISTENER = "ultrasync_update_sensors"

# Zone conditions (as the ultrasync library names them) that mean a device
# needs attention.  Informational ones such as Entry Delay are left out.
ZONE_FLAG_LOW_BATTERY = "Low Battery"
ZONE_FLAG_TAMPER = "Tamper"
ZONE_FAULT_FLAGS = (
    "Tamper",
    "Trouble",
    "Low Battery",
    "Supervision Fault",
    "Test Fail",
    "Activity Fail",
    "Antimask",
    "Mains Failure",
    "RF Jam",
)

# The panel event log is read every EVENT_POLL_INTERVAL seconds, and at once
# when an area changes.  EVENT_POLL_SIZE newest events are read each time.
EVENT_POLL_INTERVAL = 30
EVENT_POLL_SIZE = 10

# When more events than one read holds arrived, at most this many reads go
# further back in the log
EVENT_READ_PAGES = 5

# The panel log the event entity reads.  The panel keeps a main log (0) and an
# alarm log (1).  The alarm log holds alarms, troubles (battery, mains,
# network), arm and disarm, cancels and bypasses, and keeps months of them.
# The main log is filled with Home Assistant's own logins: the panel ends a
# session after 10 minutes, so the library logs in again six times an hour,
# and the main log only covers about a week.
EVENT_LOG_TYPE = 1

# Contact ID codes left out of the event entity.  412 is a remote login, which
# Home Assistant itself causes every 10 minutes (only seen in the main log).
IGNORED_EVENT_CODES = ("412",)

# The event entity's event types, chosen from the Contact ID code
EVENT_TYPES = [
    "alarm",
    "alarm_restore",
    "trouble",
    "trouble_restore",
    "arm",
    "disarm",
    "bypass",
    "bypass_restore",
    "other",
]


def event_type(code: str | None, restore: bool) -> str:
    """Return the event entity type for a Contact ID code."""
    try:
        number = int(code)
    except (TypeError, ValueError):
        return "other"

    if 100 <= number < 200:
        return "alarm_restore" if restore else "alarm"
    if 300 <= number < 400:
        return "trouble_restore" if restore else "trouble"
    if 400 <= number < 410:
        # Contact ID reports an arm as the restore of an open/close event
        return "arm" if restore else "disarm"
    if 570 <= number < 580:
        return "bypass_restore" if restore else "bypass"
    return "other"
