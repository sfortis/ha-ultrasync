"""Siren mute buttons for the Interlogix/Hills ComNav UltraSync Hub."""

from __future__ import annotations

from typing import Any, Optional

from homeassistant.components.button import ButtonEntity
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import UltraSyncConfigEntry
from .const import DEFAULT_NAME
from .coordinator import UltraSyncDataUpdateCoordinator
from .entity import UltraSyncEntity
from .siren import SIREN_VENDORS


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UltraSyncConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one siren mute button for every area of the panel."""
    coordinator = entry.runtime_data.coordinator
    if coordinator.hub.vendor not in SIREN_VENDORS:
        return

    entry_name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    async_add_entities(
        UltraSyncAreaSirenMuteButton(coordinator, entry.entry_id, entry_name, area)
        for area in coordinator.areas
    )


class UltraSyncAreaSirenMuteButton(UltraSyncEntity, ButtonEntity):
    """Silences the siren of one area without disarming it.

    It sends the same mute command as turning the area siren off, but it does
    not depend on the siren state.  The siren entity is on only while the
    panel sets the bit seen after the start command, and it is not known
    whether a real alarm sets that bit, so the button is the way to silence
    the siren of a real alarm from the dashboard.
    """

    _attr_icon = "mdi:volume-off"

    def __init__(
        self,
        coordinator: UltraSyncDataUpdateCoordinator,
        entry_id: str,
        entry_name: str,
        area: dict[str, Any],
    ) -> None:
        """Initialize the siren mute button."""
        # The area's position on the panel (starting at 0)
        self._bank = area["bank"]
        self._attr_unique_id = f"{entry_id}_area{self._bank + 1:02}_siren_mute"

        super().__init__(
            coordinator=coordinator,
            entry_id=entry_id,
            entry_name=entry_name,
            name=f"{entry_name} {area['name']} Siren Mute",
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

    async def async_press(self) -> None:
        """Silence the siren of the area."""
        area = self._bank + 1
        await self.coordinator.async_hub_command(
            f"mute the siren on area {area}",
            self.coordinator.hub.set_siren,
            area=area,
            state=False,
        )
