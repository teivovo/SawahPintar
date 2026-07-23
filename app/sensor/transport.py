"""Serial transport.

Two implementations share one protocol: a real pyserial port, and a fake used
by every test in this project so the whole pipeline runs without hardware.
"""

import time
from typing import Protocol

from app.sensor.profile import SensorProfile


class TransportError(Exception):
    """Raised for port level faults such as an unplugged dongle."""


class Transport(Protocol):
    """The surface the reader depends on."""

    @property
    def is_open(self) -> bool: ...

    def open(self) -> None: ...

    def close(self) -> None: ...

    def exchange(self, request: bytes, expect: int) -> bytes: ...


class SerialTransport:
    """A pyserial backed transport configured from a sensor profile."""

    def __init__(self, port: str, profile: SensorProfile) -> None:
        self._port = port
        self._profile = profile
        self._serial = None

    @property
    def is_open(self) -> bool:
        return self._serial is not None and self._serial.is_open

    def open(self) -> None:
        import serial

        try:
            self._serial = serial.Serial(
                port=self._port,
                baudrate=self._profile.baud,
                bytesize=self._profile.bytesize,
                parity=self._profile.parity,
                stopbits=self._profile.stopbits,
                timeout=self._profile.timeout,
            )
        except Exception as error:
            self._serial = None
            raise TransportError(f"could not open {self._port}: {error}") from error

        # The probe needs a moment after the port opens before it answers.
        time.sleep(0.2)

    def close(self) -> None:
        if self._serial is not None:
            try:
                self._serial.close()
            finally:
                self._serial = None

    def exchange(self, request: bytes, expect: int) -> bytes:
        if not self.is_open:
            raise TransportError(f"port {self._port} is not open")

        try:
            self._serial.reset_input_buffer()
            self._serial.write(request)
            return self._serial.read(expect)
        except Exception as error:
            try:
                self.close()
            except Exception:
                # A double fault: the port failed the exchange and then
                # failed to close cleanly too, for example because the
                # dongle was pulled mid read. The original TransportError
                # below must still be what escapes, not this secondary
                # failure, so it is swallowed here.
                pass
            raise TransportError(f"exchange failed on {self._port}: {error}") from error


class FakeTransport:
    """An in-memory transport that replays canned responses."""

    def __init__(
        self, responses: dict[bytes, bytes], fail_on_open: bool = False
    ) -> None:
        self._responses = responses
        self._fail_on_open = fail_on_open
        self._open = False
        self.sent: list[bytes] = []

    @property
    def is_open(self) -> bool:
        return self._open

    def open(self) -> None:
        if self._fail_on_open:
            raise TransportError("could not open fake port")
        self._open = True

    def close(self) -> None:
        self._open = False

    def exchange(self, request: bytes, expect: int) -> bytes:
        if not self._open:
            raise TransportError("fake port is not open")
        self.sent.append(request)
        return self._responses.get(request, b"")
