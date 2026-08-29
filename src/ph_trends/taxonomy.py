from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Category:
    key: str
    label: str
    patterns: tuple[re.Pattern[str], ...]


class Taxonomy:
    def __init__(self, *, version: str, categories: list[Category]) -> None:
        self.version = version
        self.categories = categories

    @classmethod
    def load(cls, path: str | Path | None = None) -> Taxonomy:
        if path:
            payload = json.loads(Path(path).read_text())
        else:
            payload = json.loads(files("ph_trends").joinpath("taxonomy.json").read_text())
        categories = [
            Category(
                key=key,
                label=value["label"],
                patterns=tuple(re.compile(pattern, re.IGNORECASE) for pattern in value["patterns"]),
            )
            for key, value in payload["categories"].items()
        ]
        return cls(version=payload["version"], categories=categories)

    def classify(self, post: dict[str, Any]) -> dict[str, list[str]]:
        topics = " ".join(post.get("topics", []))
        text = " ".join(str(post.get(field) or "") for field in ("name", "tagline", "description"))
        text = f"{text} {topics}"
        matches: dict[str, list[str]] = {}
        for category in self.categories:
            terms = sorted(
                {
                    match.group(0).lower()
                    for pattern in category.patterns
                    for match in pattern.finditer(text)
                }
            )
            if terms:
                matches[category.key] = terms
        return matches
