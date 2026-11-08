"""Area sirens for the Interlogix/Hills ComNav UltraSync Hub."""

from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, Optional

from homeassistant.components.siren import (
    ATTR_DURATION,
    SirenEntity,
    SirenEntityFeature,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later

from . import UltraSyncConfigEntry
from .alarm_control_panel import TRIGGERED_STATUS
from .const import DEFAULT_NAME
from .coordinator import UltraSyncDataUpdateCoordinator
from .entity import UltraSyncEntity
from .vendor.ultrasync.common import NX595EVendor

_LOGGER = logging.getLogger(__name__)

# The panels whose siren the library can start and silence
SIREN_VENDORS = (NX595EVendor.XGEN8,)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: UltraSyncConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one siren for every area of the panel."""
    coordinator = entry.runtime_data.coordinator
    if coordinator.hub.vendor not in SIREN_VENDORS:
        return

    entry_name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    async_add_entities(
        UltraSyncAreaSiren(coordinator, entry.entry_id, entry_name, area)
        for area in coordinator.areas
    )


class UltraSyncAreaSiren(UltraSyncEntity, SirenEntity):
    """The siren of one area.

    Turning it on starts the panel's (non-fire) siren.  Turning it off
    silences the siren and leaves the area armed or disarmed as it was.  The
    state is read from the panel, so the siren also shows as on when a real
    alarm sounds it.  The panel stops the siren by itself after its
    programmed siren time.
    """

    _attr_supported_features = (
        SirenEntityFeature.TURN_ON
        | SirenEntityFeature.TURN_OFF
        | SirenEntityFeature.DURATION
    )

    def __init__(
        self,
        coordinator: UltraSyncDataUpdateCoordinator,
        entry_id: str,
        entry_name: str,
        area: dict[str, Any],
    ) -> None:
        """Initialize the area siren."""
        # The area's position on the panel (starting at 0)
        self._bank = area["bank"]
        self._attr_unique_id = f"{entry_id}_area{self._bank + 1:02}_siren"

        # Cancels the pending turn off of a siren started with a duration
        self._cancel_off: Optional[CALLBACK_TYPE] = None

        # Whether a poll has shown the siren on since that turn off was
        # scheduled; only then does a poll showing it off mean it has stopped
        self._seen_on = False

        # Raised by every turn on and turn off, so that a command that
        # finishes after a newer one was sent does not schedule a turn off
        self._generation = 0

        super().__init__(
            coordinator=coordinator,
            entry_id=entry_id,
            entry_name=entry_name,
            name=f"{entry_name} {area['name']} Siren",
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
        """Return true while the panel reports the siren of the area on."""
        area = self._area
        return None if area is None else bool(area.get("states", {}).get("siren"))

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start the siren, and silence it again after the duration if given."""
        self._generation += 1
        generation = self._generation

        # If this fails, a turn off scheduled by an earlier call stays pending
        await self._async_set(True)

        if generation != self._generation:
            # A newer turn on or turn off was sent while this one waited
            return

        self._cancel_pending_off()
        duration = kwargs.get(ATTR_DURATION)
        if duration:
            self._seen_on = False
            self._cancel_off = async_call_later(
                self.hass, float(duration), self._async_off_after_duration
            )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Silence the siren."""
        self._generation += 1
        self._cancel_pending_off()
        await self._async_set(False)

    async def async_will_remove_from_hass(self) -> None:
        """Drop a pending turn off when the entity goes away."""
        self._cancel_pending_off()
        await super().async_will_remove_from_hass()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Drop the pending turn off once the panel has stopped the siren."""
        if self._cancel_off is not None:
            if self.is_on:
                self._seen_on = True
            elif self._seen_on:
                # The panel's siren time ended, or someone disarmed or
                # silenced it, so a later mute could only hit a new alarm
                self._cancel_pending_off()
        super()._handle_coordinator_update()

    async def _async_off_after_duration(self, _now: datetime) -> None:
        """Silence the siren once the requested duration has passed."""
        self._cancel_off = None

        area = self._area
        if area is not None and area.get("status") in TRIGGERED_STATUS:
            # The siren now sounds for a real alarm, which only a person
            # should silence
            _LOGGER.warning(
                "Not silencing the siren of area %s after the requested duration, "
                "because the area is in alarm (%s)",
                self._bank + 1,
                area.get("status"),
            )
            return

        try:
            await self._async_set(False)
        except HomeAssistantError as err:
            # Nobody waits for this call, so the failure can only be logged.
            # The panel still stops the siren after its own siren time.
            _LOGGER.error(
                "%s; the siren keeps sounding until the panel's siren time ends", err
            )

    def _cancel_pending_off(self) -> None:
        if self._cancel_off is not None:
            self._cancel_off()
            self._cancel_off = None

    async def _async_set(self, state: bool) -> None:
        area = self._bank + 1
        await self.coordinator.async_hub_command(
            f"set siren={state} on area {area}",
            self.coordinator.hub.set_siren,
            area=area,
            state=state,
        )
