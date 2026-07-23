"""Advice models and growth stages.

Severity, GrowthStage and AdviceCard are the vocabulary every later module
in this package shares. Nothing here reads a file or talks to a sensor.
"""

from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    """Traffic light severity, three levels from least to most urgent.

    Design spec section 9.1: green for satisfactory, amber for attention
    needed, red for act now. The member names spell out the plain English
    reading of each level so rule authors write "severity: act_now" rather
    than memorising a colour. The values are fixed at "green", "amber" and
    "red" because the interface layer keys its CSS classes and its ranking
    table directly on these three strings.
    """

    GOOD = "green"
    ATTENTION = "amber"
    ACT_NOW = "red"


SEVERITY_BY_YAML_WORD = {
    "good": Severity.GOOD,
    "attention": Severity.ATTENTION,
    "act_now": Severity.ACT_NOW,
}

SEVERITY_RANK = {
    Severity.GOOD: 1,
    Severity.ATTENTION: 2,
    Severity.ACT_NOW: 3,
}


class GrowthStage(str, Enum):
    """The standard rice growth stage sequence, design spec section 8."""

    LAND_PREPARATION = "land_preparation"
    TRANSPLANTING = "transplanting"
    TILLERING = "tillering"
    PANICLE_INITIATION = "panicle_initiation"
    FLOWERING = "flowering"
    RIPENING = "ripening"


RULE_GROUPS = ("salinity", "water", "acidity", "nutrients")

# Higher number ranks higher. Matches the interface layer's
# RULE_GROUP_PRIORITY table exactly, so a card ranked here sorts the same
# way once it reaches the farmer-facing screen.
RULE_GROUP_PRIORITY = {
    "salinity": 4,
    "water": 3,
    "acidity": 2,
    "nutrients": 1,
}


@dataclass(frozen=True)
class AdviceCard:
    """One piece of advice ready to render.

    Field order and names match the shape the interface layer already
    assumes: icon key, severity, headline, body, English subtitle, rule
    group. See the Interfaces section of this plan's Task 1.
    """

    icon: str
    severity: str
    headline: str
    body: str
    subtitle_en: str
    rule_group: str
