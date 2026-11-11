"""Regression checks for the FDI tooth-number contract shared by mobile clinical endpoints."""
import ast
from pathlib import Path


SOURCE = Path(__file__).resolve().parents[1] / "app" / "mobile_api.py"


def _load_validator():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_valid_fdi_tooth_number"]
    assert len(functions) == 1
    namespace = {}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace["_valid_fdi_tooth_number"]


def test_fdi_all_and_only_52_valid_numbers():
    valid = {f"{q}{n}" for q in "1234" for n in "12345678"} | {f"{q}{n}" for q in "5678" for n in "12345"}
    validator = _load_validator()
    assert len(valid) == 52
    for number in (f"{a}{b}" for a in "0123456789" for b in "0123456789"):
        assert validator(number) is (number in valid), number
    for number in ("", "1", "111", "55 ", " 55", "A1", "59", "49", "00"):
        assert validator(number) is False


def test_mobile_clinical_routes_use_shared_fdi_validator():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    routes = ("mobile_update_tooth", "mobile_create_treatment", "mobile_update_treatment")
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in routes:
            assert any(isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == "_valid_fdi_tooth_number" for call in ast.walk(node)), node.name


def test_tooth_updates_do_not_create_completed_treatments():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    update = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "mobile_update_tooth")
    assert not any(isinstance(item, ast.Call) and isinstance(item.func, ast.Name) and item.func.id == "Treatment" for item in ast.walk(update))


def test_tooth_surface_updates_validate_duplicates_and_ownership():
    source_text = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source_text)
    update = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "mobile_update_tooth")
    source = ast.get_source_segment(source_text, update)
    assert "len(set(payload.surfaces))" in source
    assert "patient.owner_user_id != user.id" in source
    assert "for surface_name in requested_surfaces" in source
    assert "session.commit()" in source


WEB_SOURCE = Path(__file__).resolve().parents[1] / "app" / "main.py"


def test_web_tooth_chart_does_not_invent_treatment_history():
    tree = ast.parse(WEB_SOURCE.read_text(encoding="utf-8"))
    update = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "update_tooth_status")
    assert not any(isinstance(item, ast.Call) and isinstance(item.func, ast.Name) and item.func.id == "Treatment" for item in ast.walk(update))


def test_web_tooth_chart_validates_fdi_and_note_length():
    source = WEB_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    update = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "update_tooth_status")
    route = ast.get_source_segment(source, update)
    assert 'tooth_number[0] in "1234"' in route
    assert 'tooth_number[0] in "5678"' in route
    assert "len(note) > 2000" in route
    assert "Geçersiz diş yüzeyi" in route
