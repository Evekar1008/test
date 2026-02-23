from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Dict, List

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)


@dataclass
class Product:
    id: str
    name: str
    material: str
    diameter_mm: float
    cut_length_mm: float
    required_cnc_program: str


class ProductionCellService:
    def __init__(self) -> None:
        self.products: List[Product] = [
            Product("P1001", "Aksel Ø120", "42CrMo4", 120, 95, "O1200"),
            Product("P1002", "Flens Ø280", "S355", 280, 140, "O2801"),
            Product("P1003", "Hylse Ø80", "Al 6082", 80, 55, "O0802"),
        ]
        self.part_types: List[Dict] = [
            {"part_type_id": "PT-RAW-120", "name": "Råemne Ø120", "diameter_mm": 120, "length_mm": 95, "height_mm": 95, "product_id": "P1001", "quantity_total": 60},
            {"part_type_id": "PT-RAW-280", "name": "Råemne Ø280", "diameter_mm": 280, "length_mm": 140, "height_mm": 140, "product_id": "P1002", "quantity_total": 22},
            {"part_type_id": "PT-INP-080", "name": "Emne Ø80", "diameter_mm": 80, "length_mm": 55, "height_mm": 55, "product_id": "P1003", "quantity_total": 45},
        ]

        self.settings = {
            "shelf_width_mm": 2000,
            "shelf_depth_mm": 800,
            "status_colors": {
                "empty": "#cbd5e1",
                "raw": "#60a5fa",
                "in_process": "#f59e0b",
                "finished": "#34d399",
                "blocked": "#f87171",
            },
        }

        self.shelves = [str(i) for i in range(1, 51)]
        self.active_shelf = "1"
        self.shelf_slots: Dict[str, List[Dict]] = {s: self._generate_slots(4, 3) for s in self.shelves}

        self.robot_status = {"vendor": "Güdel + ABB IRC", "connection": "Online", "mode": "Auto", "active_task": "Idle", "alarms": []}
        self.cnc_status = {
            "vendor": "Fanuc",
            "connection": "Online (FOCAS)",
            "machine_state": "Klar",
            "selected_program": "O0001",
            "spindle_rpm": 0,
            "feed_rate": 0,
            "alarm": "Ingen",
            "part_counter": 0,
        }
        self.lift_status = {"connection": "Online", "mode": "Auto", "current_shelf": "1", "last_response": "Ingen kommando sendt"}
        self.simulation = {"running": False, "tick": 0, "active_shelf": "1", "last_event": "Ikke startet"}
        self.production_order = {"active": False, "part_type_id": "", "target_qty": 0, "processed_qty": 0, "mode": "quantity"}

        self.available_focas_functions = [
            "cnc_statinfo", "cnc_rdalmmsg2", "cnc_rdparam", "cnc_wrparam", "cnc_rdmacro", "cnc_wrmacro",
            "cnc_rdprognum", "cnc_pdf_rdmain", "cnc_start", "cnc_stop", "cnc_reset", "cnc_rdspmeter",
            "cnc_rdsvmeter", "cnc_rdposition", "cnc_rdexecprog", "cnc_rdspeed", "cnc_rdopmsg",
        ]
        self.available_leanlift_rest_commands = [
            "Login", "Logoff", "GetSystemStatus", "GetTrayInfo", "RequestTray", "StoreTray", "MoveToTray",
            "CreateBooking", "DeleteBooking", "GetInventory", "SetAutoMode", "SetManualMode", "AcknowledgeAlarm",
        ]

        self.history: List[Dict] = []
        self.diagnostics: List[Dict] = []

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _log(self, category: str, message: str) -> None:
        self.history.insert(0, {"ts": self._now(), "category": category, "message": message})
        self.history = self.history[:400]

    def _diag(self, channel: str, direction: str, payload: Dict) -> None:
        self.diagnostics.insert(0, {"ts": self._now(), "channel": channel, "direction": direction, "raw": payload})
        self.diagnostics = self.diagnostics[:500]

    def _get_part_type(self, part_type_id: str) -> Dict:
        pt = next((p for p in self.part_types if p["part_type_id"] == part_type_id), None)
        if not pt:
            raise ValueError(f"Ukjent part_type_id: {part_type_id}")
        return pt

    def _generate_slots(self, cols: int, rows: int, z_mm: float = 100) -> List[Dict]:
        slots = []
        slot_no = 1
        x_spacing = self.settings["shelf_width_mm"] / (cols + 1)
        y_spacing = self.settings["shelf_depth_mm"] / (rows + 1)
        for r in range(rows):
            for c in range(cols):
                slots.append(
                    {
                        "slot_no": slot_no,
                        "x_mm": round((c + 1) * x_spacing, 2),
                        "y_mm": round((r + 1) * y_spacing, 2),
                        "z_mm": z_mm,
                        "occupied": False,
                        "status": "empty",
                        "part_type_id": "",
                        "part_no": None,
                    }
                )
                slot_no += 1
        return slots

    def get_shelf_layout(self, shelf: str) -> Dict:
        if shelf not in self.shelves:
            raise ValueError("Ukjent hylle")
        return {
            "shelf": shelf,
            "shelf_width_mm": self.settings["shelf_width_mm"],
            "shelf_depth_mm": self.settings["shelf_depth_mm"],
            "status_colors": self.settings["status_colors"],
            "slots": self.shelf_slots[shelf],
        }

    def get_stats(self) -> Dict:
        all_slots = [slot for s in self.shelves for slot in self.shelf_slots[s]]
        return {
            "total_shelves": len(self.shelves),
            "total_slots": len(all_slots),
            "occupied_slots": sum(1 for s in all_slots if s["occupied"]),
            "finished_slots": sum(1 for s in all_slots if s["status"] == "finished"),
            "in_process_slots": sum(1 for s in all_slots if s["status"] == "in_process"),
            "simulation_ticks": self.simulation["tick"],
            "cnc_part_counter": self.cnc_status["part_counter"],
        }

    def get_state(self) -> Dict:
        return {
            "products": [asdict(p) for p in self.products],
            "part_types": self.part_types,
            "settings": self.settings,
            "shelves": self.shelves,
            "active_shelf": self.active_shelf,
            "robot": self.robot_status,
            "cnc": self.cnc_status,
            "lift": self.lift_status,
            "simulation": self.simulation,
            "production_order": self.production_order,
            "stats": self.get_stats(),
            "history": self.history[:100],
            "available_focas_functions": self.available_focas_functions,
            "available_leanlift_rest_commands": self.available_leanlift_rest_commands,
        }

    def update_settings(self, payload: Dict) -> Dict:
        if "shelf_width_mm" in payload:
            self.settings["shelf_width_mm"] = float(payload["shelf_width_mm"])
        if "shelf_depth_mm" in payload:
            self.settings["shelf_depth_mm"] = float(payload["shelf_depth_mm"])
        if "status_colors" in payload and isinstance(payload["status_colors"], dict):
            self.settings["status_colors"].update(payload["status_colors"])
        self._log("settings", "Oppdaterte settings")
        return self.settings

    def configure_shelf_layout_graphic(self, shelf: str, part_type_id: str, cols: int, rows: int, z_mm: float) -> Dict:
        if shelf not in self.shelves:
            raise ValueError("Ukjent hylle")
        self._get_part_type(part_type_id)
        slots = self._generate_slots(cols, rows, z_mm)
        for i, slot in enumerate(slots, start=1):
            slot["occupied"] = True
            slot["status"] = "raw"
            slot["part_type_id"] = part_type_id
            slot["part_no"] = i
        self.shelf_slots[shelf] = slots
        self._log("shelf", f"Grafisk layout definert for hylle {shelf}")
        return self.get_shelf_layout(shelf)

    def update_slot(self, shelf: str, slot_no: int, occupied: bool, status: str, part_type_id: str | None) -> Dict:
        slots = self.shelf_slots.get(shelf)
        if not slots:
            raise ValueError("Ukjent hylle")
        slot = next((s for s in slots if s["slot_no"] == slot_no), None)
        if not slot:
            raise ValueError("Ukjent slot")

        slot["occupied"] = occupied
        slot["status"] = status
        slot["part_type_id"] = part_type_id or ""
        slot["part_no"] = slot_no if occupied else None
        self._log("lift", f"Manuell {'innlasting' if occupied else 'utlasting'} på hylle {shelf}, slot {slot_no}")
        return slot


    def upsert_part_type(self, payload: Dict) -> Dict:
        part_type_id = payload.get("part_type_id", "").strip()
        if not part_type_id:
            raise ValueError("part_type_id er påkrevd")
        record = {
            "part_type_id": part_type_id,
            "name": payload.get("name", "Uten navn"),
            "diameter_mm": float(payload.get("diameter_mm", 0)),
            "length_mm": float(payload.get("length_mm", 0)),
            "height_mm": float(payload.get("height_mm", 0)),
            "product_id": payload.get("product_id", ""),
            "quantity_total": int(payload.get("quantity_total", 0)),
        }
        if record["diameter_mm"] <= 0 or record["length_mm"] <= 0 or record["height_mm"] <= 0:
            raise ValueError("Diameter/lengde/høyde må være > 0")
        existing = next((p for p in self.part_types if p["part_type_id"] == part_type_id), None)
        if existing:
            existing.update(record)
        else:
            self.part_types.append(record)
        self._log("parts", f"Lagret deltype {part_type_id}")
        return record

    def start_production(self, part_type_id: str, mode: str, quantity: int | None) -> Dict:
        pt = self._get_part_type(part_type_id)
        target = pt["quantity_total"] if mode == "all" else int(quantity or 0)
        if target <= 0:
            raise ValueError("Antall må være > 0")
        self.production_order = {"active": True, "part_type_id": part_type_id, "target_qty": target, "processed_qty": 0, "mode": mode}
        self._log("production", f"Startet produksjon: {part_type_id}, target={target}, mode={mode}")
        return self.production_order

    def complete_one_part(self) -> None:
        if not self.production_order["active"]:
            return
        self.production_order["processed_qty"] += 1
        self.cnc_status["part_counter"] += 1
        if self.production_order["processed_qty"] >= self.production_order["target_qty"]:
            self.production_order["active"] = False
            self._log("production", "Produksjon ferdig")

    def call_cnc_focas(self, function_name: str, params: Dict) -> Dict:
        if function_name not in self.available_focas_functions:
            raise ValueError("FOCAS-funksjon ikke tilgjengelig i simulering")
        self._diag("cnc", "tx", {"function": function_name, "params": params})

        if function_name in ["cnc_start", "cnc_stop", "cnc_reset"]:
            self.cnc_status["machine_state"] = {"cnc_start": "Kjører", "cnc_stop": "Stop", "cnc_reset": "Klar"}[function_name]
        if function_name == "cnc_rdspmeter":
            response = {"spindle": self.cnc_status["spindle_rpm"]}
        elif function_name == "cnc_rdspeed":
            response = {"spindle_rpm": self.cnc_status["spindle_rpm"], "feed_rate": self.cnc_status["feed_rate"]}
        else:
            response = {"result": "ok", "function": function_name}

        out = {"function": function_name, "params": params, "response": response}
        self._diag("cnc", "rx", out)
        self._log("cnc", f"FOCAS: {function_name}")
        return out

    def call_lift_rest(self, function_name: str, params: Dict) -> Dict:
        if function_name not in self.available_leanlift_rest_commands:
            raise ValueError("LeanLift REST-kommando ikke tilgjengelig i simulering")
        self._diag("lift", "tx", {"command": function_name, "params": params})

        if function_name in ["RequestTray", "MoveToTray", "GetTrayInfo"]:
            shelf = str(params.get("shelf", self.lift_status["current_shelf"]))
            if shelf in self.shelves:
                self.lift_status["current_shelf"] = shelf
        response = {"command": function_name, "accepted": True, "current_shelf": self.lift_status["current_shelf"]}
        self.lift_status["last_response"] = str(response)

        out = {"function": function_name, "params": params, "response": response}
        self._diag("lift", "rx", out)
        self._log("lift", f"REST: {function_name}")
        return out

    def simulation_start(self) -> Dict:
        self.simulation["running"] = True
        self.simulation["last_event"] = "Simulering startet"
        self.robot_status["active_task"] = "Simulering kjører"
        self._log("simulation", "Start")
        return self.simulation

    def simulation_pause(self) -> Dict:
        self.simulation["running"] = False
        self.simulation["last_event"] = "Simulering pauset"
        self.robot_status["active_task"] = "Idle"
        self.cnc_status["spindle_rpm"] = 0
        self.cnc_status["feed_rate"] = 0
        self._log("simulation", "Pause")
        return self.simulation

    def simulation_step(self) -> Dict:
        self.simulation["tick"] += 1
        shelf_index = (self.simulation["tick"] - 1) % len(self.shelves)
        shelf = self.shelves[shelf_index]
        self.active_shelf = shelf
        self.simulation["active_shelf"] = shelf
        self.lift_status["current_shelf"] = shelf

        slots = self.shelf_slots[shelf]
        if self.simulation["tick"] % 2 == 1:
            self.robot_status["active_task"] = f"Laster del fra hylle {shelf}"
            self.cnc_status["machine_state"] = "Kjører"
            self.cnc_status["spindle_rpm"] = 1400
            self.cnc_status["feed_rate"] = 220
            for s in slots:
                if s["occupied"]:
                    s["status"] = "in_process"
            self.simulation["last_event"] = f"Startet prosess på hylle {shelf}"
        else:
            self.robot_status["active_task"] = f"Lagrer ferdig del på hylle {shelf}"
            self.cnc_status["machine_state"] = "Klar"
            self.cnc_status["spindle_rpm"] = 0
            self.cnc_status["feed_rate"] = 0
            for s in slots:
                if s["occupied"]:
                    s["status"] = "finished"
            self.complete_one_part()
            self.simulation["last_event"] = f"Fullførte prosess på hylle {shelf}"

        self._diag("cell", "rx", {"tick": self.simulation["tick"], "active_shelf": shelf, "event": self.simulation["last_event"]})
        self._log("simulation", self.simulation["last_event"])
        return self.simulation


