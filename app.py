from __future__ import annotations

from flask import Flask, jsonify, render_template, request

from cell_service import ProductionCellService
from opcua_server import OpcUaSimulator


app = Flask(__name__)
service = ProductionCellService()
opcua_simulator = OpcUaSimulator(service)


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


@app.get("/opcua")
def opcua_page():
    return render_template("opcua.html")


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
        return jsonify(
            service.configure_shelf_layout_graphic(
                str(payload.get("shelf", "")),
                payload.get("part_type_id", ""),
                int(payload.get("cols", 4)),
                int(payload.get("rows", 3)),
                float(payload.get("z_mm", 100)),
            )
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/shelf/slot/update")
def api_slot_update():
    payload = request.get_json(force=True)
    try:
        return jsonify(
            service.update_slot(
                str(payload.get("shelf", "")),
                int(payload.get("slot_no", 0)),
                bool(payload.get("occupied", False)),
                payload.get("status", "empty"),
                payload.get("part_type_id"),
            )
        )
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/parts")
def api_parts():
    try:
        return jsonify(service.upsert_part_type(request.get_json(force=True)))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/production/start")
def api_production_start():
    payload = request.get_json(force=True)
    try:
        return jsonify(service.start_production(payload.get("part_type_id", ""), payload.get("mode", "quantity"), payload.get("quantity")))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400


@app.post("/api/production/stop")
def api_production_stop():
    payload = request.get_json(silent=True) or {}
    return jsonify(service.stop_production(payload.get("reason", "Stopped from HMI")))


@app.post("/api/cnc/program/select")
def api_cnc_program_select():
    payload = request.get_json(force=True)
    try:
        return jsonify(service.select_cnc_program(payload.get("product_id", ""), payload.get("program", ""), payload.get("operator", "development")))
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


@app.get("/api/opcua/status")
def api_opcua_status():
    return jsonify(service.get_state()["opcua"])


@app.post("/api/opcua/start")
def api_opcua_start():
    started = opcua_simulator.start()
    state = service.get_state()["opcua"]
    state["start_requested"] = started
    return jsonify(state)


@app.post("/api/opcua/signal")
def api_opcua_signal():
    payload = request.get_json(force=True)
    if "command" in payload:
        return jsonify(service.apply_sim_command(payload.get("command", ""), source="web"))
    return jsonify(service.update_machine_signals("web", payload))


@app.post("/api/simulation/start")
def api_sim_start():
    return jsonify(service.simulation_start())


@app.post("/api/simulation/pause")
def api_sim_pause():
    return jsonify(service.simulation_pause())


@app.post("/api/simulation/step")
def api_sim_step():
    return jsonify(service.simulation_step())


def start_background_services() -> None:
    opcua_simulator.start()


if __name__ == "__main__":
    start_background_services()
    app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)
