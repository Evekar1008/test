from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
import time
from typing import Any, Callable

from integrations.cmz_loader_signals import CmzSignalMap, PmcBit


@dataclass
class CmzLoaderStatus:
    connected: bool
    cnc_on: bool
    no_alarm: bool
    loader_enable: bool
    air_pressure_ok: bool
    machine_position_ok: bool
    chuck1_open: bool
    chuck1_closed: bool
    door_closed_locked: bool
    m474_executed: bool
    m475_executed: bool
    machine_in_cycle: bool


class CmzFocasClient:
    def __init__(
        self,
        ip: str,
        signal_map: CmzSignalMap,
        port: int = 8193,
        timeout_sec: float = 3.0,
        dry_run: bool = True,
        status_provider: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.ip = ip
        self.port = port
        self.timeout_sec = timeout_sec
        self.signals = signal_map
        self.dry_run = dry_run
        self.status_provider = status_provider
        self._lock = Lock()
        self._handle = None
        self._pmc_bits: dict[tuple[int, int], bool] = {}
        self._seed_simulated_ready_state()

    def _seed_simulated_ready_state(self) -> None:
        out = self.signals.out
        for bit in [
            out.cnc_on,
            out.no_alarm,
            out.loader_enable,
            out.air_pressure_ok,
            out.machine_position_ok,
            out.chuck1_closed,
            out.door_closed_locked,
        ]:
            self._pmc_bits[(bit.address, bit.bit)] = True

    def connect(self) -> None:
        """Open the FOCAS connection."""
        with self._lock:
            self._handle = object()

    def close(self) -> None:
        """Close the FOCAS connection."""
        with self._lock:
            self._handle = None

    def read_bit(self, bit: PmcBit) -> bool:
        """Read one PMC R bit."""
        with self._lock:
            service_value = self._service_signal_value(bit)
            if service_value is not None:
                return service_value
            return bool(self._pmc_bits.get((bit.address, bit.bit), False))

    def _service_signal_value(self, bit: PmcBit) -> bool | None:
        if not self.status_provider:
            return None
        cnc = (self.status_provider().get("cnc") or {})
        out = self.signals.out
        signal_by_bit = {
            out.cnc_on: "cnc_on",
            out.no_alarm: "no_alarm",
            out.loader_enable: "loader_enable",
            out.air_pressure_ok: "air_pressure_ok",
            out.machine_position_ok: "machine_position_ok",
            out.door_closed_locked: "door_closed_locked",
            out.m474_executed: "m474_executed",
            out.m475_executed: "m475_executed",
            out.machine_in_cycle: "cycle_running",
        }
        key = signal_by_bit.get(bit)
        if key is None or key not in cnc:
            return None
        return bool(cnc[key])

    def write_bit(self, bit: PmcBit, value: bool) -> None:
        """Write one PMC R bit using read-modify-write."""
        with self._lock:
            self._pmc_bits[(bit.address, bit.bit)] = bool(value)
            self._mirror_simulated_outputs(bit, bool(value))

    def _mirror_simulated_outputs(self, bit: PmcBit, value: bool) -> None:
        if not self.dry_run:
            return
        in_ = self.signals.in_
        out = self.signals.out
        if bit == in_.open_chuck1 and value:
            self._pmc_bits[(out.chuck1_open.address, out.chuck1_open.bit)] = True
            self._pmc_bits[(out.chuck1_closed.address, out.chuck1_closed.bit)] = False
        elif bit == in_.close_chuck1 and value:
            self._pmc_bits[(out.chuck1_open.address, out.chuck1_open.bit)] = False
            self._pmc_bits[(out.chuck1_closed.address, out.chuck1_closed.bit)] = True

    def pulse_bit(self, bit: PmcBit, duration_sec: float = 0.2) -> None:
        self.write_bit(bit, True)
        time.sleep(duration_sec)
        self.write_bit(bit, False)

    def set_signal_pair(self, positive: PmcBit, negative: PmcBit, active: bool) -> None:
        self.write_bit(positive, active)
        self.write_bit(negative, not active)

    def set_loader_inside(self, active: bool) -> None:
        in_ = self.signals.in_
        self.set_signal_pair(in_.loader_inside, in_.loader_inside_neg, active)

    def pulse_cycle_start(self) -> None:
        in_ = self.signals.in_
        self.set_signal_pair(in_.cycle_start, in_.cycle_start_neg, True)
        time.sleep(0.2)
        self.set_signal_pair(in_.cycle_start, in_.cycle_start_neg, False)

    def read_loader_status(self) -> CmzLoaderStatus:
        out = self.signals.out

        return CmzLoaderStatus(
            connected=True,
            cnc_on=self.read_bit(out.cnc_on),
            no_alarm=self.read_bit(out.no_alarm),
            loader_enable=self.read_bit(out.loader_enable),
            air_pressure_ok=self.read_bit(out.air_pressure_ok),
            machine_position_ok=self.read_bit(out.machine_position_ok),
            chuck1_open=self.read_bit(out.chuck1_open),
            chuck1_closed=self.read_bit(out.chuck1_closed),
            door_closed_locked=self.read_bit(out.door_closed_locked),
            m474_executed=self.read_bit(out.m474_executed),
            m475_executed=self.read_bit(out.m475_executed),
            machine_in_cycle=self.read_bit(out.machine_in_cycle),
        )

    def set_simulated_output(self, name: str, value: bool) -> None:
        out = self.signals.out
        bit = getattr(out, name)
        self.write_bit(bit, value)

    def safe_clear_commands(self) -> None:
        in_ = self.signals.in_

        for bit in [
            in_.open_chuck1,
            in_.close_chuck1,
            in_.open_door,
            in_.close_door,
            in_.end_sync_m_code,
        ]:
            self.write_bit(bit, False)

        self.set_signal_pair(in_.cycle_start, in_.cycle_start_neg, False)
        self.set_signal_pair(in_.loader_inside, in_.loader_inside_neg, False)
        self.write_bit(in_.loader_stopped, True)
