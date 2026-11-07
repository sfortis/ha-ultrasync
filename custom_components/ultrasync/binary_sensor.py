"""Fault binary sensors for the Interlogix/Hills ComNav UltraSync Hub."""

from __future__ import annotations

import logging
from typing import Any, Optional

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import CONF_NAME, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import UltraSyncConfigEntry
from .const import (
    DEFAULT_NAME,
    ZONE_FAULT_FLAGS,
    ZONE_FLAG_LOW_BATTERY,
    ZONE_FLAG_TAMPER,
)
from .coordinator import UltraSyncDataUpdateCoordinator
from .entity import UltraSyncEntity

_LOGGER = logging.getLogger(__name__)

# The zone binary sensors: (unique id suffix, name suffix, device class, flag)
ZONE_SENSORS = (
    ("battery", "Battery", BinarySensorDeviceClass.BATTERY, ZONE_FLAG_LOW_BATTERY),
    ("tamper", "Tamper", BinarySensorDeviceClass.TAMPER, ZONE_FLAG_TAMPER),
)


# The area binary sensors, read from the area's "states" dictionary
AREA_SENSORS = (
    {"key": "night", "label": "Night Mode", "icon": "mdi:weather-night", "category": None},
    {
        "key": "walk_test",
        "label": "Walk Test",
        "icon": "mdi:walk",
        "category": EntityCategory.DIAGNOSTIC,
    },
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UltraSyncConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the panel problem sensor and the zone fault sensors."""
    coordinator = entry.runtime_data.coordinator
    entry_name = entry.data.get(CONF_NAME, DEFAULT_NAME)

    # The panel does not say which zones have a battery or a tamper switch.
    # A zone's Battery or Tamper sensor is therefore created the first time
    # the panel reports that condition on the zone, and is kept from then on
    # because its entity stays in the entity registry.
    registered = {
        e.unique_id
        for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        if e.domain == "binary_sensor"
    }
    added: set[str] = set()

    def _new_zone_sensors() -> list[BinarySensorEntity]:
        """Return the zone sensors that are due and not added yet."""
        new: list[BinarySensorEntity] = []
        for zone in coordinator.zones:
            # Zone flags come from xGen, xGen8 and ZeroWire panels only
            if "flags" not in zone:
                continue

            for key, label, device_class, flag in ZONE_SENSORS:
                unique_id = zone_flag_unique_id(entry.entry_id, zone["bank"], key)
                if unique_id in added:
                    continue
                if unique_id not in registered and flag not in zone["flags"]:
                    continue

                added.add(unique_id)
                new.append(
                    UltraSyncZoneFlagSensor(
                        coordinator,
                        entry.entry_id,
                        entry_name,
                        zone,
                        key=key,
                        label=label,
                        device_class=device_class,
                        flag=flag,
                    )
                )
        return new

    # Night mode and walk test come from xGen, xGen8 and ZeroWire panels
    area_sensors: list[BinarySensorEntity] = [
        UltraSyncAreaStateSensor(coordinator, entry.entry_id, entry_name, area, **spec)
        for area in coordinator.areas
        for spec in AREA_SENSORS
        if spec["key"] in area.get("states", {})
    ]

    # The first poll has already run, so the zones and areas are known
    async_add_entities(
        [UltraSyncProblemSensor(coordinator, entry.entry_id, entry_name)]
        + area_sensors
        + _new_zone_sensors()
    )

    @callback
    def _async_add_reported_zone_sensors() -> None:
        """Add the sensor of a condition a zone reports for the first time."""
        if new := _new_zone_sensors():
            async_add_entities(new)

    entry.async_on_unload(coordinator.async_add_listener(_async_add_reported_zone_sensors))


def zone_flag_unique_id(entry_id: str, bank: int, key: str) -> str:
    """Return the unique id of a zone's Battery or Tamper sensor."""
    return f"{entry_id}_zone{bank + 1:02}_{key}"


def _zone_faults(zone: dict[str, Any]) -> list[str]:
    """Return the conditions of a zone that need attention."""
    return [f for f in zone.get("flags", []) if f in ZONE_FAULT_FLAGS]


class UltraSyncProblemSensor(UltraSyncEntity, BinarySensorEntity):
    """On when the panel reports a system fault or a zone needs attention."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator: UltraSyncDataUpdateCoordinator,
        entry_id: str,
        entry_name: str,
    ) -> None:
        """Initialize the panel problem sensor."""
        self._attr_unique_id = f"{entry_id}_problem"

        super().__init__(
            coordinator=coordinator,
            entry_id=entry_id,
            entry_name=entry_name,
            name=f"{entry_name} Problem",
        )

    def _faults(self) -> list[str]:
        """Return every fault as text, system faults first."""
        faults = [f"System: {f}" for f in self.coordinator.system_faults]
        for zone in self.coordinator.zones:
            for flag in _zone_faults(zone):
                faults.append(f"{zone['name']}: {flag}")
        return faults

    @property
    def is_on(self) -> bool:
        """Return true when anything needs attention."""
        return bool(self._faults())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the list of faults."""
        return {"faults": self._faults()}


class UltraSyncZoneFlagSensor(UltraSyncEntity, BinarySensorEntity):
    """On when the panel reports one condition, such as Low Battery, on a zone."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: UltraSyncDataUpdateCoordinator,
        entry_id: str,
        entry_name: str,
        zone: dict[str, Any],
        *,
        key: str,
        label: str,
        device_class: BinarySensorDeviceClass,
        flag: str,
    ) -> None:
        """Initialize the zone condition sensor."""
        # The zone's position on the panel (starting at 0)
        self._bank = zone["bank"]
        self._flag = flag

        self._attr_device_class = device_class
        self._attr_unique_id = zone_flag_unique_id(entry_id, self._bank, key)

        super().__init__(
            coordinator=coordinator,
            entry_id=entry_id,
            entry_name=entry_name,
            name=f"{entry_name} {zone['name']} {label}",
            zone=zone,
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
        """Return true when the panel reports the condition on this zone."""
        zone = self._zone
        if zone is None:
            return None
        return self._flag in zone.get("flags", [])


class UltraSyncAreaStateSensor(UltraSyncEntity, BinarySensorEntity):
    """On while an area is in a mode such as night mode or walk test."""

    def __init__(
        self,
        coordinator: UltraSyncDataUpdateCoordinator,
        entry_id: str,
        entry_name: str,
        area: dict[str, Any],
        *,
        key: str,
        label: str,
        icon: str,
        category: Optional[EntityCategory],
    ) -> None:
        """Initialize the area mode sensor."""
        # The area's position on the panel (starting at 0)
        self._bank = area["bank"]
        self._key = key

        self._attr_icon = icon
        self._attr_entity_category = category
        self._attr_unique_id = f"{entry_id}_area{self._bank + 1:02}_{key}"

        super().__init__(
            coordinator=coordinator,
            entry_id=entry_id,
            entry_name=entry_name,
            name=f"{entry_name} {area['name']} {label}",
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
        """Return true while the area is in this mode."""
        area = self._area
        if area is None:
            return None
        return bool(area.get("states", {}).get(self._key))
