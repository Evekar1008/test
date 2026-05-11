from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, cast


MachineFamily = Literal["TA_TD", "TTL_TTS"]
VALID_MACHINE_FAMILIES = {"TA_TD", "TTL_TTS"}


@dataclass(frozen=True)
class AppConfig:
    cmz_ip: str
    cmz_port: int
    cmz_machine_family: MachineFamily
    haenel_base_url: str


def _get_machine_family() -> MachineFamily:
    value = os.getenv("CMZ_MACHINE_FAMILY", "TA_TD").strip().upper()

    aliases = {
        "TD": "TA_TD",
        "TA": "TA_TD",
        "TA/TD": "TA_TD",
        "TA_TD": "TA_TD",
        "TTS": "TTL_TTS",
        "TTL": "TTL_TTS",
        "TTL/TTS": "TTL_TTS",
        "TTL_TTS": "TTL_TTS",
    }

    normalized = aliases.get(value, value)

    if normalized not in VALID_MACHINE_FAMILIES:
        raise RuntimeError(
            f"Invalid CMZ_MACHINE_FAMILY={value!r}. "
            "Valid values are TA_TD or TTL_TTS."
        )

    return cast(MachineFamily, normalized)


def load_config() -> AppConfig:
    return AppConfig(
        cmz_ip=os.getenv("CMZ_IP", "192.168.1.5"),
        cmz_port=int(os.getenv("CMZ_PORT", "8193")),
        cmz_machine_family=_get_machine_family(),
        haenel_base_url=os.getenv("HAENEL_BASE_URL", "http://192.168.1.20"),
    )
