"""Modbus RTU framing.

Hand-rolled rather than taken from a library. The protocol surface we need is
one function code, the implementation is small enough to test exhaustively,
and it was verified against the SN-3002 probe before this code was written.
"""


class ModbusError(Exception):
    """Raised when a response frame is malformed, mismatched or corrupt."""


def crc16(data: bytes) -> bytes:
    """Return the two byte Modbus CRC for data, low byte first."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def build_read_request(address: int, function: int, start: int, count: int) -> bytes:
    """Build a register read request frame."""
    if not 1 <= count <= 125:
        raise ValueError("count must be between 1 and 125")
    if not 0 <= address <= 247:
        raise ValueError("address must be between 0 and 247")
    body = bytes(
        [
            address,
            function,
            (start >> 8) & 0xFF,
            start & 0xFF,
            (count >> 8) & 0xFF,
            count & 0xFF,
        ]
    )
    return body + crc16(body)


def expected_response_length(count: int) -> int:
    """Return the total byte length of a well formed response."""
    return 5 + 2 * count


def parse_read_response(
    frame: bytes, address: int, function: int, count: int
) -> list[int]:
    """Validate a response frame and return its unsigned register values."""
    if len(frame) < 5:
        raise ModbusError(f"response too short: {len(frame)} bytes")

    if crc16(frame[:-2]) != frame[-2:]:
        raise ModbusError("CRC check failed")

    if frame[0] != address:
        raise ModbusError(f"unexpected address {frame[0]}, wanted {address}")

    if frame[1] == function | 0x80:
        raise ModbusError(f"device returned exception code {frame[2]}")

    if frame[1] != function:
        raise ModbusError(f"unexpected function {frame[1]}, wanted {function}")

    if frame[2] != 2 * count:
        raise ModbusError(f"unexpected byte count {frame[2]}, wanted {2 * count}")

    if len(frame) != expected_response_length(count):
        expected = expected_response_length(count)
        direction = "short" if len(frame) < expected else "long"
        raise ModbusError(
            f"response too {direction}: {len(frame)} bytes, wanted {expected}"
        )

    return [
        int.from_bytes(frame[3 + 2 * i : 5 + 2 * i], "big") for i in range(count)
    ]
