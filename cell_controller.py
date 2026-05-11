from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from queue import Empty, Queue
from threading import Event, Thread
import time
from typing import Any, Callable

from integrations.cmz_focas_client import CmzFocasClient
from integrations.haenel_client import HaenelClient


class CellState(str, Enum):
    IDLE = "Idle"
    WAITING_FOR_M474 = "Waiting for M474"
    PREPARE_LOAD = "Prepare load"
    REQUEST_HAENEL_SHELF = "Request Haenel shelf"
    WAIT_MACHINE_READY = "Wait machine ready"
    LOAD_PART = "Load part"
    ACK_M474 = "Ack M474"
    WAIT_CYCLE_COMPLETE = "Wait cycle complete"
    UNLOAD_PART = "Unload part"
    ACK_M475 = "Ack M475"
    ERROR = "Error"


@dataclass
class CellCommand:
    name: str
    payload: dict[str, Any]


class CellController:
    def __init__(self, service: Any, cmz: CmzFocasClient, haenel: HaenelClient) -> None:
        self.service = service
        self.cmz = cmz
        self.haenel = haenel
        self.commands: Queue[CellCommand] = Queue()
        self.stop_event = Event()
        self.thread: Thread | None = None
        self.state = CellState.IDLE
        self.active_job_id: str | None = None
        self.last_error = ""

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = Thread(target=self._run, name="cell-controller", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()

    def submit(self, name: str, payload: dict[str, Any] | None = None) -> None:
        self.commands.put(CellCommand(name=name, payload=payload or {}))

    def _run(self) -> None:
        self._log("Controller started")
        self._set_state(CellState.IDLE)
        while not self.stop_event.is_set():
            try:
                self._handle_commands()
                self._tick()
                time.sleep(0.10)
            except Exception as exc:
                self.last_error = str(exc)
                self._set_state(CellState.ERROR)
                self._log(f"Controller error: {exc}")
                self._safe_state()
                time.sleep(1.0)
        self._set_state(CellState.IDLE)
        self._log("Controller stopped")

    def _handle_commands(self) -> None:
        while True:
            try:
                command = self.commands.get_nowait()
            except Empty:
                return

            if command.name == "START_JOB":
                self.active_job_id = str(command.payload["job_id"])
                self.last_error = ""
                self._set_state(CellState.WAITING_FOR_M474)
                self._log(f"Started automatic sequence for {self.active_job_id}")

            elif command.name == "STOP":
                self._safe_state()
                self.active_job_id = None
                self._set_state(CellState.IDLE)
                self._log("Stopped automatic sequence")

            elif command.name == "RESET":
                self._safe_state()
                self.last_error = ""
                self.active_job_id = None
                self._set_state(CellState.IDLE)
                self._log("Controller reset")

    def _tick(self) -> None:
        if self.state in {CellState.IDLE, CellState.ERROR}:
            return

        status = self.cmz.read_loader_status()
        self._publish_cmz_status(status)

        if self.state == CellState.WAITING_FOR_M474:
            if status.m474_executed:
                self._set_state(CellState.PREPARE_LOAD)

        elif self.state == CellState.PREPARE_LOAD:
            self._require_machine_ready_for_loader(status)
            self._set_state(CellState.REQUEST_HAENEL_SHELF)

        elif self.state == CellState.REQUEST_HAENEL_SHELF:
            next_pick = self._get_next_pick()
            shelf = str(next_pick["shelf"])

            self.haenel.get_shelf(
                shelf=shelf,
                access_point=2,
                text_lines=[
                    f"Job: {self.active_job_id}",
                    f"Shelf: {shelf}",
                    f"Slot: {next_pick.get('slot_no', '')}",
                ],
            )

            if hasattr(self.service, "request_shelf"):
                self.service.request_shelf(shelf, access_point=2, actor="robot", override=True)

            self._set_state(CellState.WAIT_MACHINE_READY)

        elif self.state == CellState.WAIT_MACHINE_READY:
            self._require_machine_ready_for_loader(status)
            self._set_state(CellState.LOAD_PART)

        elif self.state == CellState.LOAD_PART:
            self._load_part_to_chuck()
            self._set_state(CellState.ACK_M474)

        elif self.state == CellState.ACK_M474:
            self._ack_m474()
            self._set_state(CellState.WAIT_CYCLE_COMPLETE)

        elif self.state == CellState.WAIT_CYCLE_COMPLETE:
            if status.m475_executed:
                self._set_state(CellState.UNLOAD_PART)

        elif self.state == CellState.UNLOAD_PART:
            self._unload_part_from_chuck()
            self._set_state(CellState.ACK_M475)

        elif self.state == CellState.ACK_M475:
            self._ack_m475()

            if hasattr(self.service, "complete_one_part"):
                self.service.complete_one_part()

            if self._production_is_active():
                self._set_state(CellState.WAITING_FOR_M474)
            else:
                self.active_job_id = None
                self._set_state(CellState.IDLE)

    def _require_machine_ready_for_loader(self, status: Any) -> None:
        missing = []

        if not status.cnc_on:
            missing.append("CNC ON")
        if not status.no_alarm:
            missing.append("No alarm")
        if not status.loader_enable:
            missing.append("Loader Enable")
        if not status.air_pressure_ok:
            missing.append("Air pressure OK")
        if not status.machine_position_ok:
            missing.append("Machine position OK")

        if missing:
            raise RuntimeError("Machine not ready for loader: " + ", ".join(missing))

    def _load_part_to_chuck(self) -> None:
        in_ = self.cmz.signals.in_

        self.cmz.set_loader_inside(True)

        self.cmz.write_bit(in_.open_chuck1, True)
        self._wait_until(lambda: self.cmz.read_loader_status().chuck1_open, "Chuck 1 did not open")
        self.cmz.write_bit(in_.open_chuck1, False)

        # TODO: Insert robot movement here:
        # - pick part from Haenel/access location
        # - place part in chuck

        self.cmz.write_bit(in_.close_chuck1, True)
        self._wait_until(lambda: self.cmz.read_loader_status().chuck1_closed, "Chuck 1 did not close")
        self.cmz.write_bit(in_.close_chuck1, False)

        self.cmz.set_loader_inside(False)

    def _unload_part_from_chuck(self) -> None:
        in_ = self.cmz.signals.in_

        self.cmz.set_loader_inside(True)

        self.cmz.write_bit(in_.open_chuck1, True)
        self._wait_until(lambda: self.cmz.read_loader_status().chuck1_open, "Chuck 1 did not open")
        self.cmz.write_bit(in_.open_chuck1, False)

        # TODO: Insert robot movement here:
        # - pick finished part from chuck
        # - place finished part to configured destination

        self.cmz.set_loader_inside(False)

    def _ack_m474(self) -> None:
        in_ = self.cmz.signals.in_

        self.cmz.write_bit(in_.end_m474, True)
        self._wait_until(lambda: not self.cmz.read_loader_status().m474_executed, "M474 did not drop")
        self.cmz.write_bit(in_.end_m474, False)

    def _ack_m475(self) -> None:
        in_ = self.cmz.signals.in_

        self.cmz.write_bit(in_.end_m475, True)
        self._wait_until(lambda: not self.cmz.read_loader_status().m475_executed, "M475 did not drop")
        self.cmz.write_bit(in_.end_m475, False)

    def _wait_until(
        self,
        predicate: Callable[[], bool],
        error_message: str,
        timeout_sec: float = 10.0,
    ) -> None:
        deadline = time.monotonic() + timeout_sec

        while time.monotonic() < deadline:
            if self.stop_event.is_set():
                raise RuntimeError("Controller stopped")
            if predicate():
                return
            time.sleep(0.05)

        raise TimeoutError(error_message)

    def _safe_state(self) -> None:
        try:
            self.cmz.safe_clear_commands()
        except Exception as exc:
            self._log(f"Could not clear CMZ commands: {exc}")

    def _set_state(self, state: CellState) -> None:
        self.state = state

        if hasattr(self.service, "update_controller_status"):
            self.service.update_controller_status(
                state=state.value,
                running=self.thread is not None and self.thread.is_alive(),
                last_error=self.last_error,
            )

    def _publish_cmz_status(self, status: Any) -> None:
        if hasattr(self.service, "update_machine_signals"):
            self.service.update_machine_signals(
                "focas",
                {
                    "cnc": {
                        "machine_ready": status.cnc_on and status.no_alarm,
                        "alarm_active": not status.no_alarm,
                        "cycle_running": status.machine_in_cycle,
                        "loader_enable": status.loader_enable,
                        "machine_position_ok": status.machine_position_ok,
                        "m474_executed": status.m474_executed,
                        "m475_executed": status.m475_executed,
                    }
                },
            )

    def _get_next_pick(self) -> dict[str, Any]:
        state = self.service.get_state()
        next_pick = state.get("production_order", {}).get("next_pick")
        if not next_pick:
            raise RuntimeError("No next pick available")
        return next_pick

    def _production_is_active(self) -> bool:
        state = self.service.get_state()
        return bool(state.get("production_order", {}).get("active"))

    def _log(self, message: str) -> None:
        if hasattr(self.service, "_log"):
            self.service._log("controller", message)
