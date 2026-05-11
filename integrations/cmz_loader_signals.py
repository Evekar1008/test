from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


MachineFamily = Literal["TA_TD", "TTL_TTS"]


@dataclass(frozen=True)
class PmcBit:
    address: int
    bit: int


@dataclass(frozen=True)
class CmzOutSignals:
    """Signals from lathe to loader. Read by Python."""

    machine_in_cycle: PmcBit
    chuck1_open: PmcBit
    chuck1_closed: PmcBit
    machine_position_ok: PmcBit

    no_alarm: PmcBit
    end_of_program: PmcBit
    loader_enable: PmcBit
    front_door_open: PmcBit
    door_closed_locked: PmcBit

    m474_executed: PmcBit
    cnc_on: PmcBit
    air_pressure_ok: PmcBit

    m475_executed: PmcBit
    m410_executed: PmcBit
    m411_executed: PmcBit
    m412_executed: PmcBit
    m413_executed: PmcBit
    m414_executed: PmcBit


@dataclass(frozen=True)
class CmzInSignals:
    """Signals from loader/Python to lathe. Written by Python."""

    cycle_start: PmcBit
    cycle_start_neg: PmcBit
    loader_inside: PmcBit
    loader_inside_neg: PmcBit

    open_chuck1: PmcBit
    close_chuck1: PmcBit
    open_chuck2: PmcBit
    close_chuck2: PmcBit

    tailstock_forward: PmcBit
    tailstock_backward: PmcBit
    air_blow: PmcBit
    loader_alarm: PmcBit
    open_door: PmcBit
    close_door: PmcBit

    end_m474: PmcBit
    loader_stopped: PmcBit
    loader_air_alarm: PmcBit
    end_m475: PmcBit
    end_sync_m_code: PmcBit


@dataclass(frozen=True)
class CmzSignalMap:
    machine_family: MachineFamily
    base: int
    out: CmzOutSignals
    in_: CmzInSignals


def get_loader_base(machine_family: MachineFamily) -> int:
    if machine_family == "TA_TD":
        return 2000
    if machine_family == "TTL_TTS":
        return 6100
    raise ValueError(
        f"Invalid CMZ machine family: {machine_family!r}. "
        "Expected 'TA_TD' or 'TTL_TTS'."
    )


def build_cmz_signal_map(machine_family: MachineFamily) -> CmzSignalMap:
    base = get_loader_base(machine_family)

    return CmzSignalMap(
        machine_family=machine_family,
        base=base,
        out=CmzOutSignals(
            machine_in_cycle=PmcBit(base + 50, 0),
            chuck1_open=PmcBit(base + 50, 3),
            chuck1_closed=PmcBit(base + 50, 4),
            machine_position_ok=PmcBit(base + 50, 7),
            no_alarm=PmcBit(base + 51, 1),
            end_of_program=PmcBit(base + 51, 3),
            loader_enable=PmcBit(base + 51, 4),
            front_door_open=PmcBit(base + 51, 5),
            door_closed_locked=PmcBit(base + 51, 7),
            m474_executed=PmcBit(base + 52, 3),
            cnc_on=PmcBit(base + 52, 5),
            air_pressure_ok=PmcBit(base + 52, 6),
            m475_executed=PmcBit(base + 53, 0),
            m410_executed=PmcBit(base + 53, 2),
            m411_executed=PmcBit(base + 53, 3),
            m412_executed=PmcBit(base + 53, 4),
            m413_executed=PmcBit(base + 53, 5),
            m414_executed=PmcBit(base + 53, 6),
        ),
        in_=CmzInSignals(
            cycle_start=PmcBit(base + 0, 0),
            cycle_start_neg=PmcBit(base + 0, 1),
            loader_inside=PmcBit(base + 0, 2),
            loader_inside_neg=PmcBit(base + 0, 3),
            open_chuck1=PmcBit(base + 0, 4),
            close_chuck1=PmcBit(base + 0, 5),
            open_chuck2=PmcBit(base + 0, 6),
            close_chuck2=PmcBit(base + 0, 7),
            tailstock_forward=PmcBit(base + 1, 0),
            tailstock_backward=PmcBit(base + 1, 1),
            air_blow=PmcBit(base + 1, 2),
            loader_alarm=PmcBit(base + 1, 3),
            open_door=PmcBit(base + 1, 5),
            close_door=PmcBit(base + 1, 6),
            end_m474=PmcBit(base + 2, 1),
            loader_stopped=PmcBit(base + 2, 2),
            loader_air_alarm=PmcBit(base + 2, 4),
            end_m475=PmcBit(base + 2, 6),
            end_sync_m_code=PmcBit(base + 3, 1),
        ),
    )
