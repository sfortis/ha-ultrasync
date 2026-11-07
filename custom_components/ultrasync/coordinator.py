"""Provides the UltraSync DataUpdateCoordinator."""
from datetime import timedelta
import logging
import threading
import time
from typing import Any, Callable

try:
    # Python 3.11+ has this built in; newer Home Assistant no longer ships
    # the async_timeout package
    from asyncio import timeout

except ImportError:
    from async_timeout import timeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PIN, CONF_SCAN_INTERVAL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from .vendor import ultrasync

from .const import (
    DOMAIN,
    EVENT_POLL_INTERVAL,
    EVENT_LOG_TYPE,
    EVENT_POLL_SIZE,
    EVENT_READ_PAGES,
    IGNORED_EVENT_CODES,
    SENSOR_UPDATE_LISTENER,
)
from .vendor.ultrasync.common import NX595EVendor

# Marks an event log that was empty when it was first read
_EMPTY_LOG = object()

_LOGGER = logging.getLogger(__name__)


class UltraSyncDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching UltraSync data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Initialize global UltraSync data updater."""
        config = entry.data
        self.hub = ultrasync.UltraSync(
            user=config[CONF_USERNAME],
            pin=config[CONF_PIN],
            host=config[CONF_HOST],
        )

        self._init = False

        # Polls and alarm panel commands run in different worker threads, but
        # share one panel session; this lock makes them take turns
        self.hub_lock = threading.Lock()

        # The areas from the last successful poll (used by the alarm panels)
        self.areas = []

        # The zones from the last successful poll (used by the binary sensors)
        self.zones = []

        # The system faults the panel reported on the last successful poll
        self.system_faults = []

        # The panel events that appeared since the previous poll, oldest
        # first (used by the event entity)
        self.new_events: list[dict[str, Any]] = []

        # The id of the newest panel event seen; None until the event log
        # has been read once, so old events are not replayed at start up
        self._last_event_id = None

        # When the event log is read next (time.monotonic), and the area
        # sequences at the last read; an area change triggers a read at once
        self._next_event_read = 0.0
        self._event_area_sequences = None

        # Used to track delta (for change tracking)
        self._area_delta = {}
        self._zone_delta = {}
        self._output_delta = {}
        self._history_delta = {}

        update_interval = timedelta(seconds=entry.options[CONF_SCAN_INTERVAL])

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> dict:
        """Fetch data from UltraSync Hub."""

        # initialize our response
        response = {}

        # The hub can sometimes take a very long time to respond; wait
        async with timeout(10):
            details = await self.hass.async_add_executor_job(self._details)

        # The event log is read after the details, with its own time limit,
        # so a slow event read never fails the poll
        self.new_events = []
        if details and self._event_read_due(details):
            self.new_events = await self._async_read_events()

        if not details:
            # The library logs the reason (timeout, refused login and so on).
            # Raising marks the entities unavailable, and on the first poll
            # makes Home Assistant retry the setup later.
            raise UpdateFailed("UltraSync panel did not return any data")

        # Update our details
        if details:
            # Keep the latest areas, zones and faults for the entities that
            # read them directly
            self.areas = details["areas"]
            self.zones = details["zones"]

            # Library versions before panel fault support do not send this
            self.system_faults = details.get("system_faults", [])

            async_dispatcher_send(
                self.hass,
                SENSOR_UPDATE_LISTENER,
                details["areas"],
                details["zones"],
                details["outputs"],
                details["history_data"]
            )

            # Process zone data
            for zone in details["zones"]:
                if self._zone_delta.get(zone["bank"]) != zone["sequence"]:
                    self.hass.bus.fire(
                        "ultrasync_zone_update",
                        {
                            "sensor": zone["bank"] + 1,
                            "name": zone["name"],
                            "status": zone["status"],
                        },
                    )

                    # Update our sequence
                    self._zone_delta[zone["bank"]] = zone["sequence"]

                # Set our state:
                response["zone{:0>2}_state".format(zone["bank"] + 1)] = zone[
                    "status"
                ]

            # Process history data (if present)
            for history in details["history_data"]:
                history_name = history["area_name"]
                sensor_id = "history_name{}state".format(history_name)
                state_value = "{} by {} at {}".format(history["action"], history["user"], history["timestamp"])
                response[sensor_id] = state_value

                # Fire event to get initial state
                self.hass.bus.fire(
                    "ultrasync_history_update",
                    {
                        "name": history_name,
                        "status": history["action"],
                        "timestamp": history["timestamp"],
                        "user": history["user"],
                    },
                )

            # Process area data
            for area in details["areas"]:
                area_changed = self._area_delta.get(area["bank"]) != area["sequence"]
                if area_changed:
                    self.hass.bus.fire(
                        "ultrasync_area_update",
                        {
                            "area": area["bank"] + 1,
                            "name": area["name"],
                            "status": area["status"],
                        },
                    )

                    # Update our sequence
                    self._area_delta[area["bank"]] = area["sequence"]

                    # Update our history when area state changes (if history data is present)
                    if "history" in details and details["history_data"]:
                        for history in details["history_data"]:
                            history_name = history["area_name"]
                            sensor_id = "history_name{}state".format(history_name)
                            state_value = "{} by {} at {}".format(history["action"], history["user"], history["timestamp"])
                            if history_name == area["name"]:
                               self.hass.bus.fire(
                                   "ultrasync_history_update",
                                   {
                                        "name": history_name,
                                        "status": history["action"],
                                        "timestamp": history["timestamp"],
                                        "user": history["user"],
                                   },
                               )
                               self._history_delta[history["area_name"]] = history["action"]
                               response[sensor_id] = state_value

                # Set our state:
                response["area{:0>2}_state".format(area["bank"] + 1)] = area[
                    "status"
                ]

            # Process output data (if present)
            output_index = 1
            for output in details["outputs"]:
                if self._output_delta.get(output["name"]) != output["state"]:
                    self.hass.bus.fire(
                        "ultrasync_output_update",
                        {
                            "name": output["name"],
                            "status": output["state"],
                        },
                    )

                    # Update our sequence
                    self._output_delta[output["name"]] = output["state"]

                # Set our state:
                response["output{}state".format(output_index)] = output[
                    "state"
                ]
                output_index += 1

        self._init = True

        # Return our response
        return response

    @property
    def supports_events(self) -> bool:
        """Return true if the library can read this panel's event log."""
        return self.hub.vendor is NX595EVendor.XGEN8

    def _details(self) -> dict:
        """Read the panel details, waiting for any alarm command to finish."""
        with self.hub_lock:
            return self.hub.details(max_age_sec=0)

    def _event_read_due(self, details: dict) -> bool:
        """Return true if the event log should be read on this poll.

        The log is read every EVENT_POLL_INTERVAL seconds, and at once when an
        area changes (arm, disarm or alarm).
        """
        if not self.supports_events:
            return False

        sequences = tuple(a.get("sequence") for a in details["areas"])
        now = time.monotonic()
        if now < self._next_event_read and sequences == self._event_area_sequences:
            return False

        self._next_event_read = now + EVENT_POLL_INTERVAL
        self._event_area_sequences = sequences
        return True

    async def _async_read_events(self) -> list[dict[str, Any]]:
        """Return the new panel events, or none if the log could not be read."""
        try:
            async with timeout(10):
                return await self.hass.async_add_executor_job(self._read_new_events)
        except Exception:  # noqa: BLE001
            # The event log is extra information; never fail a poll on it
            _LOGGER.debug("Reading the UltraSync event log failed", exc_info=True)
            return []

    def _read_events(self, start: int | None = None) -> list[dict[str, Any]] | None:
        """Read one page of the event log, newest first."""
        with self.hub_lock:
            return self.hub.events(
                count=EVENT_POLL_SIZE, start=start, event_type=EVENT_LOG_TYPE
            )

    def _read_new_events(self) -> list[dict[str, Any]]:
        """Return the events newer than the last one seen, oldest first."""
        events = self._read_events()
        if events is None:
            return []

        if self._last_event_id is None:
            # The first read only marks where the log is
            self._last_event_id = events[0].get("id") if events else _EMPTY_LOG
            return []

        if not events:
            return []

        new: list[dict[str, Any]] = []
        page = events
        complete = False
        for _ in range(EVENT_READ_PAGES):
            for event in page:
                if event.get("id") == self._last_event_id:
                    complete = True
                    break
                new.append(event)

            if complete:
                break

            oldest = page[-1].get("id")
            if (
                self._last_event_id is _EMPTY_LOG
                or len(page) < EVENT_POLL_SIZE
                or not isinstance(oldest, int)
                or oldest <= 0
            ):
                # The log has no older entries (or was empty before)
                complete = True
                break

            # More events arrived than one page holds; read further back
            page = self._read_events(start=oldest - 1)
            if not page:
                break

        if not complete:
            _LOGGER.warning(
                "More than %d UltraSync panel events arrived since the last read; "
                "the older ones were not reported",
                len(new),
            )

        self._last_event_id = events[0].get("id")
        return [e for e in reversed(new) if e.get("code") not in IGNORED_EVENT_CODES]

    async def async_hub_command(
        self, description: str, command: Callable[..., bool], **kwargs: Any
    ) -> None:
        """Send a command to the panel and refresh, raising if it failed."""

        def _send() -> bool:
            with self.hub_lock:
                return command(**kwargs)

        if not await self.hass.async_add_executor_job(_send):
            raise HomeAssistantError(f"UltraSync could not {description}")

        await self.async_request_refresh()
