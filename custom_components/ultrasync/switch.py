"""Bypass and chime switches for the Interlogix/Hills ComNav UltraSync Hub."""

from __future__ import annotations

from typing import Any, Optional

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import CONF_NAME, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import UltraSyncConfigEntry
from .const import DEFAULT_NAME
from .coordinator import UltraSyncDataUpdateCoordinator
from .entity import UltraSyncEntity
from .vendor.ultrasync.common import NX595EVendor

# The panels whose area chime the library can switch
AREA_CHIME_VENDORS = (NX595EVendor.XGEN8,)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UltraSyncConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the zone bypass, zone chime and area chime switches."""
    coordinator = entry.runtime_data.coordinator
    entry_name = entry.data.get(CONF_NAME, DEFAULT_NAME)

    entities: list[SwitchEntity] = []

    # The first poll has already run, so the zones and areas are known.  The
    # bypass and chime state of a zone come from xGen8 panels only.
    for zone in coordinator.zones:
        # Some zones are programmed so that they can not be bypassed
        if "bypassed" in zone and zone.get("can_bypass", True):
            entities.append(
                UltraSyncZoneBypassSwitch(coordinator, entry.entry_id, entry_name, zone)
            )
        if "chime" in zone:
            entities.append(
                UltraSyncZoneChimeSwitch(coordinator, entry.entry_id, entry_name, zone)
            )

    if coordinator.hub.vendor in AREA_CHIME_VENDORS:
        for area in coordinator.areas:
            entities.append(
                UltraSyncAreaChimeSwitch(coordinator, entry.entry_id, entry_name, area)
            )

    async_add_entities(entities)


class _UltraSyncZoneSwitch(UltraSyncEntity, SwitchEntity):
    """A switch for one zone setting, read from the zone's poll data."""

    # The key of the zone dictionary that holds the state
    _state_key: str

    def __init__(
        self,
        coordinator: UltraSyncDataUpdateCoordinator,
        entry_id: str,
        entry_name: str,
        zone: dict[str, Any],
        *,
        key: str,
        label: str,
    ) -> None:
        """Initialize the zone switch."""
        # The zone's position on the panel (starting at 0)
        self._bank = zone["bank"]
        self._attr_unique_id = f"{entry_id}_zone{self._bank + 1:02}_{key}"

        super().__init__(
            coordinator=coordinator,
            entry_id=entry_id,
            entry_name=entry_name,
            name=label,
            zone=zone,
            has_entity_name=True,
        )

    @property
    def _zone(self) -> Optional[dict[str, Any]]:
        """Return this zone from the latest poll, if the panel still has it."""
        return next(
            (z for z in self.coordinator.zones if z["bank"] == self._bank), None
        )

    @property
    def available(self) -> bool:
        """Return false when the panel or the zone can not be read."""
        return super().available and self._zone is not None

    @property
    def is_on(self) -> Optional[bool]:
        """Return the state of the setting."""
        zone = self._zone
        return None if zone is None else bool(zone.get(self._state_key))


class UltraSyncZoneBypassSwitch(_UltraSyncZoneSwitch):
    """On while the zone is bypassed."""

    _attr_icon = "mdi:shield-off-outline"
    _state_key = "bypassed"

    # A bypassed zone does not trigger the alarm.  Home Assistant exposes new
    # switches to voice assistants by default, so these start disabled and
    # are enabled one by one where they are wanted.
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, entry_id, entry_name, zone) -> None:
        """Initialize the bypass switch."""
        super().__init__(
            coordinator, entry_id, entry_name, zone, key="bypass", label="Bypass"
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Bypass the zone."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop bypassing the zone."""
        await self._async_set(False)

    async def _async_set(self, state: bool) -> None:
        zone = self._bank + 1
        await self.coordinator.async_hub_command(
            f"set bypass={state} on zone {zone}",
            self.coordinator.hub.set_zone_bypass,
            zone=zone,
            state=state,
        )


class UltraSyncZoneChimeSwitch(_UltraSyncZoneSwitch):
    """On while the zone sounds the keypad chime when it opens."""

    _attr_icon = "mdi:bell-ring-outline"
    _attr_entity_category = EntityCategory.CONFIG
    _state_key = "chime"

    def __init__(self, coordinator, entry_id, entry_name, zone) -> None:
        """Initialize the zone chime switch."""
        super().__init__(
            coordinator, entry_id, entry_name, zone, key="chime", label="Chime"
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the zone chime on."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the zone chime off."""
        await self._async_set(False)

    async def _async_set(self, state: bool) -> None:
        zone = self._bank + 1
        await self.coordinator.async_hub_command(
            f"set chime={state} on zone {zone}",
            self.coordinator.hub.set_zone_chime,
            zone=zone,
            state=state,
        )


class UltraSyncAreaChimeSwitch(UltraSyncEntity, SwitchEntity):
    """On while the chime of an area is on."""

    _attr_icon = "mdi:bell-ring-outline"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator: UltraSyncDataUpdateCoordinator,
        entry_id: str,
        entry_name: str,
        area: dict[str, Any],
    ) -> None:
        """Initialize the area chime switch."""
        # The area's position on the panel (starting at 0)
        self._bank = area["bank"]
        self._attr_unique_id = f"{entry_id}_area{self._bank + 1:02}_chime"

        super().__init__(
            coordinator=coordinator,
            entry_id=entry_id,
            entry_name=entry_name,
            name=f"{entry_name} {area['name']} Chime",
        )

    @property
    def _area(self) -> Optional[dict[str, Any]]:
        """Return this area from the latest poll, if the panel still has it."""
        return next(
            (a for a in self.coordinator.areas if a["bank"] == self._bank), None
        )

    @property
    def available(self) -> bool:
        """Return false when the panel or the area can not be read."""
        return super().available and self._area is not None

    @property
    def is_on(self) -> Optional[bool]:
        """Return true while the area chime is on."""
        area = self._area
        return None if area is None else bool(area.get("states", {}).get("chime"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the area chime on."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the area chime off."""
        await self._async_set(False)

    async def _async_set(self, state: bool) -> None:
        area = self._bank + 1
        await self.coordinator.async_hub_command(
            f"set chime={state} on area {area}",
            self.coordinator.hub.set_area_chime,
            area=area,
            state=state,
        )
