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
