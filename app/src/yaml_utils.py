from __future__ import annotations

from pathlib import Path
from typing import Any
import yaml


class IgnoreUnknownLoader(yaml.SafeLoader):
    """SafeLoader that tolerates unknown/custom YAML tags found in XSOAR content."""
    pass


def _ignore_unknown(loader: yaml.SafeLoader, tag_suffix: str, node: yaml.Node) -> Any:
    # Parse the underlying value normally
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


# Catch ANY unknown tag (e.g. tag:yaml.org,2002:value)
IgnoreUnknownLoader.add_multi_constructor("", _ignore_unknown)


def load_yaml(path: Path) -> dict:
    """Loads YAML safely while ignoring unknown tags. Always returns a dict."""
    with path.open("r", encoding="utf-8") as f:
        data = yaml.load(f, Loader=IgnoreUnknownLoader) or {}
    return data if isinstance(data, dict) else {}