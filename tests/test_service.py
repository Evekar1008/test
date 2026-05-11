import importlib
import time

from app import ProductionCellService, app
from cell_controller import CellController
from config import load_config
from integrations.cmz_focas_client import CmzFocasClient
from integrations.cmz_loader_signals import build_cmz_signal_map
from integrations.haenel_client import HaenelClient


def test_shelves_are_numbered_1_to_50():
    service = ProductionCellService()
    assert service.shelves[0] == "1"
    assert service.shelves[-1] == "50"


def test_active_shelf_layout_tracks_simulation_step():
    service = ProductionCellService()
    service.simulation_step()
    assert service.active_shelf == "1"
    service.simulation_step()
    assert service.active_shelf == "2"


def test_start_production_quantity_and_complete():
    service = ProductionCellService()
    order = service.start_production("PT-RAW-120", "quantity", 2)
    assert order["target_qty"] == 2
    assert order["selected_program"] == "O1200"
    assert order["cycle_time_sec_estimate"] > 0
    assert service.get_state()["dashboard"]["remaining_hours"] > 0
    service.complete_one_part()
    service.complete_one_part()
    assert service.production_order["active"] is False


def test_job_start_loads_uploaded_program_and_sets_fifo_robot_target():
    service = ProductionCellService()
    upload = service.register_uploaded_nc_program("O1200.NC", r"C:\NC\O1200.NC", "O1200")
    job = service.create_job({"job_name": "Aksel serie 1", "part_type_id": "PT-RAW-120", "fifo_enabled": True, **upload})

    order = service.start_job(job["job_id"], "quantity", 2)

    assert order["job_id"] == job["job_id"]
    assert service.cnc_status["loaded_program"] == "O1200"
    assert service.cnc_status["program_source"] == "uploaded"
    assert service.lift_status["current_shelf"] == "1"
    assert service.robot_status["next_pick"]["shelf"] == "1"
    assert service.robot_status["next_pick"]["slot_no"] == 1
    assert service.robot_status["place_target"] == service.robot_status["next_pick"]
    assert service.shelf_slots["1"][0]["status"] == "reserved"
    assert service.shelf_slots["1"][1]["status"] == "reserved"


def test_job_can_use_existing_cnc_program():
    service = ProductionCellService()
    job = service.create_job(
        {
            "job_name": "CNC eksisterende",
            "part_type_id": "PT-RAW-120",
            "program_source_type": "cnc_existing",
            "program_name": "O1201",
        }
    )

    order = service.start_job(job["job_id"], "quantity", 1)

    assert order["selected_program"] == "O1201"
    assert service.cnc_status["program_transfer_state"] == "Using existing CNC program"


def test_set_shelf_status_changes_all_occupied_locations_only():
    service = ProductionCellService()
    service.update_slot("1", 1, False, "empty", "")

    result = service.set_shelf_status("1", "quarantine")

    assert result["changed"] == 11
    assert service.shelf_slots["1"][0]["status"] == "empty"
    assert all(slot["status"] == "quarantine" for slot in service.shelf_slots["1"][1:])


def test_fill_and_empty_entire_shelf():
    service = ProductionCellService()
    service.set_shelf_status("6", "raw", include_empty=True, part_type_id="PT-RAW-120")

    assert all(slot["occupied"] for slot in service.shelf_slots["6"])
    assert all(slot["part_type_id"] == "PT-RAW-120" for slot in service.shelf_slots["6"])
    assert all(slot["status"] == "raw" for slot in service.shelf_slots["6"])

    result = service.set_shelf_status("6", "empty", include_empty=True)

    assert result["changed"] == len(service.shelf_slots["6"])
    assert all(not slot["occupied"] for slot in service.shelf_slots["6"])
    assert all(slot["status"] == "empty" for slot in service.shelf_slots["6"])


