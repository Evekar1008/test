from app import ProductionCellService


def test_shelves_are_numbered_1_to_50():
    service = ProductionCellService()
    assert service.shelves[0] == "1"
    assert service.shelves[-1] == "50"


def test_active_shelf_layout_tracks_simulation_step():
    service = ProductionCellService()
    service.simulation_step()
    assert service.simulation["active_shelf"] == "1"
    service.simulation_step()
    assert service.simulation["active_shelf"] == "2"


def test_start_production_quantity_and_complete():
    service = ProductionCellService()
    order = service.start_production("PT-RAW-120", "quantity", 2)
    assert order["target_qty"] == 2
    service.complete_one_part()
    service.complete_one_part()
    assert service.production_order["active"] is False


def test_start_production_all_uses_part_quantity_total():
    service = ProductionCellService()
    order = service.start_production("PT-RAW-280", "all", None)
    assert order["target_qty"] == 22


def test_focas_and_lift_commands_return_response():
    service = ProductionCellService()
    focas = service.call_cnc_focas("read_status", {})
    lift = service.call_lift_rest("move_to_shelf", {"shelf": "7"})
    assert "response" in focas
    assert lift["response"]["moved_to"] == "7"
