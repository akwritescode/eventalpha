from __future__ import annotations

from pathlib import Path

import yaml

from eventalpha.sources.rss import Feed


def load_feeds(path: Path) -> list[Feed]:
    data = yaml.safe_load(path.read_text())
    return [Feed(**f) for f in data["feeds"]]