def test_graphic_layout_and_manual_load_unload():
    service = ProductionCellService()
    layout = service.configure_shelf_layout_graphic("5", "PT-RAW-120", 2, 2, 95, 20, 50)
    assert len(layout["slots"]) == 4
    assert layout["slots"][0]["x_mm"] == 110
    assert layout["slots"][1]["x_mm"] == 250
    updated = service.update_slot("5", 1, False, "empty", "")
    assert updated["occupied"] is False


def test_layout_clearance_rejects_overlap_or_wall_collision():
    service = ProductionCellService()
    try:
        service.configure_shelf_layout_graphic("5", "PT-RAW-280", 6, 3, 140, 120, 300)
    except ValueError as exc:
        assert "does not fit" in str(exc)
    else:
        raise AssertionError("Expected layout size validation error")


def test_imported_layout_rows_are_validated_and_loaded():
    service = ProductionCellService()
    rows = [
        {"slot_no": 1, "x_mm": 110, "y_mm": 110, "z_mm": 95, "part_no": 10},
        {"slot_no": 2, "x_mm": 250, "y_mm": 110, "z_mm": 95, "part_no": 11},
    ]
    layout = service.import_shelf_layout_rows("8", "PT-RAW-120", rows, 20, 50)

    assert len(layout["slots"]) == 2
    assert layout["slots"][0]["part_no"] == 10
    assert layout["slots"][1]["status"] == "raw"


def test_cylinder_tray_auto_layout_uses_hex_when_it_fits_more_parts():
    service = ProductionCellService()
    layout = service.configure_shelf_layout_graphic(
        "9",
        "PT-INP-080",
        4,
        3,
        55,
        part_clearance_mm=10,
        wall_clearance_mm=40,
        packing="Auto",
        material="Aluminum",
        density_kg_m3=2700,
        max_height_mm=150,
    )

    assert layout["layout_metadata"]["source"] == "cylinder_tray"
    assert layout["layout_metadata"]["count"] == len(layout["slots"])
    assert layout["layout_metadata"]["total_weight_kg"] > 0


def test_lift_access_points_separate_operator_and_robot_requests():
    service = ProductionCellService()
    service.request_shelf("4", access_point=1, actor="operator")
    assert service.lift_status["operator_shelf"] == "4"

    try:
        service.request_shelf("7", access_point=2, actor="operator")
    except ValueError as exc:
        assert "service override" in str(exc)
    else:
        raise AssertionError("Expected robot access validation error")

    service.request_shelf("7", access_point=2, actor="service", override=True)
    assert service.lift_status["robot_shelf"] == "7"


def test_focas_and_lift_and_diagnostics():
    service = ProductionCellService()
    focas = service.call_cnc_focas("cnc_statinfo", {})
    lift = service.call_lift_rest("get_shelf", {"pm01_shelfNumber": "7"})
    assert "response" in focas
    assert lift["response"]["current_shelf"] == "7"
    assert len(service.diagnostics) >= 2


def test_production_rejects_non_whitelisted_program():
    service = ProductionCellService()
    service.cnc_status["selected_program"] = "O9999"
    try:
        service.start_production("PT-RAW-120", "quantity", 1)
    except ValueError as exc:
        assert "not whitelisted" in str(exc)
    else:
        raise AssertionError("Expected whitelist validation error")


def test_opcua_style_signal_updates_cell_state():
    service = ProductionCellService()
    state = service.update_machine_signals("opcua", {"cnc": {"CycleRunning": True}, "leanlift": {"CurrentShelf": 4}})
    assert state["cnc"]["cycle_running"] is True
    assert state["cnc"]["machine_state"] == "Running"
    assert state["active_shelf"] == "4"


def test_sim_command_can_drive_safety_and_lift():
    service = ProductionCellService()
    service.apply_sim_command("SAFETY_TRIP", source="test")
    assert service.safety_status["safety_ok"] is False
    service.apply_sim_command("SAFETY_OK", source="test")
    service.apply_sim_command("GET_SHELF 9", source="test")
    assert service.safety_status["safety_ok"] is True
    assert service.lift_status["current_shelf"] == "9"


