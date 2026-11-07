"""Defines the base UltraSync entity."""

from typing import Any, Optional

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class UltraSyncEntity(CoordinatorEntity):
    """Base class for a UltraSync entity."""

    def __init__(
        self,
        *,
        coordinator,
        entry_id: str,
        entry_name: str,
        name: str,
        zone: Optional[dict[str, Any]] = None,
        has_entity_name: bool = False,
    ) -> None:
        """Initialize the UltraSync entity."""

        super().__init__(coordinator)

        self._entry_id = entry_id
        self._attr_name = name

        # Newer entities are named relative to their device ("Chime" on the
        # device "MC KITCHEN"), which gives entity ids such as
        # switch.mc_kitchen_chime.  The older entities keep their full names,
        # so their names and ids do not change.
        self._attr_has_entity_name = has_entity_name

        if zone is None:
            # The panel itself is one device, named after what the user called
            # the integration when setting it up
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, entry_id)},
                name=entry_name,
                manufacturer="UltraSync",
            )
        else:
            # Each zone is its own device, connected through the panel, so its
            # state, battery and tamper entities are grouped together and the
            # zone can be placed in the area of its room
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{entry_id}_zone{zone['bank'] + 1:02}")},
                name=zone["name"],
                manufacturer="UltraSync",
                model=f"Zone {zone['bank'] + 1}",
                via_device_id=coordinator.config_entry.runtime_data.panel_device_id,
            )
