from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
import json
import math
import re
from typing import Any, Dict, List
from werkzeug.security import check_password_hash, generate_password_hash


@dataclass
class Product:
    id: str
    name: str
    material: str
    diameter_mm: float
    cut_length_mm: float
    required_cnc_program: str
    allowed_cnc_programs: List[str]


class ProductionCellService:
    """In-memory development model for the integrated manufacturing cell."""

    ROLE_ORDER = {"operator": 1, "innstiller": 2, "service": 3, "administrator": 4}

    def __init__(self) -> None:
        self.lock = RLock()
        self.base_dir = Path(__file__).resolve().parent
        self.upload_dir = self.base_dir / "uploads" / "nc_programs"
        self.inventory_sequence = 0
        self.job_sequence = 0

        self.products: List[Product] = [
            Product("P1001", "Aksel O120", "42CrMo4", 120, 95, "O1200", ["O1200", "O1201"]),
            Product("P1002", "Flens O280", "S355", 280, 140, "O2801", ["O2801"]),
            Product("P1003", "Hylse O80", "Al 6082", 80, 55, "O0802", ["O0802", "O0803"]),
        ]
        self.part_types: List[Dict[str, Any]] = [
            {"part_type_id": "PT-RAW-120", "name": "Raemne O120", "diameter_mm": 120, "length_mm": 95, "height_mm": 95, "product_id": "P1001", "quantity_total": 60},
            {"part_type_id": "PT-RAW-280", "name": "Raemne O280", "diameter_mm": 280, "length_mm": 140, "height_mm": 140, "product_id": "P1002", "quantity_total": 22},
            {"part_type_id": "PT-INP-080", "name": "Emne O80", "diameter_mm": 80, "length_mm": 55, "height_mm": 55, "product_id": "P1003", "quantity_total": 45},
        ]

        self.settings = {
            "shelf_width_mm": 2000,
            "shelf_depth_mm": 800,
            "shelf_height_mm": 120,
            "part_clearance_mm": 20,
            "wall_clearance_mm": 50,
            "status_colors": {
                "empty": "#d8dee9",
                "raw": "#2f80ed",
                "reserved": "#7c3aed",
                "wip": "#f59e0b",
                "in_process": "#f59e0b",
                "finished": "#10b981",
                "quarantine": "#ef4444",
                "blocked": "#64748b",
            },
        }

        self.shelves = [str(i) for i in range(1, 51)]
        self.active_shelf = "1"
        self.shelf_slots: Dict[str, List[Dict[str, Any]]] = {s: self._generate_slots(4, 3) for s in self.shelves}
        self._seed_demo_inventory()

        self.safety_status = {
            "safety_ok": True,
            "emergency_stop_active": False,
            "gates_closed": True,
            "scanner_clear": True,
            "mode_key": "Automatic",
            "last_trip": "None",
        }

        self.robot_status = {
            "vendor": "Gudel CP-4 / ABB IRC5",
            "connection": "Simulated OPC UA",
            "mode": "Auto",
            "ready": True,
            "busy": False,
            "fault": False,
            "at_home": True,
            "part_in_gripper": False,
            "station_complete": False,
            "active_task": "Idle",
            "next_pick": None,
            "place_target": None,
            "status_message": "Ready",
            "alarms": [],
        }

        self.cnc_status = {
            "vendor": "Fanuc / CMZ TD55",
            "connection": "Simulated FOCAS + OPC UA",
            "machine_ready": True,
            "cycle_running": False,
            "cycle_complete": False,
            "alarm_active": False,
            "part_present": False,
            "machine_state": "Ready",
            "selected_program": "O1200",
            "program_valid": True,
            "loaded_program": "O1200",
            "program_source": "cnc_existing",
            "program_transfer_state": "Idle",
            "spindle_rpm": 0,
            "feed_rate": 0,
            "alarm": "None",
            "part_counter": 0,
            "status_message": "Ready",
        }

        self.lift_status = {
            "connection": "Simulated Host-Web + OPC UA",
            "mode": "Auto",
            "current_shelf": "1",
            "access_point": 2,
            "robot_access_point": 2,
            "operator_access_point": 1,
            "robot_shelf": "1",
            "operator_shelf": "1",
            "last_actor": "system",
            "tray_present": True,
            "tray_extended": False,
            "door_closed": True,
            "alarm_active": False,
            "status_message": "Ready",
            "last_response": "No command sent",
        }

        self.production_order = {
            "active": False,
            "job_id": "",
            "job_name": "",
            "part_type_id": "",
            "product_id": "",
            "target_qty": 0,
            "processed_qty": 0,
            "mode": "quantity",
            "selected_program": self.cnc_status["selected_program"],
            "program_source": self.cnc_status["program_source"],
            "next_pick": None,
            "started_at": "",
            "last_cycle_started_at": "",
            "cycle_time_sec_estimate": 0,
            "avg_cycle_time_sec": 0,
            "state": "Idle",
        }
        self.simulation = {"running": False, "tick": 0, "active_shelf": self.active_shelf, "last_event": "Not started"}

        self.cnc_existing_programs: List[Dict[str, Any]] = [
            {"program_name": "O1200", "description": "Aksel O120 - existing CNC program"},
            {"program_name": "O1201", "description": "Aksel O120 - revision B"},
            {"program_name": "O2801", "description": "Flens O280"},
            {"program_name": "O0802", "description": "Hylse O80"},
            {"program_name": "O0803", "description": "Hylse O80 - revision B"},
        ]
        self.jobs: List[Dict[str, Any]] = []
        self.users: Dict[str, Dict[str, Any]] = {
            "operator": {"username": "operator", "password_hash": generate_password_hash("operator123"), "role": "operator", "active": True},
            "innstiller": {"username": "innstiller", "password_hash": generate_password_hash("innstiller123"), "role": "innstiller", "active": True},
            "service": {"username": "service", "password_hash": generate_password_hash("service123"), "role": "service", "active": True},
            "admin": {"username": "admin", "password_hash": generate_password_hash("admin123"), "role": "administrator", "active": True},
        }

        self.available_focas_functions, self.focas_function_params = self._load_focas_reference()
        self.available_leanlift_rest_commands, self.leanlift_command_params = self._load_hostweb_reference()

        self.opcua_status = {
            "enabled": False,
            "running": False,
            "endpoint": "opc.tcp://0.0.0.0:4840/production-cell/sim/",
            "namespace": "urn:bergsli:production-cell:simulation",
            "last_error": "",
            "node_count": 0,
        }

        self.history: List[Dict[str, Any]] = []
        self.diagnostics: List[Dict[str, Any]] = []
        self._log("system", "Development simulator ready")

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _parse_ts(self, value: str) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _estimate_cycle_time_sec(self, part_type: Dict[str, Any]) -> int:
        return int(120 + float(part_type.get("diameter_mm", 0)) * 0.8 + float(part_type.get("length_mm", 0)) * 0.45)

    def _cycle_time_for_order(self) -> int:
        return int(self.production_order.get("avg_cycle_time_sec") or self.production_order.get("cycle_time_sec_estimate") or 180)

    def _log(self, category: str, message: str) -> None:
        self.history.insert(0, {"ts": self._now(), "category": category, "message": message})
        self.history = self.history[:500]

    def _diag(self, channel: str, direction: str, payload: Dict[str, Any]) -> None:
        self.diagnostics.insert(0, {"ts": self._now(), "channel": channel, "direction": direction, "raw": payload})
        self.diagnostics = self.diagnostics[:600]

    def _load_focas_reference(self) -> tuple[list[str], dict[str, list[str]]]:
        json_path = self.base_dir / "focas" / "focas_reference.json"
        if json_path.exists():
            data = json.loads(json_path.read_text(encoding="utf-8"))
            return data.get("functions", []), data.get("params", {})

        fallback = ["cnc_statinfo", "cnc_rdparam", "cnc_wrparam", "cnc_rdmacro", "cnc_wrmacro", "cnc_rdalmmsg2"]
        return fallback, {fn: [] for fn in fallback}

    def _load_hostweb_reference(self) -> tuple[list[str], dict[str, list[str]]]:
        json_path = self.base_dir / "doc" / "hostweb_reference.json"
        if json_path.exists():
            data = json.loads(json_path.read_text(encoding="utf-8"))
            return data.get("operations", []), data.get("params", {})

        fallback = ["get_shelf", "store_shelf", "read_status"]
        return fallback, {cmd: [] for cmd in fallback}

    def _generate_slots(
        self,
        cols: int,
        rows: int,
        z_mm: float | None = None,
        part_diameter_mm: float | None = None,
        part_clearance_mm: float | None = None,
        wall_clearance_mm: float | None = None,
    ) -> List[Dict[str, Any]]:
        slots: List[Dict[str, Any]] = []
        slot_no = 1
        if part_diameter_mm is not None:
            diameter = float(part_diameter_mm)
            clearance = float(self.settings["part_clearance_mm"] if part_clearance_mm is None else part_clearance_mm)
            wall_clearance = float(self.settings["wall_clearance_mm"] if wall_clearance_mm is None else wall_clearance_mm)
            if diameter <= 0 or clearance < 0 or wall_clearance < 0:
                raise ValueError("Part diameter and clearances must be valid positive values")
            required_width = 2 * wall_clearance + cols * diameter + (cols - 1) * clearance
            required_depth = 2 * wall_clearance + rows * diameter + (rows - 1) * clearance
            if required_width > self.settings["shelf_width_mm"] or required_depth > self.settings["shelf_depth_mm"]:
                raise ValueError(
                    "Layout does not fit on shelf with selected part size and clearances "
                    f"({required_width:.1f} x {required_depth:.1f} mm required)"
                )
            x_spacing = diameter + clearance
            y_spacing = diameter + clearance
            x_start = wall_clearance + diameter / 2
            y_start = wall_clearance + diameter / 2
        else:
            x_spacing = self.settings["shelf_width_mm"] / (cols + 1)
            y_spacing = self.settings["shelf_depth_mm"] / (rows + 1)
            x_start = x_spacing
            y_start = y_spacing
        for row in range(rows):
            for col in range(cols):
                slots.append(
                    {
                        "slot_no": slot_no,
                        "x_mm": round(x_start + col * x_spacing, 2),
                        "y_mm": round(y_start + row * y_spacing, 2),
                        "z_mm": float(z_mm if z_mm is not None else self.settings["shelf_height_mm"]),
                        "occupied": False,
                        "status": "empty",
                        "part_type_id": "",
                        "part_no": None,
                        "fifo_seq": None,
                        "loaded_at": None,
                    }
                )
                slot_no += 1
        return slots

    def _seed_demo_inventory(self) -> None:
        seed = [("1", "PT-RAW-120"), ("2", "PT-RAW-280"), ("3", "PT-INP-080")]
        for shelf, part_type_id in seed:
            for index, slot in enumerate(self.shelf_slots[shelf], start=1):
                self._mark_slot_loaded(slot, part_type_id, index, "raw")

    def _mark_slot_loaded(self, slot: Dict[str, Any], part_type_id: str, part_no: int | None, status: str = "raw") -> None:
        self.inventory_sequence += 1
        slot.update(
            {
                "occupied": True,
                "status": self._status_alias(status),
                "part_type_id": part_type_id,
                "part_no": part_no,
                "fifo_seq": self.inventory_sequence,
                "loaded_at": self._now(),
            }
        )

    def _get_part_type(self, part_type_id: str) -> Dict[str, Any]:
        pt = next((p for p in self.part_types if p["part_type_id"] == part_type_id), None)
        if not pt:
            raise ValueError(f"Unknown part_type_id: {part_type_id}")
        return pt

    def _get_product(self, product_id: str) -> Product:
        product = next((p for p in self.products if p.id == product_id), None)
        if not product:
            raise ValueError(f"Unknown product_id: {product_id}")
        return product

    def _product_for_part_type(self, part_type_id: str) -> Product:
        part_type = self._get_part_type(part_type_id)
        return self._get_product(part_type.get("product_id", ""))

    def _status_alias(self, status: str) -> str:
        return "wip" if status == "in_process" else status

    def _part_lookup(self) -> Dict[str, Dict[str, Any]]:
        return {p["part_type_id"]: p for p in self.part_types}

    def _enrich_slot(self, slot: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(slot)
        part_type = self._part_lookup().get(slot.get("part_type_id", ""))
        if part_type:
            out.update(
                {
                    "part_name": part_type.get("name", ""),
                    "product_id": part_type.get("product_id", ""),
                    "diameter_mm": part_type.get("diameter_mm", 0),
                    "length_mm": part_type.get("length_mm", 0),
                    "height_mm": part_type.get("height_mm", slot.get("z_mm", 0)),
                }
            )
        return out

    def _inventory_slots(self, part_type_id: str, statuses: set[str]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for shelf in self.shelves:
            for slot in self.shelf_slots[shelf]:
                if slot["occupied"] and slot["part_type_id"] == part_type_id and self._status_alias(slot["status"]) in statuses:
                    out.append(slot)
        return sorted(out, key=lambda slot: (slot.get("fifo_seq") or 10**12, slot.get("slot_no") or 0))

    def _inventory_candidates(self, part_type_id: str, statuses: set[str]) -> List[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        for shelf in self.shelves:
            for slot in self.shelf_slots[shelf]:
                if slot["occupied"] and slot["part_type_id"] == part_type_id and self._status_alias(slot["status"]) in statuses:
                    candidates.append({"shelf": shelf, "slot": slot})
        return sorted(candidates, key=lambda item: (item["slot"].get("fifo_seq") or 10**12, int(item["shelf"]), item["slot"].get("slot_no") or 0))

    def _slot_target(self, shelf: str, slot: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "shelf": shelf,
            "slot_no": slot["slot_no"],
            "x_mm": slot["x_mm"],
            "y_mm": slot["y_mm"],
            "z_mm": slot["z_mm"],
            "part_type_id": slot.get("part_type_id", ""),
            "part_no": slot.get("part_no"),
            "fifo_seq": slot.get("fifo_seq"),
        }

    def _validate_slot_clearance(
        self,
        slots: List[Dict[str, Any]],
        part_diameter_mm: float,
        part_clearance_mm: float,
        wall_clearance_mm: float,
    ) -> None:
        diameter = float(part_diameter_mm)
        clearance = float(part_clearance_mm)
        wall_clearance = float(wall_clearance_mm)
        if diameter <= 0 or clearance < 0 or wall_clearance < 0:
            raise ValueError("Part diameter and clearances must be valid positive values")
        radius = diameter / 2
        width = float(self.settings["shelf_width_mm"])
        depth = float(self.settings["shelf_depth_mm"])
        for slot in slots:
            x = float(slot["x_mm"])
            y = float(slot["y_mm"])
            if x - radius < wall_clearance or x + radius > width - wall_clearance:
                raise ValueError(f"Slot {slot['slot_no']} violates wall clearance in X direction")
            if y - radius < wall_clearance or y + radius > depth - wall_clearance:
                raise ValueError(f"Slot {slot['slot_no']} violates wall clearance in Y direction")

        minimum_distance = diameter + clearance
        for index, first in enumerate(slots):
            for second in slots[index + 1 :]:
                distance = math.hypot(float(first["x_mm"]) - float(second["x_mm"]), float(first["y_mm"]) - float(second["y_mm"]))
                if distance + 0.001 < minimum_distance:
                    raise ValueError(f"Slot {first['slot_no']} overlaps slot {second['slot_no']}")

    def _apply_lift_position(self, shelf: str, access_point: int, actor: str = "system") -> None:
        self.lift_status["current_shelf"] = shelf
        self.lift_status["access_point"] = int(access_point)
        self.lift_status["last_actor"] = actor
        if int(access_point) == int(self.lift_status["robot_access_point"]):
            self.lift_status["robot_shelf"] = shelf
        if int(access_point) == int(self.lift_status["operator_access_point"]):
            self.lift_status["operator_shelf"] = shelf
        self.active_shelf = shelf

    def request_shelf(self, shelf: str, access_point: int = 1, actor: str = "operator", override: bool = False) -> Dict[str, Any]:
        with self.lock:
            shelf = str(shelf)
            access_point = int(access_point)
            if shelf not in self.shelves:
                raise ValueError("Unknown shelf")
            if access_point not in {int(self.lift_status["operator_access_point"]), int(self.lift_status["robot_access_point"])}:
                raise ValueError("Unknown lift access point")
            if access_point == int(self.lift_status["robot_access_point"]) and actor != "robot" and not override:
                raise ValueError("Robot access point requires robot request or service override")
            command = self.call_lift_rest(
                "get_shelf",
                {"pm01_shelfNumber": shelf, "pm01_accessPoint": access_point, "actor": actor, "override": override},
            )
            self._log("lift", f"{actor} requested shelf {shelf} to access point {access_point}")
            return command

    def _set_robot_target(self, target: Dict[str, Any] | None) -> None:
        self.robot_status["next_pick"] = target
        self.production_order["next_pick"] = target
        if target:
            self.robot_status["place_target"] = target
            self.robot_status["active_task"] = f"Next pick shelf {target['shelf']} slot {target['slot_no']}"
        else:
            self.robot_status["active_task"] = "Idle"

    def _prepare_next_pick(self) -> Dict[str, Any] | None:
        part_type_id = self.production_order.get("part_type_id", "")
        if not part_type_id:
            self._set_robot_target(None)
            return None
        candidates = self._inventory_candidates(part_type_id, {"reserved", "raw"})
        if not candidates:
            self._set_robot_target(None)
            return None
        selected = candidates[0]
        target = self._slot_target(selected["shelf"], selected["slot"])
        self._apply_lift_position(selected["shelf"], int(self.lift_status["robot_access_point"]), actor="robot")
        self.lift_status["tray_present"] = True
        self._set_robot_target(target)
        return target

    def _inventory_summary(self) -> Dict[str, Dict[str, int]]:
        summary: Dict[str, Dict[str, int]] = {}
        for shelf in self.shelves:
            for slot in self.shelf_slots[shelf]:
                part_type_id = slot.get("part_type_id") or "empty"
                status = self._status_alias(slot.get("status", "empty"))
                summary.setdefault(part_type_id, {})
                summary[part_type_id][status] = summary[part_type_id].get(status, 0) + 1
        return summary

    def _dashboard_metrics(self) -> Dict[str, Any]:
        order = dict(self.production_order)
        part_type_id = order.get("part_type_id", "")
        cycle_sec = self._cycle_time_for_order()
        remaining_qty = max(int(order.get("target_qty") or 0) - int(order.get("processed_qty") or 0), 0)
        available_qty = len(self._inventory_candidates(part_type_id, {"raw", "reserved", "wip"})) if part_type_id else 0
        started = self._parse_ts(order.get("started_at", ""))
        elapsed_sec = int((datetime.now(timezone.utc) - started).total_seconds()) if started else 0
        return {
            "cell_state": "Produksjon" if order.get("active") else order.get("state", "Idle"),
            "active_job": order.get("job_name") or order.get("job_id") or "Ingen aktiv jobb",
            "job_id": order.get("job_id", ""),
            "part_type_id": part_type_id,
            "target_qty": order.get("target_qty", 0),
            "processed_qty": order.get("processed_qty", 0),
            "remaining_qty": remaining_qty,
            "cycle_time_sec": cycle_sec,
            "cycle_time_min": round(cycle_sec / 60, 1),
            "remaining_hours": round((remaining_qty * cycle_sec) / 3600, 2),
            "hours_until_refill": round((available_qty * cycle_sec) / 3600, 2) if part_type_id else 0,
            "available_parts_for_job": available_qty,
            "elapsed_hours": round(elapsed_sec / 3600, 2),
        }

    def get_shelf_layout(self, shelf: str) -> Dict[str, Any]:
        with self.lock:
            if shelf not in self.shelves:
                raise ValueError("Unknown shelf")
            return {
                "shelf": shelf,
                "shelf_width_mm": self.settings["shelf_width_mm"],
                "shelf_depth_mm": self.settings["shelf_depth_mm"],
                "shelf_height_mm": self.settings["shelf_height_mm"],
                "part_clearance_mm": self.settings["part_clearance_mm"],
                "wall_clearance_mm": self.settings["wall_clearance_mm"],
                "status_colors": self.settings["status_colors"],
                "slots": [self._enrich_slot(slot) for slot in self.shelf_slots[shelf]],
            }

    def get_stats(self) -> Dict[str, Any]:
        all_slots = [slot for shelf in self.shelves for slot in self.shelf_slots[shelf]]
        return {
            "total_shelves": len(self.shelves),
            "total_slots": len(all_slots),
            "occupied_slots": sum(1 for slot in all_slots if slot["occupied"]),
            "raw_slots": sum(1 for slot in all_slots if self._status_alias(slot["status"]) == "raw"),
            "reserved_slots": sum(1 for slot in all_slots if self._status_alias(slot["status"]) == "reserved"),
            "wip_slots": sum(1 for slot in all_slots if self._status_alias(slot["status"]) == "wip"),
            "finished_slots": sum(1 for slot in all_slots if self._status_alias(slot["status"]) == "finished"),
            "quarantine_slots": sum(1 for slot in all_slots if self._status_alias(slot["status"]) == "quarantine"),
            "simulation_ticks": self.simulation.get("tick", 0) if hasattr(self, "simulation") else 0,
            "cnc_part_counter": self.cnc_status["part_counter"],
        }

    def get_state(self) -> Dict[str, Any]:
        with self.lock:
            if not hasattr(self, "simulation"):
                self.simulation = {"running": False, "tick": 0, "active_shelf": self.active_shelf, "last_event": "Not started"}
            return {
                "products": [asdict(product) for product in self.products],
                "part_types": self.part_types,
                "settings": self.settings,
                "shelves": self.shelves,
                "active_shelf": self.active_shelf,
                "robot": self.robot_status,
                "cnc": self.cnc_status,
                "lift": self.lift_status,
                "safety": self.safety_status,
                "opcua": self.opcua_status,
                "simulation": self.simulation,
                "production_order": self.production_order,
                "dashboard": self._dashboard_metrics(),
                "jobs": self.jobs,
                "cnc_existing_programs": self.cnc_existing_programs,
                "stats": self.get_stats(),
                "inventory": self._inventory_summary(),
                "history": self.history[:150],
                "available_focas_functions": self.available_focas_functions,
                "focas_function_params": self.focas_function_params,
                "available_leanlift_rest_commands": self.available_leanlift_rest_commands,
                "leanlift_command_params": self.leanlift_command_params,
            }

    def update_settings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            for key in ("shelf_width_mm", "shelf_depth_mm", "shelf_height_mm", "part_clearance_mm", "wall_clearance_mm"):
                if key in payload:
                    value = float(payload[key])
                    if key in {"part_clearance_mm", "wall_clearance_mm"}:
                        if value < 0:
                            raise ValueError(f"{key} must be zero or greater")
                    elif value <= 0:
                        raise ValueError(f"{key} must be greater than zero")
                    self.settings[key] = value
            if "status_colors" in payload and isinstance(payload["status_colors"], dict):
                self.settings["status_colors"].update(payload["status_colors"])
            self._log("settings", "Updated shelf/status settings")
            return self.settings

    def configure_shelf_layout_graphic(
        self,
        shelf: str,
        part_type_id: str,
        cols: int,
        rows: int,
        z_mm: float,
        part_clearance_mm: float | None = None,
        wall_clearance_mm: float | None = None,
    ) -> Dict[str, Any]:
        with self.lock:
            if shelf not in self.shelves:
                raise ValueError("Unknown shelf")
            if cols <= 0 or rows <= 0 or cols * rows > 120:
                raise ValueError("Layout must contain 1-120 locations")
            part_type = self._get_part_type(part_type_id)
            clearance = float(self.settings["part_clearance_mm"] if part_clearance_mm is None else part_clearance_mm)
            wall_clearance = float(self.settings["wall_clearance_mm"] if wall_clearance_mm is None else wall_clearance_mm)
            slots = self._generate_slots(cols, rows, z_mm, float(part_type["diameter_mm"]), clearance, wall_clearance)
            self._validate_slot_clearance(slots, float(part_type["diameter_mm"]), clearance, wall_clearance)
            for index, slot in enumerate(slots, start=1):
                self._mark_slot_loaded(slot, part_type_id, index, "raw")
            self.shelf_slots[shelf] = slots
            self.settings["part_clearance_mm"] = clearance
            self.settings["wall_clearance_mm"] = wall_clearance
            self._log("shelf", f"Configured shelf {shelf} with {len(slots)} production locations and clearance validation")
            return self.get_shelf_layout(shelf)

    def export_shelf_layout_rows(self, shelf: str) -> List[Dict[str, Any]]:
        with self.lock:
            if shelf not in self.shelves:
                raise ValueError("Unknown shelf")
            return [
                {
                    "slot_no": int(slot["slot_no"]),
                    "x_mm": float(slot["x_mm"]),
                    "y_mm": float(slot["y_mm"]),
                    "z_mm": float(slot["z_mm"]),
                    "part_no": slot.get("part_no") or "",
                }
                for slot in self.shelf_slots[shelf]
            ]

    def import_shelf_layout_rows(
        self,
        shelf: str,
        part_type_id: str,
        rows: List[Dict[str, Any]],
        part_clearance_mm: float | None = None,
        wall_clearance_mm: float | None = None,
    ) -> Dict[str, Any]:
        with self.lock:
            if shelf not in self.shelves:
                raise ValueError("Unknown shelf")
            part_type = self._get_part_type(part_type_id)
            if not rows or len(rows) > 120:
                raise ValueError("Imported layout must contain 1-120 locations")
            clearance = float(self.settings["part_clearance_mm"] if part_clearance_mm is None else part_clearance_mm)
            wall_clearance = float(self.settings["wall_clearance_mm"] if wall_clearance_mm is None else wall_clearance_mm)
            slots: List[Dict[str, Any]] = []
            seen: set[int] = set()
            part_numbers_by_slot: Dict[int, int | None] = {}
            for index, row in enumerate(rows, start=1):
                slot_no = int(row.get("slot_no") or index)
                if slot_no in seen:
                    raise ValueError(f"Duplicate slot number {slot_no}")
                seen.add(slot_no)
                x_mm = float(row["x_mm"])
                y_mm = float(row["y_mm"])
                z_value = row.get("z_mm", self.settings["shelf_height_mm"])
                z_mm = float(self.settings["shelf_height_mm"] if z_value in {"", None} else z_value)
                if x_mm <= 0 or y_mm <= 0 or z_mm <= 0:
                    raise ValueError(f"Slot {slot_no} contains invalid coordinates")
                slots.append(
                    {
                        "slot_no": slot_no,
                        "x_mm": round(x_mm, 2),
                        "y_mm": round(y_mm, 2),
                        "z_mm": round(z_mm, 2),
                        "occupied": False,
                        "status": "empty",
                        "part_type_id": "",
                        "part_no": None,
                        "fifo_seq": None,
                        "loaded_at": None,
                    }
                )
                raw_part_no = row.get("part_no")
                part_text = str(raw_part_no).strip() if raw_part_no is not None else ""
                part_numbers_by_slot[slot_no] = int(float(part_text)) if part_text else None

            self._validate_slot_clearance(slots, float(part_type["diameter_mm"]), clearance, wall_clearance)
            for slot in slots:
                part_no = part_numbers_by_slot.get(slot["slot_no"]) or slot["slot_no"]
                self._mark_slot_loaded(slot, part_type_id, part_no, "raw")
            self.shelf_slots[shelf] = sorted(slots, key=lambda item: item["slot_no"])
            self.settings["part_clearance_mm"] = clearance
            self.settings["wall_clearance_mm"] = wall_clearance
            self._log("shelf", f"Imported layout for shelf {shelf} with {len(slots)} locations")
            return self.get_shelf_layout(shelf)

    def update_slot(self, shelf: str, slot_no: int, occupied: bool, status: str, part_type_id: str | None) -> Dict[str, Any]:
        with self.lock:
            slots = self.shelf_slots.get(shelf)
            if not slots:
                raise ValueError("Unknown shelf")
            slot = next((s for s in slots if s["slot_no"] == slot_no), None)
            if not slot:
                raise ValueError("Unknown slot")
            normalized_status = self._status_alias(status)
            if occupied and part_type_id:
                self._get_part_type(part_type_id)
            if occupied and not part_type_id:
                raise ValueError("part_type_id is required when loading a slot")
            if occupied:
                if not slot.get("occupied") or slot.get("part_type_id") != part_type_id:
                    self._mark_slot_loaded(slot, part_type_id or "", slot_no, normalized_status)
                else:
                    slot["status"] = normalized_status
            else:
                slot.update({"occupied": False, "status": "empty", "part_type_id": "", "part_no": None, "fifo_seq": None, "loaded_at": None})
            self._log("inventory", f"Manual {'load' if occupied else 'unload'} on shelf {shelf}, slot {slot_no}")
            return self._enrich_slot(slot)

    def upsert_part_type(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            part_type_id = payload.get("part_type_id", "").strip()
            if not part_type_id:
                raise ValueError("part_type_id is required")
            record = {
                "part_type_id": part_type_id,
                "name": payload.get("name", "Unnamed"),
                "diameter_mm": float(payload.get("diameter_mm", 0)),
                "length_mm": float(payload.get("length_mm", 0)),
                "height_mm": float(payload.get("height_mm", 0)),
                "product_id": payload.get("product_id", ""),
                "quantity_total": int(payload.get("quantity_total", 0)),
            }
            if record["diameter_mm"] <= 0 or record["length_mm"] <= 0 or record["height_mm"] <= 0:
                raise ValueError("Diameter/length/height must be greater than zero")
            if record["product_id"]:
                self._get_product(record["product_id"])
            existing = next((p for p in self.part_types if p["part_type_id"] == part_type_id), None)
            if existing:
                existing.update(record)
            else:
                self.part_types.append(record)
            self._log("parts", f"Saved part type {part_type_id}")
            return record

    def list_users(self) -> List[Dict[str, Any]]:
        with self.lock:
            return [{"username": user["username"], "role": user["role"], "active": user["active"]} for user in sorted(self.users.values(), key=lambda item: item["username"])]

    def authenticate_user(self, username: str, password: str) -> Dict[str, Any] | None:
        with self.lock:
            user = self.users.get((username or "").strip().lower())
            if not user or not user.get("active"):
                return None
            if not check_password_hash(user["password_hash"], password or ""):
                return None
            return {"username": user["username"], "role": user["role"], "active": user["active"]}

    def upsert_user(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            username = (payload.get("username") or "").strip().lower()
            role = (payload.get("role") or "operator").strip().lower()
            password = payload.get("password") or ""
            if not username:
                raise ValueError("username is required")
            if role not in self.ROLE_ORDER:
                raise ValueError("Unknown role")
            existing = self.users.get(username)
            if not existing and not password:
                raise ValueError("password is required for new users")
            record = existing or {"username": username, "password_hash": "", "role": role, "active": True}
            record["role"] = role
            record["active"] = bool(payload.get("active", True))
            if password:
                record["password_hash"] = generate_password_hash(password)
            self.users[username] = record
            self._log("admin", f"Saved user {username} with role {role}")
            return {"username": record["username"], "role": record["role"], "active": record["active"]}

    def delete_user(self, username: str) -> Dict[str, Any]:
        with self.lock:
            key = (username or "").strip().lower()
            if key == "admin":
                raise ValueError("Default admin user cannot be deleted in development mode")
            if key not in self.users:
                raise ValueError("Unknown user")
            self.users.pop(key)
            self._log("admin", f"Deleted user {key}")
            return {"deleted": key}

    def _normalize_program_name(self, value: str) -> str:
        raw = (value or "").strip().upper()
        if not raw:
            raise ValueError("NC program name is required")
        if not re.match(r"^[A-Z0-9_.-]+$", raw):
            raise ValueError("NC program name can only contain letters, numbers, dot, underscore and dash")
        return raw

    def _get_job(self, job_id: str) -> Dict[str, Any]:
        job = next((item for item in self.jobs if item["job_id"] == job_id), None)
        if not job:
            raise ValueError(f"Unknown job_id: {job_id}")
        return job

    def _cnc_program_exists(self, program_name: str) -> bool:
        return any(item["program_name"] == program_name for item in self.cnc_existing_programs)

    def create_job(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            job_name = (payload.get("job_name") or "").strip()
            if not job_name:
                raise ValueError("job_name is required")
            part_type = self._get_part_type(payload.get("part_type_id", ""))
            product = self._get_product(part_type["product_id"])
            source_type = (payload.get("program_source_type") or "uploaded").strip().lower()
            if source_type not in {"uploaded", "server_path", "cnc_existing"}:
                raise ValueError("program_source_type must be uploaded, server_path or cnc_existing")

            program_name = self._normalize_program_name(payload.get("program_name") or product.required_cnc_program)
            source_path = (payload.get("source_path") or "").strip()
            original_filename = (payload.get("original_filename") or "").strip()
            display_name = original_filename or source_path or program_name

            if source_type == "cnc_existing" and not self._cnc_program_exists(program_name):
                raise ValueError(f"CNC program {program_name} is not registered as existing on the CNC")
            if source_type in {"uploaded", "server_path"} and not source_path:
                raise ValueError("source_path is required for uploaded/server_path programs")

            self.job_sequence += 1
            job = {
                "job_id": f"JOB-{self.job_sequence:04d}",
                "job_name": job_name,
                "part_type_id": part_type["part_type_id"],
                "part_name": part_type["name"],
                "product_id": product.id,
                "program_name": program_name,
                "program_source_type": source_type,
                "source_path": source_path,
                "original_filename": original_filename,
                "display_name": display_name,
                "fifo_enabled": bool(payload.get("fifo_enabled", True)),
                "created_at": self._now(),
                "status": "ready",
                "last_started_at": "",
            }
            self.jobs.append(job)
            self._log("jobs", f"Created job {job['job_id']} for {part_type['part_type_id']} using {program_name}")
            return job

    def register_uploaded_nc_program(self, filename: str, stored_path: str, program_name: str | None = None) -> Dict[str, Any]:
        with self.lock:
            normalized = self._normalize_program_name(program_name or Path(filename).stem)
            record = {
                "program_name": normalized,
                "program_source_type": "uploaded",
                "source_path": stored_path,
                "original_filename": filename,
                "display_name": filename,
                "registered_at": self._now(),
            }
            self._log("programs", f"Uploaded NC program {filename} as {normalized}")
            return record

    def _load_job_program_to_cnc(self, job: Dict[str, Any]) -> None:
        self.cnc_status["selected_program"] = job["program_name"]
        self.cnc_status["loaded_program"] = job["program_name"]
        self.cnc_status["program_source"] = job["program_source_type"]
        self.cnc_status["program_valid"] = True
        if job["program_source_type"] == "cnc_existing":
            self.cnc_status["program_transfer_state"] = "Using existing CNC program"
        else:
            self.cnc_status["program_transfer_state"] = f"Simulated transfer from {job['display_name']}"
        self._diag("cnc", "tx", {"action": "load_nc_program", "job_id": job["job_id"], "program": job["program_name"], "source": job["program_source_type"], "path": job["source_path"]})
        self._log("cnc", f"Loaded NC program {job['program_name']} for {job['job_id']}")

    def start_job(self, job_id: str, mode: str = "quantity", quantity: int | None = None) -> Dict[str, Any]:
        with self.lock:
            job = self._get_job(job_id)
            part_type = self._get_part_type(job["part_type_id"])
            if not self.safety_status["safety_ok"]:
                raise ValueError("Safety chain is not OK in simulation")
            candidates = self._inventory_candidates(job["part_type_id"], {"raw"})
            target = len(candidates) if mode == "all" else int(quantity or 0)
            if target <= 0:
                raise ValueError("Quantity must be greater than zero")
            if len(candidates) < target:
                raise ValueError(f"Not enough raw material. Requested {target}, available {len(candidates)}")

            self._load_job_program_to_cnc(job)
            ordered_candidates = candidates if job.get("fifo_enabled", True) else sorted(candidates, key=lambda item: (int(item["shelf"]), item["slot"].get("slot_no") or 0))
            selected_candidates = ordered_candidates[:target]
            for item in selected_candidates:
                item["slot"]["status"] = "reserved"

            first = selected_candidates[0]
            first_target = self._slot_target(first["shelf"], first["slot"])
            started_at = self._now()
            self.production_order = {
                "active": True,
                "job_id": job["job_id"],
                "job_name": job["job_name"],
                "part_type_id": part_type["part_type_id"],
                "product_id": job["product_id"],
                "target_qty": target,
                "processed_qty": 0,
                "mode": mode,
                "selected_program": job["program_name"],
                "program_source": job["program_source_type"],
                "next_pick": first_target,
                "started_at": started_at,
                "last_cycle_started_at": started_at,
                "cycle_time_sec_estimate": self._estimate_cycle_time_sec(part_type),
                "avg_cycle_time_sec": 0,
                "state": "Queued",
            }
            job["status"] = "running"
            job["last_started_at"] = self._now()
            self._prepare_next_pick()
            self.call_lift_rest("get_shelf", {"pm01_shelfNumber": first["shelf"], "pm01_accessPoint": self.lift_status["robot_access_point"], "actor": "robot"})
            self._log("production", f"Started job {job['job_id']} with FIFO shelf {first['shelf']} slot {first['slot']['slot_no']}")
            return self.production_order

    def set_shelf_status(self, shelf: str, status: str, include_empty: bool = False, part_type_id: str | None = None) -> Dict[str, Any]:
        with self.lock:
            if shelf not in self.shelves:
                raise ValueError("Unknown shelf")
            normalized_status = self._status_alias(status)
            part_type = self._get_part_type(part_type_id) if part_type_id else None
            if normalized_status != "empty" and include_empty and not part_type:
                empty_slots = [slot for slot in self.shelf_slots[shelf] if not slot["occupied"]]
                if empty_slots:
                    raise ValueError("part_type_id is required when filling empty shelf locations")
            changed = 0
            for slot in self.shelf_slots[shelf]:
                if not include_empty and not slot["occupied"]:
                    continue
                if normalized_status == "empty":
                    slot.update({"occupied": False, "status": "empty", "part_type_id": "", "part_no": None, "fifo_seq": None, "loaded_at": None})
                elif not slot["occupied"]:
                    self._mark_slot_loaded(slot, part_type["part_type_id"], slot["slot_no"], normalized_status)
                else:
                    if part_type:
                        slot["part_type_id"] = part_type["part_type_id"]
                    slot["status"] = normalized_status
                changed += 1
            self._log("inventory", f"Set {changed} locations on shelf {shelf} to {normalized_status}")
            return {"shelf": shelf, "status": normalized_status, "changed": changed}

    def select_cnc_program(self, product_id: str, program: str, operator: str = "development") -> Dict[str, Any]:
        with self.lock:
            product = self._get_product(product_id)
            selected = program.strip().upper()
            if selected not in product.allowed_cnc_programs:
                raise ValueError(f"Program {selected} is not whitelisted for {product_id}")
            self.cnc_status["selected_program"] = selected
            self.cnc_status["program_valid"] = selected == product.required_cnc_program or selected in product.allowed_cnc_programs
            self.production_order["selected_program"] = selected
            self._log("cnc", f"{operator} selected CNC program {selected} for {product_id}")
            self._diag("cnc", "tx", {"action": "select_program", "product_id": product_id, "program": selected, "operator": operator})
            return {"product_id": product_id, "program": selected, "program_valid": self.cnc_status["program_valid"]}

    def start_production(self, part_type_id: str, mode: str, quantity: int | None) -> Dict[str, Any]:
        with self.lock:
            part_type = self._get_part_type(part_type_id)
            product = self._get_product(part_type["product_id"])
            selected_program = self.cnc_status["selected_program"]
            if selected_program not in product.allowed_cnc_programs:
                raise ValueError(f"Selected CNC program {selected_program} is not whitelisted for {product.id}")
            raw_slots = self._inventory_slots(part_type_id, {"raw"})
            target = len(raw_slots) if mode == "all" else int(quantity or 0)
            if target <= 0:
                raise ValueError("Quantity must be greater than zero")
            if len(raw_slots) < target:
                raise ValueError(f"Not enough raw material. Requested {target}, available {len(raw_slots)}")
            if not self.safety_status["safety_ok"]:
                raise ValueError("Safety chain is not OK in simulation")
            for slot in raw_slots[:target]:
                slot["status"] = "reserved"
            started_at = self._now()
            self.production_order = {
                "active": True,
                "job_id": "",
                "job_name": "Ad-hoc production",
                "part_type_id": part_type_id,
                "product_id": product.id,
                "target_qty": target,
                "processed_qty": 0,
                "mode": mode,
                "selected_program": selected_program,
                "program_source": "manual_selection",
                "next_pick": None,
                "started_at": started_at,
                "last_cycle_started_at": started_at,
                "cycle_time_sec_estimate": self._estimate_cycle_time_sec(part_type),
                "avg_cycle_time_sec": 0,
                "state": "Queued",
            }
            self._prepare_next_pick()
            self._log("production", f"Started job {part_type_id}, qty={target}, program={selected_program}")
            return self.production_order

    def stop_production(self, reason: str = "Stopped from HMI") -> Dict[str, Any]:
        with self.lock:
            job_id = self.production_order.get("job_id")
            self.production_order["active"] = False
            self.production_order["state"] = "Stopped"
            self.robot_status["busy"] = False
            self.cnc_status["cycle_running"] = False
            self.cnc_status["spindle_rpm"] = 0
            self.cnc_status["feed_rate"] = 0
            if job_id:
                job = next((item for item in self.jobs if item["job_id"] == job_id), None)
                if job:
                    job["status"] = "stopped"
            self._log("production", reason)
            return self.production_order

    def complete_one_part(self) -> None:
        if not self.production_order["active"]:
            return
        wip_slot = None
        wip_shelf = ""
        for shelf in self.shelves:
            wip_slot = next(
                (
                    slot
                    for slot in self.shelf_slots[shelf]
                    if slot["part_type_id"] == self.production_order["part_type_id"] and self._status_alias(slot["status"]) in {"wip", "reserved"}
                ),
                None,
            )
            if wip_slot:
                wip_shelf = shelf
                break
        if wip_slot:
            wip_slot["status"] = "finished"
            finished_target = self._slot_target(wip_shelf, wip_slot)
            self.robot_status["place_target"] = finished_target
        now = datetime.now(timezone.utc)
        cycle_started = self._parse_ts(self.production_order.get("last_cycle_started_at", ""))
        if cycle_started:
            cycle_time = max(int((now - cycle_started).total_seconds()), 1)
            previous_avg = int(self.production_order.get("avg_cycle_time_sec") or 0)
            completed = int(self.production_order.get("processed_qty") or 0)
            self.production_order["avg_cycle_time_sec"] = cycle_time if previous_avg <= 0 else int(((previous_avg * completed) + cycle_time) / (completed + 1))
        self.production_order["last_cycle_started_at"] = self._now()
        self.production_order["processed_qty"] += 1
        self.cnc_status["part_counter"] += 1
        if self.production_order["processed_qty"] >= self.production_order["target_qty"]:
            self.production_order["active"] = False
            self.production_order["state"] = "Complete"
            if self.production_order.get("job_id"):
                job = next((item for item in self.jobs if item["job_id"] == self.production_order["job_id"]), None)
                if job:
                    job["status"] = "complete"
                    job["completed_at"] = self._now()
            self._set_robot_target(None)
            self._log("production", "Production job complete")
        else:
            self._prepare_next_pick()

    def call_cnc_focas(self, function_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            if function_name not in self.available_focas_functions:
                raise ValueError("FOCAS function is not available in the simulator reference")
            self._diag("cnc", "tx", {"function": function_name, "params": params})
            response = {"result": "ok", "function": function_name}
            if function_name in ["cnc_start", "cnc_cycle_start"]:
                self.update_machine_signals("focas", {"cnc": {"cycle_running": True, "cycle_complete": False}})
            elif function_name in ["cnc_stop", "cnc_reset"]:
                self.update_machine_signals("focas", {"cnc": {"cycle_running": False, "alarm_active": False}})
            elif function_name == "cnc_rdspmeter":
                response = {"spindle": self.cnc_status["spindle_rpm"]}
            elif function_name == "cnc_rdspeed":
                response = {"spindle_rpm": self.cnc_status["spindle_rpm"], "feed_rate": self.cnc_status["feed_rate"]}
            out = {"function": function_name, "params": params, "response": response}
            self._diag("cnc", "rx", out)
            self._log("cnc", f"FOCAS: {function_name}")
            return out

    def call_lift_rest(self, function_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            if function_name not in self.available_leanlift_rest_commands:
                raise ValueError("LeanLift Host-Web command is not available in the simulator reference")
            self._diag("lift", "tx", {"command": function_name, "params": params})
            if function_name in ["get_shelf", "getShelfV02", "add_shelf", "remove_shelf", "get_shelf_backgr"]:
                shelf = str(params.get("pm01_shelfNumber", params.get("shelf", self.lift_status["current_shelf"])))
                if shelf in self.shelves:
                    access_point = int(params.get("pm01_accessPoint", params.get("pm01_accessNumber", params.get("access_point", self.lift_status["access_point"]))) or self.lift_status["access_point"])
                    self._apply_lift_position(shelf, access_point, str(params.get("actor", "host-web")))
            if function_name == "shelf_transfer":
                self.lift_status["access_point"] = int(params.get("pm01_destinationAccessNumber", self.lift_status["access_point"]) or self.lift_status["access_point"])
            response = {
                "command": function_name,
                "accepted": True,
                "current_shelf": self.lift_status["current_shelf"],
                "access_point": self.lift_status["access_point"],
                "robot_shelf": self.lift_status["robot_shelf"],
                "operator_shelf": self.lift_status["operator_shelf"],
            }
            self.lift_status["last_response"] = str(response)
            out = {"function": function_name, "params": params, "response": response}
            self._diag("lift", "rx", out)
            self._log("lift", f"Host-Web: {function_name}")
            return out

    def simulation_start(self) -> Dict[str, Any]:
        with self.lock:
            self.simulation["running"] = True
            self.simulation["last_event"] = "Simulation started"
            self.robot_status["active_task"] = "Simulation running"
            self._log("simulation", "Start")
            return self.simulation

    def simulation_pause(self) -> Dict[str, Any]:
        with self.lock:
            self.simulation["running"] = False
            self.simulation["last_event"] = "Simulation paused"
            self.robot_status["busy"] = False
            self.robot_status["active_task"] = "Idle"
            self.cnc_status["cycle_running"] = False
            self.cnc_status["spindle_rpm"] = 0
            self.cnc_status["feed_rate"] = 0
            self._log("simulation", "Pause")
            return self.simulation

    def simulation_step(self) -> Dict[str, Any]:
        with self.lock:
            self.simulation["tick"] += 1
            shelf_index = (self.simulation["tick"] - 1) % len(self.shelves)
            shelf = self.shelves[shelf_index]
            self.active_shelf = shelf
            self.simulation["active_shelf"] = shelf
            self.lift_status["current_shelf"] = shelf

            if self.production_order["active"] and self.simulation["tick"] % 2 == 1:
                next_slot = next(
                    (
                        slot
                        for slot in self.shelf_slots[shelf]
                        if slot["part_type_id"] == self.production_order["part_type_id"] and self._status_alias(slot["status"]) in {"reserved", "raw"}
                    ),
                    None,
                )
                if next_slot:
                    next_slot["status"] = "wip"
                self.update_machine_signals(
                    "simulation",
                    {"robot": {"busy": True, "part_in_gripper": True, "active_task": f"Load CNC from shelf {shelf}"}, "cnc": {"cycle_running": True, "cycle_complete": False, "part_present": True}},
                )
                self.production_order["state"] = "Running"
                self.simulation["last_event"] = f"Started machining cycle from shelf {shelf}"
            elif self.production_order["active"]:
                self.update_machine_signals(
                    "simulation",
                    {"robot": {"busy": False, "part_in_gripper": False, "station_complete": True, "active_task": f"Store finished part on shelf {shelf}"}, "cnc": {"cycle_running": False, "cycle_complete": True, "part_present": False}},
                )
                self.complete_one_part()
                self.simulation["last_event"] = f"Completed machining cycle on shelf {shelf}"
            else:
                self.simulation["last_event"] = f"Moved active shelf pointer to {shelf}"

            self._diag("cell", "rx", {"tick": self.simulation["tick"], "active_shelf": shelf, "event": self.simulation["last_event"]})
            self._log("simulation", self.simulation["last_event"])
            return self.simulation

    def set_opcua_status(self, **updates: Any) -> Dict[str, Any]:
        with self.lock:
            self.opcua_status.update(updates)
            return self.opcua_status

    def _coerce_like(self, current: Any, value: Any) -> Any:
        if isinstance(current, bool):
            if isinstance(value, str):
                return value.strip().lower() in {"1", "true", "yes", "on", "ok"}
            return bool(value)
        if isinstance(current, int) and not isinstance(current, bool):
            return int(value)
        if isinstance(current, float):
            return float(value)
        return str(value) if value is not None else ""

    def update_machine_signals(self, source: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            if {"group", "key", "value"}.issubset(payload):
                payload = {str(payload["group"]): {str(payload["key"]): payload["value"]}}

            group_map = {
                "safety": self.safety_status,
                "robot": self.robot_status,
                "cnc": self.cnc_status,
                "leanlift": self.lift_status,
                "lift": self.lift_status,
            }
            key_aliases = {
                "safety": {"safetyok": "safety_ok", "emergencystopactive": "emergency_stop_active", "gatesclosed": "gates_closed", "scannerclear": "scanner_clear", "mode": "mode_key", "modekey": "mode_key"},
                "robot": {"ready": "ready", "busy": "busy", "fault": "fault", "athome": "at_home", "partingripper": "part_in_gripper", "stationcomplete": "station_complete", "activetask": "active_task", "statusmessage": "status_message"},
                "cnc": {"machineready": "machine_ready", "cyclerunning": "cycle_running", "cyclecomplete": "cycle_complete", "alarmactive": "alarm_active", "partpresent": "part_present", "selectedprogram": "selected_program", "loadedprogram": "loaded_program", "programsource": "program_source", "programtransferstate": "program_transfer_state", "statusmessage": "status_message"},
                "leanlift": {"currentshelf": "current_shelf", "accesspoint": "access_point", "robotshelf": "robot_shelf", "operatorshelf": "operator_shelf", "traypresent": "tray_present", "trayextended": "tray_extended", "doorclosed": "door_closed", "alarmactive": "alarm_active", "statusmessage": "status_message"},
                "lift": {"currentshelf": "current_shelf", "accesspoint": "access_point", "robotshelf": "robot_shelf", "operatorshelf": "operator_shelf", "traypresent": "tray_present", "trayextended": "tray_extended", "doorclosed": "door_closed", "alarmactive": "alarm_active", "statusmessage": "status_message"},
            }

            applied: Dict[str, Any] = {}
            for group_name, values in payload.items():
                normalized_group = str(group_name).lower()
                target = group_map.get(normalized_group)
                if not target or not isinstance(values, dict):
                    continue
                applied[normalized_group] = {}
                aliases = key_aliases.get(normalized_group, {})
                for raw_key, raw_value in values.items():
                    compact_key = str(raw_key).replace("_", "").replace(" ", "").lower()
                    key = aliases.get(compact_key, str(raw_key))
                    if key not in target:
                        continue
                    target[key] = self._coerce_like(target[key], raw_value)
                    applied[normalized_group][key] = target[key]

            self._derive_state_after_signal()
            if applied:
                self._diag("opcua" if source == "opcua" else "cell", "rx", {"source": source, "signals": applied})
                self._log("signals", f"{source} updated {', '.join(applied.keys())}")
            return self.get_state()

    def _derive_state_after_signal(self) -> None:
        self.safety_status["safety_ok"] = (
            not self.safety_status["emergency_stop_active"]
            and self.safety_status["gates_closed"]
            and self.safety_status["scanner_clear"]
        )
        if not self.safety_status["safety_ok"]:
            self.safety_status["last_trip"] = "E-stop/scanner/gate simulated trip"

        if self.robot_status["fault"]:
            self.robot_status["status_message"] = "Fault"
            self.robot_status["busy"] = False
        elif self.robot_status["busy"]:
            self.robot_status["status_message"] = "Busy"
        else:
            self.robot_status["status_message"] = "Ready" if self.robot_status["ready"] else "Not ready"

        if self.cnc_status["alarm_active"]:
            self.cnc_status["machine_state"] = "Alarm"
            self.cnc_status["alarm"] = "Simulated alarm"
        elif self.cnc_status["cycle_running"]:
            self.cnc_status["machine_state"] = "Running"
            self.cnc_status["spindle_rpm"] = 1400
            self.cnc_status["feed_rate"] = 220
        elif self.cnc_status["cycle_complete"]:
            self.cnc_status["machine_state"] = "Cycle complete"
            self.cnc_status["spindle_rpm"] = 0
            self.cnc_status["feed_rate"] = 0
        else:
            self.cnc_status["machine_state"] = "Ready" if self.cnc_status["machine_ready"] else "Not ready"
            self.cnc_status["spindle_rpm"] = 0
            self.cnc_status["feed_rate"] = 0

        if self.lift_status["alarm_active"]:
            self.lift_status["status_message"] = "Alarm"
        elif self.lift_status["tray_extended"]:
            self.lift_status["status_message"] = "Tray extended"
        else:
            self.lift_status["status_message"] = "Ready"
        current_shelf = str(self.lift_status["current_shelf"])
        if current_shelf in self.shelves:
            self.active_shelf = current_shelf
            if int(self.lift_status["access_point"]) == int(self.lift_status["robot_access_point"]):
                self.lift_status["robot_shelf"] = current_shelf
            if int(self.lift_status["access_point"]) == int(self.lift_status["operator_access_point"]):
                self.lift_status["operator_shelf"] = current_shelf

    def apply_sim_command(self, command: str, source: str = "web") -> Dict[str, Any]:
        with self.lock:
            text = (command or "").strip()
            if not text:
                return self.get_state()
            parts = text.split()
            name = parts[0].upper()
            arg = parts[1] if len(parts) > 1 else ""

            if name in {"GET_SHELF", "SHELF"} and arg:
                access_point = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else int(self.lift_status["operator_access_point"])
                self.request_shelf(arg, access_point, actor="opcua" if source == "opcua" else "operator", override=access_point == int(self.lift_status["robot_access_point"]))
            elif name == "TRAY_EXTEND":
                self.update_machine_signals(source, {"leanlift": {"tray_extended": True, "tray_present": True}})
            elif name in {"TRAY_HOME", "TRAY_RETRACT"}:
                self.update_machine_signals(source, {"leanlift": {"tray_extended": False}})
            elif name in {"CNC_START", "CYCLE_START"}:
                self.update_machine_signals(source, {"cnc": {"cycle_running": True, "cycle_complete": False}})
            elif name in {"CNC_COMPLETE", "CYCLE_COMPLETE"}:
                self.update_machine_signals(source, {"cnc": {"cycle_running": False, "cycle_complete": True}})
                self.complete_one_part()
            elif name == "ROBOT_FAULT":
                self.update_machine_signals(source, {"robot": {"fault": True}})
            elif name == "RESET_ALARMS":
                self.update_machine_signals(source, {"robot": {"fault": False}, "cnc": {"alarm_active": False}, "leanlift": {"alarm_active": False}, "safety": {"emergency_stop_active": False, "gates_closed": True, "scanner_clear": True}})
                self.safety_status["last_trip"] = "None"
            elif name == "SAFETY_TRIP":
                self.update_machine_signals(source, {"safety": {"emergency_stop_active": True}})
            elif name == "SAFETY_OK":
                self.update_machine_signals(source, {"safety": {"emergency_stop_active": False, "gates_closed": True, "scanner_clear": True}})
                self.safety_status["last_trip"] = "None"
            elif name == "MODE" and arg:
                mode_map = {"AUTO": "Automatic", "AUTOMATIC": "Automatic", "SETUP": "Setup/Manual", "MANUAL": "Setup/Manual", "SERVICE": "Maintenance/Service", "MAINTENANCE": "Maintenance/Service"}
                self.update_machine_signals(source, {"safety": {"mode_key": mode_map.get(arg.upper(), arg)}})
            else:
                self._log("message", f"{source}: {text}")
                self._diag("opcua" if source == "opcua" else "cell", "rx", {"message": text})
            return self.get_state()
