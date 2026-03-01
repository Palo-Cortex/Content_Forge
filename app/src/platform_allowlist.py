# app/src/platform_allowlist.py
from dataclasses import dataclass
from typing import Set


@dataclass(frozen=True)
class Allowlist:
    platform_scripts: Set[str]
    external_playbooks_by_name: Set[str]


DEFAULT_ALLOWLIST = Allowlist(
    platform_scripts={
        "SetAndHandleEmpty",
        "DeleteContext",
        "Print",
        "DBotAverageScore",
    },
    external_playbooks_by_name={
        "WildFire - Detonate file v2",
    },
)