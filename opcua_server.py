from __future__ import annotations

from threading import Event, Thread
import time
from typing import Any, Dict

try:
    from opcua import Server
except Exception:  # pragma: no cover - development dependency may be absent
    Server = None  # type: ignore[assignment]


class OpcUaSimulator:
    """Small OPC UA server used to simulate machine-side signals during development."""

    def __init__(
        self,
        service: Any,
        endpoint: str = "opc.tcp://0.0.0.0:4840/production-cell/sim/",
        namespace_uri: str = "urn:bergsli:production-cell:simulation",
    ) -> None:
        self.service = service
        self.endpoint = endpoint
        self.namespace_uri = namespace_uri
        self.stop_event = Event()
        self.thread: Thread | None = None
        self.server: Any = None
        self.variables: Dict[str, Any] = {}
        self.last_values: Dict[str, Any] = {}

    @property
    def is_running(self) -> bool:
        return bool(self.thread and self.thread.is_alive())

    def start(self) -> bool:
        if Server is None:
            self.service.set_opcua_status(enabled=False, running=False, last_error="Install package 'opcua' to enable the simulator")
            return False
        if self.is_running:
            return True
        self.stop_event.clear()
        self.thread = Thread(target=self._run, name="opcua-simulator", daemon=True)
        self.thread.start()
        return True

    def stop(self) -> None:
        self.stop_event.set()

    def _add_var(self, folder: Any, namespace_index: int, path: str, initial_value: Any) -> None:
        name = path.split("/")[-1]
        var = folder.add_variable(namespace_index, name, initial_value)
        var.set_writable()
        self.variables[path] = var
        self.last_values[path] = initial_value

    def _run(self) -> None:
        server_cls = Server
        if server_cls is None:
            self.service.set_opcua_status(enabled=False, running=False, last_error="Install package 'opcua' to enable the simulator")
            return
        try:
            self.server = server_cls()
            self.server.set_endpoint(self.endpoint)
            self.server.set_server_name("Bergsli Production Cell Development Simulator")
            namespace_index = self.server.register_namespace(self.namespace_uri)
            root = self.server.nodes.objects.add_object(namespace_index, "ProductionCell")

            folders = {
                "Cell": root.add_object(namespace_index, "Cell"),
                "Safety": root.add_object(namespace_index, "Safety"),
                "LeanLift": root.add_object(namespace_index, "LeanLift"),
                "Robot": root.add_object(namespace_index, "Robot"),
                "CNC": root.add_object(namespace_index, "CNC"),
            }

            node_defaults = {
                "Cell/Heartbeat": 0,
                "Cell/Mode": "Automatic",
                "Cell/Command": "",
                "Cell/Message": "",
                "Cell/ActiveJob": "",
                "Cell/LastEvent": "",
                "Safety/SafetyOk": True,
                "Safety/EmergencyStopActive": False,
                "Safety/GatesClosed": True,
                "Safety/ScannerClear": True,
                "Safety/LastTrip": "None",
                "LeanLift/CurrentShelf": 1,
                "LeanLift/AccessPoint": 2,
                "LeanLift/RobotShelf": "1",
                "LeanLift/OperatorShelf": "1",
                "LeanLift/TrayPresent": True,
                "LeanLift/TrayExtended": False,
                "LeanLift/DoorClosed": True,
                "LeanLift/AlarmActive": False,
                "LeanLift/StatusMessage": "Ready",
                "Robot/Ready": True,
                "Robot/Busy": False,
                "Robot/Fault": False,
                "Robot/AtHome": True,
                "Robot/PartInGripper": False,
                "Robot/StationComplete": False,
                "Robot/ActiveTask": "Idle",
                "Robot/NextPick": "",
                "Robot/PlaceTarget": "",
                "Robot/StatusMessage": "Ready",
                "CNC/MachineReady": True,
                "CNC/CycleRunning": False,
                "CNC/CycleComplete": False,
                "CNC/AlarmActive": False,
                "CNC/PartPresent": False,
                "CNC/SelectedProgram": "O1200",
                "CNC/LoadedProgram": "O1200",
                "CNC/ProgramSource": "cnc_existing",
                "CNC/ProgramTransferState": "Idle",
                "CNC/StatusMessage": "Ready",
            }

            for path, value in node_defaults.items():
                folder_name = path.split("/")[0]
                self._add_var(folders[folder_name], namespace_index, path, value)

            self.server.start()
            self.service.set_opcua_status(
                enabled=True,
                running=True,
                endpoint=self.endpoint,
                namespace=self.namespace_uri,
                last_error="",
                node_count=len(self.variables),
            )

            while not self.stop_event.is_set():
                self._poll_writes()
                self._push_state()
                time.sleep(0.35)
        except Exception as exc:  # pragma: no cover - runtime integration path
            self.service.set_opcua_status(enabled=Server is not None, running=False, last_error=str(exc))
        finally:
            if self.server is not None:
                try:
                    self.server.stop()
                except Exception:
                    pass
            self.service.set_opcua_status(running=False)

    def _poll_writes(self) -> None:
        for path, var in list(self.variables.items()):
            try:
                current = var.get_value()
            except Exception:
                continue
            if current == self.last_values.get(path):
                continue
            self.last_values[path] = current
            self._handle_write(path, current)

    def _handle_write(self, path: str, value: Any) -> None:
        if path == "Cell/Command":
            command = str(value or "").strip()
            if command:
                self.service.apply_sim_command(command, source="opcua")
                self._set_var(path, "")
            return
        if path == "Cell/Message":
            message = str(value or "").strip()
            if message:
                self.service.apply_sim_command(message, source="opcua")
            return
        if path == "Cell/Mode":
            self.service.update_machine_signals("opcua", {"safety": {"Mode": value}})
            return

        if "/" not in path:
            return
        group, key = path.split("/", 1)
        group_map = {"LeanLift": "leanlift", "Robot": "robot", "CNC": "cnc", "Safety": "safety"}
        target_group = group_map.get(group)
        if not target_group:
            return
        self.service.update_machine_signals("opcua", {target_group: {key: value}})

    def _format_target(self, target: Dict[str, Any] | None) -> str:
        if not target:
            return ""
        return f"shelf={target.get('shelf')} slot={target.get('slot_no')} x={target.get('x_mm')} y={target.get('y_mm')} z={target.get('z_mm')}"

    def _push_state(self) -> None:
        state = self.service.get_state()
        latest_event = state["history"][0]["message"] if state["history"] else ""
        values = {
            "Cell/Heartbeat": int(time.time()),
            "Cell/Mode": state["safety"]["mode_key"],
            "Cell/ActiveJob": state["production_order"].get("job_id", ""),
            "Cell/LastEvent": latest_event,
            "Safety/SafetyOk": state["safety"]["safety_ok"],
            "Safety/EmergencyStopActive": state["safety"]["emergency_stop_active"],
            "Safety/GatesClosed": state["safety"]["gates_closed"],
            "Safety/ScannerClear": state["safety"]["scanner_clear"],
            "Safety/LastTrip": state["safety"]["last_trip"],
            "LeanLift/CurrentShelf": int(state["lift"]["current_shelf"]),
            "LeanLift/AccessPoint": int(state["lift"]["access_point"]),
            "LeanLift/RobotShelf": state["lift"]["robot_shelf"],
            "LeanLift/OperatorShelf": state["lift"]["operator_shelf"],
            "LeanLift/TrayPresent": state["lift"]["tray_present"],
            "LeanLift/TrayExtended": state["lift"]["tray_extended"],
            "LeanLift/DoorClosed": state["lift"]["door_closed"],
            "LeanLift/AlarmActive": state["lift"]["alarm_active"],
            "LeanLift/StatusMessage": state["lift"]["status_message"],
            "Robot/Ready": state["robot"]["ready"],
            "Robot/Busy": state["robot"]["busy"],
            "Robot/Fault": state["robot"]["fault"],
            "Robot/AtHome": state["robot"]["at_home"],
            "Robot/PartInGripper": state["robot"]["part_in_gripper"],
            "Robot/StationComplete": state["robot"]["station_complete"],
            "Robot/ActiveTask": state["robot"]["active_task"],
            "Robot/NextPick": self._format_target(state["robot"].get("next_pick")),
            "Robot/PlaceTarget": self._format_target(state["robot"].get("place_target")),
            "Robot/StatusMessage": state["robot"]["status_message"],
            "CNC/MachineReady": state["cnc"]["machine_ready"],
            "CNC/CycleRunning": state["cnc"]["cycle_running"],
            "CNC/CycleComplete": state["cnc"]["cycle_complete"],
            "CNC/AlarmActive": state["cnc"]["alarm_active"],
            "CNC/PartPresent": state["cnc"]["part_present"],
            "CNC/SelectedProgram": state["cnc"]["selected_program"],
            "CNC/LoadedProgram": state["cnc"]["loaded_program"],
            "CNC/ProgramSource": state["cnc"]["program_source"],
            "CNC/ProgramTransferState": state["cnc"]["program_transfer_state"],
            "CNC/StatusMessage": state["cnc"]["status_message"],
        }
        for path, value in values.items():
            self._set_var(path, value)

    def _set_var(self, path: str, value: Any) -> None:
        var = self.variables.get(path)
        if var is None:
            return
        try:
            var.set_value(value)
            self.last_values[path] = value
        except Exception:
            pass
