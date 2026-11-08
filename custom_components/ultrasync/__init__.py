"""The Interlogix/Hills ComNav UltraSync Hub component."""

from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
import voluptuous as vol

from .const import (
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SERVICE_AWAY,
    SERVICE_BYPASS,
    SERVICE_DISARM,
    SERVICE_FIRE,
    SERVICE_MEDICAL,
    SERVICE_PANIC,
    SERVICE_STAY,
    SERVICE_SWITCH,
    SERVICE_UNBYPASS,
)
from .coordinator import UltraSyncDataUpdateCoordinator
from .vendor.ultrasync import AlarmScene

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.SIREN,
    Platform.EVENT,
    Platform.ALARM_CONTROL_PANEL,
]


@dataclass
class UltraSyncData:
    """The objects one UltraSync config entry keeps while it is loaded."""

    coordinator: UltraSyncDataUpdateCoordinator

    # The device registry id of the panel; the zone devices link to it
    panel_device_id: str

    # The dynamically created area, zone, output and history sensors, by id
    sensors: dict = field(default_factory=dict)


type UltraSyncConfigEntry = ConfigEntry[UltraSyncData]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate an old config entry."""
    if entry.version == 1 and entry.minor_version < 2:
        # Version 1.1 created a Battery and a Tamper sensor for every zone.
        # From 1.2 they are only created once the panel reports the
        # condition, so the sensors created up front are removed.
        ent_reg = er.async_get(hass)
        for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
            if ent.domain == "binary_sensor" and ent.unique_id.endswith(
                ("_battery", "_tamper")
            ):
                ent_reg.async_remove(ent.entity_id)

        hass.config_entries.async_update_entry(entry, minor_version=2)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: UltraSyncConfigEntry) -> bool:
    """Set up UltraSync from a config entry."""
    if not entry.options:
        options = {
            CONF_SCAN_INTERVAL: entry.data.get(
                CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
            ),
        }
        hass.config_entries.async_update_entry(entry, options=options)

    coordinator = UltraSyncDataUpdateCoordinator(hass, entry)

    # Raises ConfigEntryNotReady if the panel can not be reached
    await coordinator.async_config_entry_first_refresh()

    # Register the panel device before the platforms add their entities, so
    # the zone devices can link to it by its registry id
    panel = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.data.get(CONF_NAME, DEFAULT_NAME),
        manufacturer="UltraSync",
    )

    entry.runtime_data = UltraSyncData(
        coordinator=coordinator, panel_device_id=panel.id
    )

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    _async_register_services(hass, coordinator)

    return True


SERVICES = (
    SERVICE_AWAY,
    SERVICE_STAY,
    SERVICE_DISARM,
    SERVICE_FIRE,
    SERVICE_MEDICAL,
    SERVICE_PANIC,
    SERVICE_BYPASS,
    SERVICE_UNBYPASS,
    SERVICE_SWITCH,
)


async def async_unload_entry(hass: HomeAssistant, entry: UltraSyncConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # The services hold this entry's logged-in panel session.  Only one
        # entry is allowed, so nothing else is using them.
        for service in SERVICES:
            hass.services.async_remove(DOMAIN, service)

    return unload_ok


def _async_register_services(
    hass: HomeAssistant,
    coordinator: UltraSyncDataUpdateCoordinator,
) -> None:
    """Register integration-level services."""

    def _set_alarm(state: str) -> None:
        """Send an arm mode to every area, raising an error if it failed."""
        with coordinator.hub_lock:
            ok = coordinator.hub.set_alarm(state=state)

        if not ok:
            # The panel refused the command, could not be reached, or does not
            # support this mode (fire, medical and panic are ComNav only)
            raise HomeAssistantError(f"UltraSync could not set the alarm to {state}")

    def _alarm_service(state: str):
        """Return a service handler that sends one arm mode."""

        def handler(call: ServiceCall) -> None:
            _set_alarm(state)

        return handler

    def bypass(call: ServiceCall) -> None:
        """Service call to bypass a zone in UltraSync Hub."""
        with coordinator.hub_lock:
            ok = coordinator.hub.set_zone_bypass(state=True, zone=call.data["zone"])
        if not ok:
            raise HomeAssistantError(f"UltraSync could not bypass zone {call.data['zone']}")

    def unbypass(call: ServiceCall) -> None:
        """Service call to unbypass a zone in UltraSync Hub."""
        with coordinator.hub_lock:
            ok = coordinator.hub.set_zone_bypass(state=False, zone=call.data["zone"])
        if not ok:
            raise HomeAssistantError(f"UltraSync could not unbypass zone {call.data['zone']}")

    def switch(call: ServiceCall) -> None:
        """Service call to switch on/off an output control in UltraSync Hub."""
        with coordinator.hub_lock:
            ok = coordinator.hub.set_output_control(
                output=call.data["output"], state=call.data["state"]
            )
        if not ok:
            raise HomeAssistantError(
                f"UltraSync could not switch output {call.data['output']}"
            )

    no_fields = vol.Schema({})
    for service, state in (
        (SERVICE_AWAY, AlarmScene.AWAY),
        (SERVICE_STAY, AlarmScene.STAY),
        (SERVICE_DISARM, AlarmScene.DISARMED),
        (SERVICE_FIRE, AlarmScene.FIRE),
        (SERVICE_MEDICAL, AlarmScene.MEDICAL),
        (SERVICE_PANIC, AlarmScene.PANIC),
    ):
        hass.services.async_register(
            DOMAIN, service, _alarm_service(state), schema=no_fields
        )

    zone_schema = vol.Schema({vol.Required("zone"): vol.Coerce(int)})
    hass.services.async_register(DOMAIN, SERVICE_BYPASS, bypass, schema=zone_schema)
    hass.services.async_register(
        DOMAIN, SERVICE_UNBYPASS, unbypass, schema=zone_schema
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SWITCH,
        switch,
        schema=vol.Schema(
            {
                vol.Required("output"): vol.Coerce(int),
                vol.Required("state"): vol.All(vol.Coerce(int), vol.In([0, 1])),
            }
        ),
    )


async def _async_update_listener(hass: HomeAssistant, entry: UltraSyncConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)
