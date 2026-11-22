from types import SimpleNamespace

from app.mobile_route_registry import remove_shadowed_routes


def route(path, methods=None):
    values = {"path": path}
    if methods is not None:
        values["methods"] = set(methods)
    return SimpleNamespace(**values)


def router(*routes):
    return SimpleNamespace(routes=list(routes))


def route_signature(value):
    return [(item.path, frozenset(getattr(item, "methods", ()) or ())) for item in value.routes]


def test_exact_method_path_collision_is_removed():
    primary = router(route("/patients/{patient_id}/media/{media_id}/file", {"GET"}))
    candidate = router(
        route("/patients/{patient_id}/media/{media_id}/file", {"GET"}),
        route("/patients/{patient_id}/media/{media_id}/thumbnail", {"GET"}),
    )

    result = remove_shadowed_routes((primary,), candidate)

    assert result is candidate
    assert route_signature(candidate) == [
        ("/patients/{patient_id}/media/{media_id}/thumbnail", frozenset({"GET"}))
    ]


def test_same_path_with_a_different_method_is_not_a_collision():
    primary = router(route("/patients/{patient_id}/media", {"GET"}))
    candidate = router(route("/patients/{patient_id}/media", {"POST"}))

    remove_shadowed_routes((primary,), candidate)

    assert route_signature(candidate) == [
        ("/patients/{patient_id}/media", frozenset({"POST"}))
    ]


def test_multi_method_route_keeps_only_nonconflicting_methods():
    primary = router(route("/consultations/{case_id}", {"GET"}))
    candidate_route = route("/consultations/{case_id}", {"GET", "PATCH", "DELETE"})
    candidate = router(candidate_route)

    remove_shadowed_routes((primary,), candidate)

    assert route_signature(candidate) == [
        ("/consultations/{case_id}", frozenset({"PATCH", "DELETE"}))
    ]


def test_collisions_are_collected_from_every_primary_router():
    first = router(route("/analyses", {"GET"}))
    second = router(route("/patients/{patient_id}/media", {"POST"}))
    candidate = router(
        route("/analyses", {"GET"}),
        route("/patients/{patient_id}/media", {"POST"}),
        route("/patients/{patient_id}/media", {"GET"}),
    )

    remove_shadowed_routes((first, second), candidate)

    assert route_signature(candidate) == [
        ("/patients/{patient_id}/media", frozenset({"GET"}))
    ]


def test_methodless_routes_and_noncolliding_routes_are_preserved_and_repeatable():
    primary = router(route("/health", {"GET"}))
    socket_route = route("/ws/sync")
    candidate = router(socket_route, route("/health", {"POST"}), route("/ready", {"GET"}))

    remove_shadowed_routes((primary,), candidate)
    first = route_signature(candidate)
    remove_shadowed_routes((primary,), candidate)

    assert candidate.routes[0] is socket_route
    assert first == route_signature(candidate)
    assert first == [
        ("/ws/sync", frozenset()),
        ("/health", frozenset({"POST"})),
        ("/ready", frozenset({"GET"})),
    ]


def test_method_comparison_is_case_insensitive():
    primary = router(route("/health", {"get"}))
    candidate = router(route("/health", {"GET"}))

    remove_shadowed_routes((primary,), candidate)

    assert candidate.routes == []



def test_real_fastapi_multi_method_route_keeps_the_nonconflicting_openapi_operation():
    from fastapi import APIRouter, FastAPI

    primary = APIRouter()

    @primary.get("/registry-probe/{item_id}")
    def canonical_get(item_id: int):
        return {"source": "canonical", "id": item_id}

    candidate = APIRouter()

    @candidate.api_route("/registry-probe/{item_id}", methods=["GET", "PATCH"])
    def modern_adapter(item_id: int):
        return {"source": "adapter", "id": item_id}

    remove_shadowed_routes((primary,), candidate)

    app = FastAPI()
    app.include_router(primary)
    app.include_router(candidate)
    operations = app.openapi()["paths"]["/registry-probe/{item_id}"]

    assert set(operations) == {"get", "patch"}
    assert next(
        route for route in candidate.routes
        if getattr(route, "path", None) == "/registry-probe/{item_id}"
    ).methods == {"PATCH"}



def test_registered_clinical_media_routes_use_the_expected_private_handlers():
    # Other security tests temporarily replace app.main for isolated handler
    # tests. Verify production router mounting in a clean interpreter so this
    # integration contract is independent of pytest collection/order state.
    import os
    import subprocess
    import sys
    from pathlib import Path

    script = r"""
import inspect
from app import main
from app.mobile_api import router as primary_mobile_router
from app.mobile_modern_api_v3 import router as modern_mobile_router

def symbol(endpoint):
    endpoint = inspect.unwrap(endpoint)
    return (getattr(endpoint, "__module__", None),
            getattr(endpoint, "__qualname__", getattr(endpoint, "__name__", None)))

def registered(source_router, suffix, method):
    source = [
        route for route in source_router.routes
        if getattr(route, "path", "").rstrip("/").endswith(suffix.rstrip("/"))
        and method in (getattr(route, "methods", None) or set())
    ]
    assert len(source) == 1, (method, suffix, "source", len(source))
    expected = symbol(source[0].endpoint)
    matches = [
        route for route in main.app.routes
        if symbol(getattr(route, "endpoint", None)) == expected
        and method in (getattr(route, "methods", None) or set())
    ]
    media_routes = [
        (getattr(route, "path", None), sorted(getattr(route, "methods", None) or ()),
         symbol(getattr(route, "endpoint", None)))
        for route in main.app.routes
        if "media" in getattr(route, "path", "").lower()
    ]
    assert len(matches) == 1, (expected, method, suffix, media_routes)
    assert matches[0].path.rstrip("/").endswith(suffix.rstrip("/"))
    return matches[0]

media_list = registered(primary_mobile_router, "/patients/{patient_id}/media", "GET")
media_upload = registered(primary_mobile_router, "/patients/{patient_id}/media", "POST")
original_file = registered(primary_mobile_router, "/patients/{patient_id}/media/{media_id}/file", "GET")
thumbnail = registered(modern_mobile_router, "/patients/{patient_id}/media/{media_id}/thumbnail", "GET")
metadata = registered(modern_mobile_router, "/patients/{patient_id}/media/{media_id}", "GET")

assert media_list.endpoint.__module__ == "app.mobile_api"
assert media_list.endpoint.__name__ == "mobile_patient_media"
assert "_mobile_private_no_store(response)" in inspect.getsource(media_list.endpoint)
assert media_upload.endpoint.__module__ == "app.mobile_api"
assert media_upload.endpoint.__name__ == "mobile_patient_media_upload"
assert original_file.endpoint.__module__ == "app.mobile_api"
assert "current_media.file_path == file_path" in inspect.getsource(original_file.endpoint)
assert thumbnail.endpoint.__module__ == "app.mobile_modern_api_v3"
assert "current_media.file_path == file_path" in inspect.getsource(thumbnail.endpoint)
assert "headers = dict(_PRIVATE_CLINICAL_MEDIA_HEADERS)" in inspect.getsource(thumbnail.endpoint)
assert metadata.endpoint.__module__ == "app.mobile_modern_api_v3"
assert "response.headers.update(_PRIVATE_CLINICAL_MEDIA_HEADERS)" in inspect.getsource(metadata.endpoint)
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
