from app import ProductionCellService


def test_select_product_updates_cnc_and_robot():
    service = ProductionCellService()
    state = service.select_product("P1002")
    assert state["active_product_id"] == "P1002"
    assert state["cnc"]["selected_program"] == "O2801"


def test_shelves_are_numbered_1_to_50():
    service = ProductionCellService()
    assert service.shelves[0] == "1"
    assert service.shelves[-1] == "50"
    assert len(service.shelves) == 50


def test_layout_has_xyz_coordinates_and_same_part_type_on_shelf():
    service = ProductionCellService()
    layout = service.get_shelf_layout("1")
    assert layout["shelf_width_mm"] == 2000
    assert layout["shelf_depth_mm"] == 800
    assert layout["placements"][0]["x_mm"] > 0
    assert layout["placements"][0]["y_mm"] > 0
    assert layout["placements"][0]["z_mm"] > 0
    part_types = {p["part_type_id"] for p in layout["placements"]}
    assert len(part_types) == 1


def test_template_validation_rejects_mixed_part_types():
    service = ProductionCellService()
    try:
        service.upsert_layout_template(
            "bad",
            [
                {"part_type_id": "PT-RAW-120", "x_mm": 200, "y_mm": 200, "z_mm": 95},
                {"part_type_id": "PT-INP-080", "x_mm": 600, "y_mm": 200, "z_mm": 55},
            ],
        )
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "samme type" in str(exc)


def test_apply_template_to_shelf_changes_assignment():
    service = ProductionCellService()
    service.upsert_layout_template(
        "mini",
        [
            {"part_type_id": "PT-INP-080", "x_mm": 120, "y_mm": 120, "z_mm": 55},
            {"part_type_id": "PT-INP-080", "x_mm": 220, "y_mm": 120, "z_mm": 55},
        ],
    )
    layout = service.apply_template_to_shelf("2", "mini")
    assert layout["template_name"] == "mini"
    assert layout["part_type_id"] == "PT-INP-080"
    assert len(layout["placements"]) == 2