service = ProductionCellService()


@app.get("/")
def dashboard_page():
    return render_template("dashboard.html")


@app.get("/shelves")
def shelves_page():
    return render_template("shelves.html")


@app.get("/parts")
def parts_page():
    return render_template("parts.html")


@app.get("/cnc")
def cnc_page():
    return render_template("cnc.html")


@app.get("/lift")
def lift_page():
    return render_template("lift.html")


@app.get("/stats")
def stats_page():
    return render_template("stats.html")


@app.get("/diagnostics")
def diagnostics_page():
    return render_template("diagnostics.html")


@app.get("/api/state")
def api_state():
    return jsonify(service.get_state())


@app.get("/api/diagnostics")
def api_diagnostics():
    return jsonify(service.diagnostics)


@app.get("/api/leanlift/shelf-layout/<shelf>")
def api_shelf_layout(shelf: str):
    try:
        return jsonify(service.get_shelf_layout(shelf))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/settings")
def api_settings():
    try:
        return jsonify(service.update_settings(request.get_json(force=True)))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/shelf/configure-graphic")
def api_shelf_configure_graphic():
    payload = request.get_json(force=True)
    try:
        return jsonify(service.configure_shelf_layout_graphic(str(payload.get("shelf", "")), payload.get("part_type_id", ""), int(payload.get("cols", 4)), int(payload.get("rows", 3)), float(payload.get("z_mm", 100))))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/shelf/slot/update")
