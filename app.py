from __future__ import annotations

from dataclasses import asdict, dataclass
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

        self.settings = {"shelf_width_mm": 2000, "shelf_depth_mm": 800}
        self.shelves = [str(i) for i in range(1, 51)]

        self.part_types: List[Dict] = [
            {"part_type_id": "PT-RAW-120", "name": "Råemne Ø120", "diameter_mm": 120, "length_mm": 95, "height_mm": 95, "product_id": "P1001"},
            {"part_type_id": "PT-RAW-280", "name": "Råemne Ø280", "diameter_mm": 280, "length_mm": 140, "height_mm": 140, "product_id": "P1002"},
            {"part_type_id": "PT-INP-080", "name": "Emne Ø80", "diameter_mm": 80, "length_mm": 55, "height_mm": 55, "product_id": "P1003"},
        ]

        self.layout_templates: Dict[str, Dict] = {
            "standard-120": {
                "template_name": "standard-120",
                "part_type_id": "PT-RAW-120",
                "placements": [
                    {"part_type_id": "PT-RAW-120", "x_mm": 250, "y_mm": 200, "z_mm": 95},
                    {"part_type_id": "PT-RAW-120", "x_mm": 520, "y_mm": 200, "z_mm": 95},
                    {"part_type_id": "PT-RAW-120", "x_mm": 790, "y_mm": 200, "z_mm": 95},
                ],
            },
            "standard-280": {
                "template_name": "standard-280",
                "part_type_id": "PT-RAW-280",
                "placements": [
                    {"part_type_id": "PT-RAW-280", "x_mm": 300, "y_mm": 260, "z_mm": 140},
                    {"part_type_id": "PT-RAW-280", "x_mm": 700, "y_mm": 260, "z_mm": 140},
                ],
            },
        }

        self.shelf_assignments: Dict[str, Dict] = {}
        for shelf in self.shelves:
            if int(shelf) <= 20:
                self.shelf_assignments[shelf] = {"template_name": "standard-120", "status": "Råemne"}
            elif int(shelf) <= 35:
                self.shelf_assignments[shelf] = {"template_name": "standard-280", "status": "Råemne"}
            elif int(shelf) <= 45:
                self.shelf_assignments[shelf] = {"template_name": "standard-120", "status": "Ferdig"}
            else:
                self.shelf_assignments[shelf] = {"template_name": "standard-120", "status": "Under prosess"}

        self.robot_status = {"vendor": "Güdel + ABB IRC", "connection": "Online", "mode": "Auto", "active_task": "Idle", "alarms": []}
        self.cnc_status = {
            "vendor": "Fanuc",
            "connection": "Online (FOCAS)",
            "machine_state": "Klar",
            "selected_program": "O0001",
            "spindle_rpm": 0,
            "feed_rate": 0,
            "alarm": "Ingen",
        }
        self.simulation = {"running": False, "tick": 0, "active_shelf": "1", "last_event": "Ikke startet"}
        self.active_product_id = "P1001"

    def _get_part_type(self, part_type_id: str) -> Dict:
        pt = next((p for p in self.part_types if p["part_type_id"] == part_type_id), None)
        if not pt:
            raise ValueError(f"Ukjent part_type_id: {part_type_id}")
        return pt

    def _validate_xy(self, x_mm: float, y_mm: float, diameter_mm: float) -> None:
        radius = diameter_mm / 2
        if x_mm - radius < 0 or x_mm + radius > self.settings["shelf_width_mm"]:
            raise ValueError("X-koordinat plasserer delen utenfor hyllebredde")
        if y_mm - radius < 0 or y_mm + radius > self.settings["shelf_depth_mm"]:
            raise ValueError("Y-koordinat plasserer delen utenfor hyldedybde")

    def _validate_template_payload(self, placements: List[Dict]) -> str:
        if not placements:
            raise ValueError("Malen må ha minst én plassering")
        part_type_ids = {p["part_type_id"] for p in placements}
        if len(part_type_ids) != 1:
            raise ValueError("Alle delene på en hylle må være av samme type")
        first_part_type_id = next(iter(part_type_ids))
        part_type = self._get_part_type(first_part_type_id)
        for p in placements:
            self._validate_xy(float(p["x_mm"]), float(p["y_mm"]), float(part_type["diameter_mm"]))
            if float(p.get("z_mm", part_type["height_mm"])) <= 0:
                raise ValueError("Z-koordinat/høyde må være > 0")
        return first_part_type_id

    def get_shelf_layout(self, shelf: str) -> Dict:
        assignment = self.shelf_assignments.get(str(shelf))
        if not assignment:
            raise ValueError(f"Ukjent hylle: {shelf}")
        template = self.layout_templates[assignment["template_name"]]
        placements = []
        for p in template["placements"]:
            part_type = self._get_part_type(p["part_type_id"])
            placements.append(
                {
                    "part_type_id": p["part_type_id"],
                    "name": part_type["name"],
                    "product_id": part_type["product_id"],
                    "diameter_mm": part_type["diameter_mm"],
                    "length_mm": part_type["length_mm"],
                    "height_mm": part_type["height_mm"],
                    "x_mm": p["x_mm"],
                    "y_mm": p["y_mm"],
                    "z_mm": p.get("z_mm", part_type["height_mm"]),
                    "status": assignment["status"],
                }
            )
        return {
            "shelf": str(shelf),
            "template_name": assignment["template_name"],
            "shelf_width_mm": self.settings["shelf_width_mm"],
            "shelf_depth_mm": self.settings["shelf_depth_mm"],
            "part_type_id": template["part_type_id"],
            "placements": placements,
        }

    def get_state(self) -> Dict:
        return {
            "active_product_id": self.active_product_id,
            "products": [asdict(p) for p in self.products],
            "settings": self.settings,
            "part_types": self.part_types,
            "layout_templates": list(self.layout_templates.values()),
            "shelves": self.shelves,
            "shelf_layouts": [self.get_shelf_layout(s) for s in self.shelves],
            "robot": self.robot_status,
            "cnc": self.cnc_status,
            "simulation": self.simulation,
        }

    def update_settings(self, shelf_width_mm: float, shelf_depth_mm: float) -> Dict:
        if shelf_width_mm <= 0 or shelf_depth_mm <= 0:
            raise ValueError("Hyllebredde og hyldedybde må være > 0")
        old_settings = self.settings.copy()
        self.settings["shelf_width_mm"] = shelf_width_mm
        self.settings["shelf_depth_mm"] = shelf_depth_mm
        try:
            for template in self.layout_templates.values():
                self._validate_template_payload(template["placements"])
        except ValueError:
            self.settings = old_settings
            raise
        return self.settings

    def upsert_layout_template(self, template_name: str, placements: List[Dict]) -> Dict:
        if not template_name:
            raise ValueError("template_name er påkrevd")
        part_type_id = self._validate_template_payload(placements)
        part_type = self._get_part_type(part_type_id)
        self.layout_templates[template_name] = {
            "template_name": template_name,
            "part_type_id": part_type_id,
            "placements": [
                {"part_type_id": part_type_id, "x_mm": float(p["x_mm"]), "y_mm": float(p["y_mm"]), "z_mm": float(p.get("z_mm", part_type["height_mm"]))}
                for p in placements
            ],
        }
        return self.layout_templates[template_name]

    def apply_template_to_shelf(self, shelf: str, template_name: str, status: str | None = None) -> Dict:
        shelf_key = str(shelf)
        if shelf_key not in self.shelves:
            raise ValueError(f"Ukjent hylle: {shelf}")
        if template_name not in self.layout_templates:
            raise ValueError(f"Ukjent template_name: {template_name}")
        self.shelf_assignments[shelf_key]["template_name"] = template_name
        if status:
            self.shelf_assignments[shelf_key]["status"] = status
        self.robot_status["active_task"] = f"Oppdaterte layout på hylle {shelf_key} med mal {template_name}"
        return self.get_shelf_layout(shelf_key)

    def select_product(self, product_id: str) -> Dict:
        product = next((p for p in self.products if p.id == product_id), None)
        if not product:
            raise ValueError(f"Ukjent produkt: {product_id}")
        self.active_product_id = product.id
        self.robot_status["active_task"] = f"Klargjør håndtering for {product.name}"
        self.cnc_status["selected_program"] = product.required_cnc_program
        return self.get_state()

    def select_cnc_program(self, program_number: str) -> Dict:
        if not program_number or not program_number.startswith("O"):
            raise ValueError("Program må starte med 'O', f.eks. O1200")
        self.cnc_status["selected_program"] = program_number
        self.cnc_status["machine_state"] = "Program valgt"
        return self.cnc_status

    def simulation_start(self) -> Dict:
        self.simulation["running"] = True
        self.simulation["last_event"] = "Simulering startet"
        self.robot_status["active_task"] = "Simulering kjører"
        return self.simulation

    def simulation_pause(self) -> Dict:
        self.simulation["running"] = False
        self.simulation["last_event"] = "Simulering pauset"
        self.robot_status["active_task"] = "Idle"
        self.cnc_status["spindle_rpm"] = 0
        self.cnc_status["feed_rate"] = 0
        return self.simulation

    def simulation_step(self) -> Dict:
        self.simulation["tick"] += 1
        shelf_index = (self.simulation["tick"] - 1) % len(self.shelves)
        shelf = self.shelves[shelf_index]
        self.simulation["active_shelf"] = shelf

        if self.simulation["tick"] % 2 == 1:
            self.shelf_assignments[shelf]["status"] = "Under prosess"
            self.cnc_status["machine_state"] = "Kjører"
            self.cnc_status["spindle_rpm"] = 1200 + shelf_index * 5
            self.cnc_status["feed_rate"] = 180 + shelf_index
            self.robot_status["active_task"] = f"Laster del fra hylle {shelf}"
            self.simulation["last_event"] = f"Startet bearbeiding på hylle {shelf}"
        else:
            self.shelf_assignments[shelf]["status"] = "Ferdig"
            self.cnc_status["machine_state"] = "Klar"
            self.cnc_status["spindle_rpm"] = 0
            self.cnc_status["feed_rate"] = 0
            self.robot_status["active_task"] = f"Legger ferdig del tilbake på hylle {shelf}"
            self.simulation["last_event"] = f"Fullførte bearbeiding på hylle {shelf}"

        return self.simulation


