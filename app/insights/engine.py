"""The rule engine.

evaluate() turns a reading, a growth stage and the three loaded context
objects into a ranked list of advice cards. At most one card is produced
per rule group: when several rules in the same group match, an override
match always wins outright over every non-override match in that group,
regardless of severity; failing that, the highest severity match wins,
and a tie between equally severe matches keeps whichever rule appears
first in the YAML file. Selected rules are then ranked across groups by
severity first and rule group priority second, and the top four are
returned. With exactly four rule groups shipped in Task 5, that ranking
step never actually has to drop a card; it exists so the engine still
behaves correctly if a future rule set defines a fifth group.
"""

from app.insights.content import ContentPack
from app.insights.models import (
    RULE_GROUP_PRIORITY,
    SEVERITY_BY_YAML_WORD,
    SEVERITY_RANK,
    AdviceCard,
)
from app.insights.rules import Rule, RuleSet, rule_matches
from app.storage.models import Reading


def _select_for_group(matches: list[Rule]) -> Rule:
    overrides = [rule for rule in matches if rule.override]
    candidates = overrides if overrides else matches
    return max(candidates, key=lambda rule: SEVERITY_RANK[SEVERITY_BY_YAML_WORD[rule.severity]])


def evaluate(
    reading: Reading,
    stage: str,
    calibration: object,
    rules: RuleSet,
    content: ContentPack,
) -> list[AdviceCard]:
    """Return up to four advice cards, ranked by severity then rule group priority."""
    matches_by_group: dict[str, list[Rule]] = {}
    for rule in rules.rules:
        if rule_matches(rule, reading, stage, calibration):
            matches_by_group.setdefault(rule.group, []).append(rule)

    selected = [_select_for_group(matches) for matches in matches_by_group.values()]
    selected.sort(
        key=lambda rule: (
            SEVERITY_RANK[SEVERITY_BY_YAML_WORD[rule.severity]],
            RULE_GROUP_PRIORITY.get(rule.group, 0),
        ),
        reverse=True,
    )

    cards: list[AdviceCard] = []
    for rule in selected[:4]:
        entry = content.get(rule.content_key)
        cards.append(
            AdviceCard(
                icon=entry.icon,
                severity=SEVERITY_BY_YAML_WORD[rule.severity].value,
                headline=entry.headline_id,
                body=entry.body_id,
                subtitle_en=entry.subtitle_en,
                rule_group=rule.group,
            )
        )
    return cards