def api_slot_update():
    payload = request.get_json(force=True)
    try:
        return jsonify(service.update_slot(str(payload.get("shelf", "")), int(payload.get("slot_no", 0)), bool(payload.get("occupied", False)), payload.get("status", "empty"), payload.get("part_type_id")))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/parts")
def api_parts():
    payload = request.get_json(force=True)
    try:
        return jsonify(service.upsert_part_type(payload))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/production/start")
def api_production_start():
    payload = request.get_json(force=True)
    try:
        return jsonify(service.start_production(payload.get("part_type_id", ""), payload.get("mode", "quantity"), payload.get("quantity")))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/cnc/focas")
def api_cnc_focas():
    payload = request.get_json(force=True)
    try:
        return jsonify(service.call_cnc_focas(payload.get("function_name", ""), payload.get("params", {})))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/lift/command")
def api_lift_command():
    payload = request.get_json(force=True)
    try:
        return jsonify(service.call_lift_rest(payload.get("function_name", ""), payload.get("params", {})))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/simulation/start")
def api_sim_start():
    return jsonify(service.simulation_start())


@app.post("/api/simulation/pause")
def api_sim_pause():
    return jsonify(service.simulation_pause())


@app.post("/api/simulation/step")
def api_sim_step():
    return jsonify(service.simulation_step())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
