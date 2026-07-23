"""Turning a profile and a transport into one reading."""

from datetime import datetime

from app.sensor.codec import (
    ModbusError,
    build_read_request,
    expected_response_length,
    parse_read_response,
)
from app.sensor.profile import SensorProfile, decode
from app.sensor.transport import Transport
from app.storage.models import Reading


class SensorReader:
    """Reads one probe according to its profile."""

    def __init__(
        self, sensor_id: str, profile: SensorProfile, transport: Transport
    ) -> None:
        self.sensor_id = sensor_id
        self.profile = profile
        self.transport = transport

    def read_once(self, now: datetime) -> Reading:
        """Run every read plan and return the decoded result.

        A TransportError propagates to the caller, because recovering a dead
        port is the poller's job. A ModbusError is contained here, because a
        single corrupt frame is expected occasionally on a long RS485 run.
        """
        if not self.transport.is_open:
            self.transport.open()

        raw: dict[int, int] = {}
        failures = 0

        for plan in self.profile.read_plans:
            request = build_read_request(
                self.profile.address, plan.function, plan.start, plan.count
            )
            frame = self.transport.exchange(
                request, expected_response_length(plan.count)
            )
            try:
                registers = parse_read_response(
                    frame, self.profile.address, plan.function, plan.count
                )
            except ModbusError:
                failures += 1
                continue

            for index, value in enumerate(registers):
                raw[plan.start + index] = value

        values, out_of_range = decode(self.profile, raw)

        if failures == len(self.profile.read_plans):
            quality = Reading.QUALITY_ERROR
        elif failures or out_of_range:
            quality = Reading.QUALITY_PARTIAL
        else:
            quality = Reading.QUALITY_OK

        return Reading(
            timestamp=now,
            sensor_id=self.sensor_id,
            values=values,
            quality=quality,
            source=Reading.SOURCE_LIVE,
        )
