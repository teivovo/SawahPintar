"""The bilingual advice content pack.

Every entry pairs a Bahasa Indonesia headline and supporting line with an
English subtitle and an icon key, exactly as design spec section 8.3
describes. Every entry must be marked draft, so the loader refuses to load
an entry that omits the flag rather than silently defaulting it, which
would let un-reviewed wording ship without anyone deciding that on
purpose. This is the only place farmer-visible advice text may live: no
rule or engine code in this package should ever construct a headline or a
body string itself.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ContentEntry:
    """One bilingual advice text, keyed by content_key in the pack."""

    icon: str
    headline_id: str
    body_id: str
    subtitle_en: str
    draft: bool


@dataclass(frozen=True)
class ContentPack:
    """A set of content entries keyed by content_key."""

    entries: dict[str, ContentEntry]

    def get(self, key: str) -> ContentEntry:
        try:
            return self.entries[key]
        except KeyError:
            raise KeyError(f"content pack has no entry for key: {key}") from None

    @classmethod
    def from_dict(cls, data: dict) -> "ContentPack":
        entries: dict[str, ContentEntry] = {}
        for key, entry in data.items():
            for required in ("icon", "headline_id", "body_id", "subtitle_en", "draft"):
                if required not in entry:
                    raise ValueError(f"content entry '{key}' is missing required field: {required}")
            entries[key] = ContentEntry(
                icon=entry["icon"],
                headline_id=entry["headline_id"],
                body_id=entry["body_id"],
                subtitle_en=entry["subtitle_en"],
                draft=bool(entry["draft"]),
            )
        return cls(entries=entries)

    @classmethod
    def load(cls, path: str | Path) -> "ContentPack":
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data or {})


def load_content(path: str | Path) -> ContentPack:
    """Load a ContentPack from a YAML file. The name matches load_calibration
    and load_rules so every loader in this package looks the same."""
    return ContentPack.load(path)
