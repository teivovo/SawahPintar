"""The declarative rule model.

A rule is data: a condition to test against a reading, either directly on
a raw metric or against a value derived through the calibration layer, an
optional growth stage filter, a severity and a content key. Nothing here
contains an agronomic threshold; every number a rule tests against comes
from the YAML file it was loaded from. See app/insights/engine.py for how
matched rules become ranked advice cards.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml

from app.insights.calibration import Calibration, classify_salinity, water_table_depth_cm
from app.insights.models import RULE_GROUPS, SEVERITY_BY_YAML_WORD, GrowthStage
from app.storage.models import Reading

# Each derived name maps to the raw metric it is computed from and the
# calibration function that computes it. Adding a third derived quantity
# means adding one entry here, not touching the matching logic below.
DERIVED_METRICS = {
    "salinity_class": ("conductivity", classify_salinity),
    "water_table_depth_cm": ("moisture", water_table_depth_cm),
}

_COMPARISONS = {
    "lt": lambda actual, value: actual < value,
    "le": lambda actual, value: actual <= value,
    "gt": lambda actual, value: actual > value,
    "ge": lambda actual, value: actual >= value,
    "eq": lambda actual, value: actual == value,
    "in": lambda actual, value: actual in value,
}

_VALID_STAGES = tuple(stage.value for stage in GrowthStage)


@dataclass(frozen=True)
class Condition:
    """One test against a reading, either a raw metric or a derived value."""

    source: str
    name: str
    op: str
    value: object

    def __post_init__(self) -> None:
        if self.source not in ("metric", "derived"):
            raise ValueError(f"condition source must be 'metric' or 'derived', got '{self.source}'")
        if self.op not in _COMPARISONS:
            raise ValueError(f"condition op must be one of {sorted(_COMPARISONS)}, got '{self.op}'")
        if self.source == "derived" and self.name not in DERIVED_METRICS:
            raise ValueError(f"unknown derived quantity: {self.name}")


@dataclass(frozen=True)
class Rule:
    """One declarative rule, loaded from YAML.

    override means this rule, when it matches, is the only candidate the
    engine considers for its group: no other rule in the same group may be
    selected instead, however severe. This is how the absolute flowering
    water suspension in Task 5 is implemented without any special case in
    the engine itself.
    """

    id: str
    group: str
    severity: str
    content_key: str
    condition: Condition | None = None
    stages: tuple[str, ...] | None = None
    override: bool = False


@dataclass(frozen=True)
class RuleSet:
    """An ordered collection of rules, loaded from one YAML file."""

    rules: tuple[Rule, ...]

    @classmethod
    def from_dict(cls, data: dict) -> "RuleSet":
        raw_rules = data.get("rules", [])
        rules: list[Rule] = []
        seen_ids: set[str] = set()

        for entry in raw_rules:
            rule_id = entry.get("id")
            if not rule_id:
                raise ValueError("every rule must have an id")
            if rule_id in seen_ids:
                raise ValueError(f"duplicate rule id: {rule_id}")
            seen_ids.add(rule_id)

            group = entry.get("group")
            if group not in RULE_GROUPS:
                raise ValueError(f"rule '{rule_id}' has an unknown group: {group}")

            severity = entry.get("severity")
            if severity not in SEVERITY_BY_YAML_WORD:
                raise ValueError(f"rule '{rule_id}' has an unknown severity: {severity}")

            content_key = entry.get("content_key")
            if not content_key:
                raise ValueError(f"rule '{rule_id}' must have a content_key")

            condition = None
            if "condition" in entry:
                raw_condition = entry["condition"]
                condition = Condition(
                    source=raw_condition["source"],
                    name=raw_condition["name"],
                    op=raw_condition["op"],
                    value=raw_condition["value"],
                )

            stages = None
            if "stages" in entry:
                stages = tuple(entry["stages"])
                for stage in stages:
                    if stage not in _VALID_STAGES:
                        raise ValueError(f"rule '{rule_id}' has an unknown growth stage: {stage}")

            if condition is None and stages is None:
                raise ValueError(f"rule '{rule_id}' must specify a condition, a stages list, or both")

            rules.append(
                Rule(
                    id=rule_id,
                    group=group,
                    severity=severity,
                    content_key=content_key,
                    condition=condition,
                    stages=stages,
                    override=bool(entry.get("override", False)),
                )
            )

        return cls(rules=tuple(rules))

    @classmethod
    def load(cls, path: str | Path) -> "RuleSet":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data or {})


def load_rules(path: str | Path) -> RuleSet:
    """Load a RuleSet from a YAML file. The name matches load_calibration and
    load_content so every loader in this package looks the same."""
    return RuleSet.load(path)


def rule_matches(rule: Rule, reading: Reading, stage: str, calibration: Calibration) -> bool:
    """Return whether a rule's condition and stage filter both hold.

    A missing raw metric fails the condition rather than raising, so a
    partial reading simply produces fewer matched rules instead of
    crashing the workshop.
    """
    if rule.stages is not None and stage not in rule.stages:
        return False

    if rule.condition is None:
        return True

    condition = rule.condition
    if condition.source == "metric":
        actual = reading.values.get(condition.name)
    else:
        metric_name, derive = DERIVED_METRICS[condition.name]
        raw = reading.values.get(metric_name)
        if raw is None:
            return False
        actual = derive(calibration, raw)

    if actual is None:
        return False

    return _COMPARISONS[condition.op](actual, condition.value)
