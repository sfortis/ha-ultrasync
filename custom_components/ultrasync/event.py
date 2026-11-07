"""The panel event log of the Interlogix/Hills ComNav UltraSync Hub."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import UltraSyncConfigEntry
from .const import DEFAULT_NAME, EVENT_TYPES, event_type
from .coordinator import UltraSyncDataUpdateCoordinator
from .entity import UltraSyncEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UltraSyncConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the panel event entity."""
    coordinator = entry.runtime_data.coordinator

    # The library reads the event log of xGen8 panels only
    if not coordinator.supports_events:
        return

    async_add_entities(
        [
            UltraSyncPanelEvent(
                coordinator,
                entry.entry_id,
                entry.data.get(CONF_NAME, DEFAULT_NAME),
            )
        ]
    )


class UltraSyncPanelEvent(UltraSyncEntity, EventEntity):
    """Fires for every new entry in the panel's event log."""

    _attr_event_types = EVENT_TYPES
    _attr_icon = "mdi:history"

    def __init__(
        self,
        coordinator: UltraSyncDataUpdateCoordinator,
        entry_id: str,
        entry_name: str,
    ) -> None:
        """Initialize the panel event entity."""
        self._attr_unique_id = f"{entry_id}_panel_event"

        super().__init__(
            coordinator=coordinator,
            entry_id=entry_id,
            entry_name=entry_name,
            name=f"{entry_name} Panel Event",
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Trigger one event for each new entry of the panel's event log."""
        if not self.coordinator.new_events:
            # Nothing new; still let availability changes through
            super()._handle_coordinator_update()
            return

        # An event entity keeps only its last event, so the state is written
        # after each one; otherwise only the last event of a poll is recorded
        for event in self.coordinator.new_events:
            self._trigger_event(
                event_type(event.get("code"), event.get("restore", False)),
                self._attributes(event),
            )
            self.async_write_ha_state()

    def _attributes(self, event: dict[str, Any]) -> dict[str, Any]:
        """Return the event data, with zone and area names added."""
        zone_name = next(
            (z["name"] for z in self.coordinator.zones if z["bank"] + 1 == event.get("zone")),
            None,
        )
        area_name = next(
            (a["name"] for a in self.coordinator.areas if a["bank"] + 1 == event.get("area")),
            None,
        )
        when = event.get("time")

        return {
            "description": event.get("description"),
            "code": event.get("code"),
            "restore": event.get("restore"),
            "zone": event.get("zone"),
            "zone_name": zone_name,
            "area": event.get("area"),
            "area_name": area_name,
            "user": event.get("user"),
            "user_name": event.get("user_name"),
            "panel_time": when.isoformat() if when else None,
        }
