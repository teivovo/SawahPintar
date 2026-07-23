"""Register inspector: a small OpenModScan.

Lets an operator read arbitrary registers from a port to confirm a new
sensor's layout in the field, without editing a profile first. Uses the
same codec and transport as the rest of the sensor layer, so a reading
taken here means exactly what a reading taken by the poller means. See
design spec section 6.
"""

from app.sensor.codec import (
    ModbusError,
    build_read_request,
    expected_response_length,
    parse_read_response,
)
from app.sensor.profile import SensorProfile
from app.sensor.transport import SerialTransport, Transport, TransportError

__all__ = [
    "ModbusError",
    "TransportError",
    "Transport",
    "read_registers",
    "open_transport_for_inspection",
]


def read_registers(
    transport: Transport, address: int, function: int, start: int, count: int
) -> list[int]:
    """Open transport if needed, issue one read, return raw register values.

    Raises TransportError if the port cannot be reached and ModbusError if
    the response is malformed. The caller decides how to present either to
    an operator.
    """
    if not transport.is_open:
        transport.open()
    request = build_read_request(address, function, start, count)
    frame = transport.exchange(request, expected_response_length(count))
    return parse_read_response(frame, address, function, count)


def open_transport_for_inspection(
    port: str,
    baud: int = 4800,
    bytesize: int = 8,
    parity: str = "N",
    stopbits: int = 1,
    timeout: float = 1.0,
) -> SerialTransport:
    """Build a bare transport for the inspector.

    The register inspector does not know the target device's register map
    yet, since discovering it is the point, so this builds a scratch
    profile carrying only the serial parameters SerialTransport needs to
    open the port. The address it declares is unused when opening a port;
    the caller supplies the real address separately to read_registers.
    """
    scratch_profile = SensorProfile.from_dict(
        {
            "key": "inspector",
            "label": "Register inspector scratch profile",
            "address": 1,
            "baud": baud,
            "bytesize": bytesize,
            "parity": parity,
            "stopbits": stopbits,
            "timeout": timeout,
            "read_plans": [{"function": 3, "start": 0, "count": 1}],
            "registers": [],
        }
    )
    return SerialTransport(port, scratch_profile)
