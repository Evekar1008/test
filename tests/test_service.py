from app import ProductionCellService


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
    service.complete_one_part()
    service.complete_one_part()
    assert service.production_order["active"] is False


def test_graphic_layout_and_manual_load_unload():
    service = ProductionCellService()
    layout = service.configure_shelf_layout_graphic("5", "PT-RAW-120", 2, 2, 95)
    assert len(layout["slots"]) == 4
    updated = service.update_slot("5", 1, False, "empty", "")
    assert updated["occupied"] is False


def test_focas_and_lift_and_diagnostics():
    service = ProductionCellService()
    focas = service.call_cnc_focas("cnc_statinfo", {})
    lift = service.call_lift_rest("get_shelf", {"pm01_shelfNumber": "7"})
    assert "response" in focas
    assert lift["response"]["current_shelf"] == "7"
    assert len(service.diagnostics) >= 2


def test_reference_files_are_loaded_for_commands_and_focas():
    service = ProductionCellService()
    assert "get_shelf" in service.available_leanlift_rest_commands
    assert "read_status" in service.available_leanlift_rest_commands
    assert "pm01_shelfNumber" in service.leanlift_command_params.get("get_shelf", [])
    assert "cnc_statinfo" in service.available_focas_functions
    assert "cnc_rdparam" in service.available_focas_functions
    assert len(service.focas_function_params.get("cnc_rdparam", [])) > 0
