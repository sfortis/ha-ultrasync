"""Fault binary sensors for the Interlogix/Hills ComNav UltraSync Hub."""

from __future__ import annotations

import logging
from typing import Any, Optional

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import CONF_NAME, EntityCategory
from homeassistant.core import HomeAssistant
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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UltraSyncConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the panel problem sensor and the zone fault sensors."""
    coordinator = entry.runtime_data.coordinator
    entry_name = entry.data.get(CONF_NAME, DEFAULT_NAME)

    entities: list[BinarySensorEntity] = [
        UltraSyncProblemSensor(coordinator, entry.entry_id, entry_name)
    ]

    # The first poll has already run, so the zones are known.  Zone flags
    # come from newer versions of the ultrasync library and from xGen, xGen8
    # and ZeroWire panels only; without them there is nothing to report.
    for zone in coordinator.zones:
        if "flags" not in zone:
            continue

        for key, label, device_class, flag in ZONE_SENSORS:
            entities.append(
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

    async_add_entities(entities)


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
        self._attr_unique_id = f"{entry_id}_zone{self._bank + 1:02}_{key}"

        super().__init__(
            coordinator=coordinator,
            entry_id=entry_id,
            entry_name=entry_name,
            name=f"{entry_name} {zone['name']} {label}",
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
