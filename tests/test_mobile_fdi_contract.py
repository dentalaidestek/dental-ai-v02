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