service = ProductionCellService()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/api/state")
def api_state():
    return jsonify(service.get_state())


@app.get("/api/leanlift/shelf-layout/<shelf>")
def api_shelf_layout(shelf: str):
    try:
        return jsonify(service.get_shelf_layout(shelf))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/settings")
def api_update_settings():
    payload = request.get_json(force=True)
    try:
        return jsonify(
            service.update_settings(
                shelf_width_mm=float(payload.get("shelf_width_mm", 0)),
                shelf_depth_mm=float(payload.get("shelf_depth_mm", 0)),
            )
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/layout-templates")
def api_upsert_layout_template():
    payload = request.get_json(force=True)
    try:
        return jsonify(service.upsert_layout_template(payload.get("template_name", ""), payload.get("placements", [])))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/shelf/apply-template")
def api_apply_template_to_shelf():
    payload = request.get_json(force=True)
    try:
        return jsonify(service.apply_template_to_shelf(payload.get("shelf", ""), payload.get("template_name", ""), payload.get("status")))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/select-product")
def api_select_product():
    payload = request.get_json(force=True)
    try:
        return jsonify(service.select_product(payload.get("product_id", "")))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/cnc/select-program")
def api_select_cnc_program():
    payload = request.get_json(force=True)
    try:
        return jsonify(service.select_cnc_program(payload.get("program_number", "")))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/simulation/start")
def api_simulation_start():
    return jsonify(service.simulation_start())


@app.post("/api/simulation/pause")
def api_simulation_pause():
    return jsonify(service.simulation_pause())


@app.post("/api/simulation/step")
def api_simulation_step():
    return jsonify(service.simulation_step())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
