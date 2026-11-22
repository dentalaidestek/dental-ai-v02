"""Regression tests for the canonical mobile router's circular-import order."""

import ast
import inspect
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read_tree(relative_path: str):
    source = (ROOT / relative_path).read_text(encoding="utf-8")
    return ast.parse(source, filename=relative_path)


def _call_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def test_mobile_api_does_not_mount_or_reconcile_main_during_module_import():
    tree = _read_tree("app/mobile_api.py")

    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            imported_main = node.module == "app" and any(
                alias.name == "main" for alias in node.names
            )
            imported_reconciler = node.module == "app.mobile_route_registry" and any(
                alias.name == "include_missing_routes" for alias in node.names
            )
            assert not imported_main, (
                "mobile_api must not import app.main at module scope: main imports "
                "mobile_api.router and has not mounted it until that import returns"
            )
            assert not imported_reconciler, (
                "mobile_api must not import the route reconciler at module scope"
            )
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            assert _call_name(node.value.func) != "_include_missing_mobile_routes", (
                "mobile_api must not mount its own router before main.include_router"
            )


def test_main_mounts_the_fully_initialized_mobile_router_exactly_once():
    tree = _read_tree("app/main.py")
    imports = [
        node
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module == "app.mobile_api"
        and any(
            alias.name == "router" and alias.asname == "mobile_router"
            for alias in node.names
        )
    ]
    mounts = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "app"
        and node.func.attr == "include_router"
        and node.args
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "mobile_router"
    ]

    assert len(imports) == 1
    assert len(mounts) == 1
    assert mounts[0].lineno > imports[0].lineno


def test_clinical_media_gallery_handler_is_effectively_mounted_once():
    from app import main
    from app.mobile_api import router as mobile_router
    from app.mobile_route_registry import iter_registered_routes

    def symbol(endpoint):
        endpoint = inspect.unwrap(endpoint)
        return (
            getattr(endpoint, "__module__", None),
            getattr(endpoint, "__qualname__", getattr(endpoint, "__name__", None)),
        )

    expected = [
        route
        for route in iter_registered_routes(mobile_router.routes)
        if getattr(route, "path", getattr(route, "path_format", "")).rstrip("/")
        == "/api/mobile/v1/patients/{patient_id}/media"
        and "GET" in (getattr(route, "methods", None) or set())
    ]
    assert len(expected) == 1
    owner = symbol(expected[0].endpoint)

    mounted = [
        route
        for route in iter_registered_routes(main.app.routes)
        if symbol(getattr(route, "endpoint", None)) == owner
        and "GET" in (getattr(route, "methods", None) or set())
    ]
    assert len(mounted) == 1, (
        "the private patient-media gallery handler must be mounted exactly once; "
        "an import-time reconciliation plus main.include_router creates duplicate "
        "effective routes"
    )
