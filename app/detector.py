"""Step-change detector for the probe insertion moment.

Watches for the sharp, simultaneous rise in moisture and conductivity that
happens when the probe is pushed into soil. This is deliberately a two
metric test: moisture alone can drift with humidity on the probe tip, and
conductivity alone can jump from a loose cable, but a probe going into soil
moves both together. See design spec section 9.1.
"""

from app.storage.models import Reading


class StepChangeDetector:
    """Detects the probe insertion moment from a stream of readings."""

    def __init__(
        self,
        moisture_rise: float = 15.0,
        conductivity_rise: float = 150.0,
        baseline_window: int = 3,
        cooldown_readings: int = 5,
    ) -> None:
        if baseline_window < 1:
            raise ValueError("baseline_window must be at least 1")
        self._moisture_rise = moisture_rise
        self._conductivity_rise = conductivity_rise
        self._baseline_window = baseline_window
        self._cooldown_readings = cooldown_readings
        self._baseline: list[tuple[float, float]] = []
        self._cooldown = 0

    def reset(self) -> None:
        """Clear the rolling baseline and any active cooldown."""
        self._baseline.clear()
        self._cooldown = 0

    def observe(self, reading: Reading) -> bool:
        """Feed one new reading and report whether it is an insertion moment.

        Returns True on the single reading where both moisture and
        conductivity first jump past their thresholds relative to the
        rolling baseline. A cooldown then suppresses repeat detections for
        cooldown_readings further calls, so one insertion fires once even
        though the probe stays in the soil for the rest of the reading.
        """
        if self._cooldown > 0:
            self._cooldown -= 1

        moisture = reading.values.get("moisture")
        conductivity = reading.values.get("conductivity")
        if moisture is None or conductivity is None:
            return False

        if not self._baseline:
            self._baseline.append((moisture, conductivity))
            return False

        baseline_moisture = sum(m for m, _ in self._baseline) / len(self._baseline)
        baseline_conductivity = sum(c for _, c in self._baseline) / len(self._baseline)

        moisture_jump = moisture - baseline_moisture >= self._moisture_rise
        conductivity_jump = conductivity - baseline_conductivity >= self._conductivity_rise

        if moisture_jump and conductivity_jump:
            if self._cooldown == 0:
                self._cooldown = self._cooldown_readings
                self._baseline = [(moisture, conductivity)]
                return True
            return False

        self._baseline.append((moisture, conductivity))
        if len(self._baseline) > self._baseline_window:
            self._baseline.pop(0)
        return False