def test_reference_files_are_loaded_for_commands_and_focas():
    service = ProductionCellService()
    assert "get_shelf" in service.available_leanlift_rest_commands
    assert "read_status" in service.available_leanlift_rest_commands
    assert "pm01_shelfNumber" in service.leanlift_command_params.get("get_shelf", [])
    assert "cnc_statinfo" in service.available_focas_functions
    assert "cnc_rdparam" in service.available_focas_functions
    assert len(service.focas_function_params.get("cnc_rdparam", [])) > 0


def test_development_users_authenticate_by_role():
    service = ProductionCellService()
    assert service.authenticate_user("operator", "operator123")["role"] == "operator"
    assert service.authenticate_user("admin", "admin123")["role"] == "administrator"
    assert service.authenticate_user("admin", "wrong") is None


def test_dashboard_is_public_but_admin_requires_login():
    app.config.update(TESTING=True)
    client = app.test_client()

    assert client.get("/").status_code == 200
    assert client.get("/admin").status_code == 302

    login = client.post("/login", data={"username": "admin", "password": "admin123", "next": "/admin"})
    assert login.status_code == 302
    assert client.get("/admin").status_code == 200


def test_signal_maps_use_selected_cmz_family_addresses():
    ta_td = build_cmz_signal_map("TA_TD")
    ttl_tts = build_cmz_signal_map("TTL_TTS")

    assert ta_td.base == 2000
    assert ta_td.out.m474_executed.address == 2052
    assert ta_td.in_.loader_inside.address == 2000

    assert ttl_tts.base == 6100
    assert ttl_tts.out.m474_executed.address == 6152
    assert ttl_tts.in_.loader_inside.address == 6100


def test_invalid_machine_family_env_raises(monkeypatch):
    monkeypatch.setenv("CMZ_MACHINE_FAMILY", "BAD_FAMILY")
    try:
        load_config()
    except RuntimeError as exc:
        assert "Invalid CMZ_MACHINE_FAMILY" in str(exc)
    else:
        raise AssertionError("Expected invalid machine family to fail")


def test_cell_controller_start_is_single_thread():
    service = ProductionCellService()
    signals = build_cmz_signal_map("TA_TD")
    controller = CellController(
        service,
        CmzFocasClient("127.0.0.1", signals, status_provider=service.get_state),
        HaenelClient("http://127.0.0.1"),
    )

    controller.start()
    first_thread = controller.thread
    controller.start()
    assert controller.thread is first_thread
    assert first_thread is not None
    assert first_thread.is_alive()

    controller.stop()
    first_thread.join(timeout=2)
    assert not first_thread.is_alive()


def test_flask_job_start_submits_controller_command_without_blocking(monkeypatch):
    app_module = importlib.import_module("app")

    class FakeController:
        def __init__(self):
            self.commands = []

        def submit(self, name, payload=None):
            self.commands.append((name, payload or {}))

    fake = FakeController()
    monkeypatch.setattr(app_module, "cell_controller", fake)
    app.config.update(TESTING=True)

    job = app_module.service.create_job(
        {
            "job_name": f"Pytest job {time.time()}",
            "part_type_id": "PT-RAW-120",
            "program_source_type": "cnc_existing",
            "program_name": "O1200",
        }
    )

    client = app.test_client()
    client.post("/login", data={"username": "operator", "password": "operator123", "next": "/"})
    started_at = time.monotonic()
    response = client.post(f"/api/jobs/{job['job_id']}/start", json={"mode": "quantity", "quantity": 1})
    elapsed = time.monotonic() - started_at

    assert response.status_code == 200
    assert elapsed < 1.0
    assert fake.commands == [("START_JOB", {"job_id": job["job_id"]})]
