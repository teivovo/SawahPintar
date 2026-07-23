"""Sensor profiles.

Vendor differences are handled as data, not code. A profile describes how to
talk to a probe and how to interpret the registers it returns, so a new model
can be supported in the field by editing JSON.

The SN-3002 profile's nitrogen_raw, phosphorus_raw and potassium_raw registers
are decoded here like any other register, but they are not independent
nutrient measurements. The manufacturer documents them as three functions of
one underlying conductivity reading, and the writable calibration registers
only scale and offset that single input, so the three outputs can never be
separated into real NPK values. See design spec section 8.4 for the full
evidence and the `notes` field carried in the profile JSON itself.
"""

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RegisterDef:
    """One named quantity held in one holding register."""

    name: str
    offset: int
    scale: float = 1.0
    signed: bool = False
    unit: str = ""
    minimum: float | None = None
    maximum: float | None = None

    def __post_init__(self) -> None:
        # decode() divides by scale, so a hand-authored profile with
        # scale: 0 (a typo for 1.0, or a blank left in by mistake) would
        # raise ZeroDivisionError deep inside decode() with no register
        # name attached. The module docstring invites field editing of
        # these JSON files, so the check belongs here, at construction,
        # where the error can name the offending register.
        if self.scale == 0:
            raise ValueError(f"register {self.name!r} has scale: 0, which cannot be divided by")


@dataclass(frozen=True)
class ReadPlan:
    """One request frame covering a contiguous run of registers."""

    function: int
    start: int
    count: int


@dataclass(frozen=True)
class SensorProfile:
    """Everything needed to read and interpret one model of probe."""

    key: str
    label: str
    address: int
    baud: int
    read_plans: tuple[ReadPlan, ...]
    registers: tuple[RegisterDef, ...]
    bytesize: int = 8
    parity: str = "N"
    stopbits: int = 1
    timeout: float = 1.0

    @classmethod
    def from_dict(cls, data: dict) -> "SensorProfile":
        for required in ("key", "label", "address", "baud", "read_plans", "registers"):
            if required not in data:
                raise ValueError(f"profile is missing required field: {required}")

        registers = tuple(RegisterDef(**entry) for entry in data["registers"])
        names = [register.name for register in registers]
        duplicates = {name for name in names if names.count(name) > 1}
        if duplicates:
            raise ValueError(f"duplicate register name: {sorted(duplicates)[0]}")

        return cls(
            key=data["key"],
            label=data["label"],
            address=data["address"],
            baud=data["baud"],
            read_plans=tuple(ReadPlan(**entry) for entry in data["read_plans"]),
            registers=registers,
            bytesize=data.get("bytesize", 8),
            parity=data.get("parity", "N"),
            stopbits=data.get("stopbits", 1),
            timeout=data.get("timeout", 1.0),
        )

    @classmethod
    def load(cls, path: str | Path) -> "SensorProfile":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def decode(
    profile: SensorProfile, raw: dict[int, int]
) -> tuple[dict[str, float], list[str]]:
    """Scale raw register words into named values.

    Returns the values and the names of any that fell outside the range the
    profile declares. Out of range values are still returned, because a
    facilitator needs to see a suspicious reading rather than have it hidden.
    """
    values: dict[str, float] = {}
    out_of_range: list[str] = []

    for register in profile.registers:
        if register.offset not in raw:
            continue

        word = raw[register.offset]
        if register.signed and word & 0x8000:
            word -= 0x10000

        value = word / register.scale
        values[register.name] = value

        below = register.minimum is not None and value < register.minimum
        above = register.maximum is not None and value > register.maximum
        if below or above:
            out_of_range.append(register.name)

    return values, out_of_range
