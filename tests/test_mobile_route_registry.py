from types import SimpleNamespace

from app.mobile_route_registry import include_missing_routes, iter_registered_routes, remove_shadowed_routes


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
    import inspect

    from app import main
    from app.mobile_api import router as primary_mobile_router
    from app.mobile_modern_api_v3 import router as modern_mobile_router

    def registered(source_router, suffix, method):
        # APIRouter prefixes are represented differently across FastAPI
        # versions: some route objects expose the prefixed path before mount,
        # while others apply it during include_router(). Resolve the canonical
        # source endpoint first, then assert that this exact callable is mounted
        # once on the application. This tests route ownership without guessing
        # how the framework materializes the prefix.
        def route_path(route):
            path = getattr(route, "path", None)
            if not isinstance(path, str):
                path = getattr(route, "path_format", None)
            return path if isinstance(path, str) else ""

        normalized_suffix = suffix.rstrip("/")
        source_matches = [
            route for route in iter_registered_routes(source_router.routes)
            if route_path(route).rstrip("/").endswith(normalized_suffix)
            and method in (getattr(route, "methods", None) or set())
        ]
        assert len(source_matches) == 1, (
            f"expected one source {method} route ending in {suffix}, found {len(source_matches)}"
        )
        source = source_matches[0]
        def endpoint_symbol(endpoint):
            # FastAPI can clone APIRoute objects while including routers. The
            # callable object identity is not a stable registration contract;
            # its fully-qualified source symbol is. Unwrap decorators before
            # comparing so instrumentation does not hide the canonical owner.
            endpoint = inspect.unwrap(endpoint)
            return (
                getattr(endpoint, "__module__", None),
                getattr(endpoint, "__qualname__", getattr(endpoint, "__name__", None)),
            )

        expected_symbol = endpoint_symbol(source.endpoint)
        matches = [
            route for route in iter_registered_routes(main.app.routes)
            if endpoint_symbol(getattr(route, "endpoint", None)) == expected_symbol
            and method in (getattr(route, "methods", None) or set())
        ]
        app_media_routes = [
            (
                route_path(route),
                sorted(getattr(route, "methods", None) or ()),
                endpoint_symbol(getattr(route, "endpoint", None)),
            )
            for route in iter_registered_routes(main.app.routes)
            if "media" in route_path(route).lower()
            and method in (getattr(route, "methods", None) or set())
        ]
        assert len(matches) == 1, (
            f"expected source endpoint {expected_symbol[0]}.{expected_symbol[1]} "
            f"to be mounted once, found {len(matches)}; app_media_routes={app_media_routes}"
        )
        assert route_path(matches[0]).rstrip("/").endswith(normalized_suffix), (
            f"mounted endpoint path {route_path(matches[0])!r} does not end with {normalized_suffix!r}"
        )
        return matches[0]

    # The primary router owns both the cache-private GET gallery and the
    # receipt-aware POST upload. The modern router's duplicate GET/POST
    # adapters must be removed by method-aware route deduplication.
    media_list = registered(primary_mobile_router, "/patients/{patient_id}/media", "GET")
    assert not any(
        route_path(route).rstrip("/").endswith("/patients/{patient_id}/media")
        and "GET" in (getattr(route, "methods", None) or set())
        for route in iter_registered_routes(modern_mobile_router.routes)
    ), "the primary GET gallery must shadow the legacy v3 GET adapter"
    media_upload = registered(primary_mobile_router, "/patients/{patient_id}/media", "POST")
    assert not any(
        route_path(route).rstrip("/").endswith("/patients/{patient_id}/media")
        and "POST" in (getattr(route, "methods", None) or set())
        for route in iter_registered_routes(modern_mobile_router.routes)
    ), "the receipt-aware primary POST must shadow the legacy v3 upload adapter"
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


def test_include_missing_routes_reconciles_a_router_that_grows_after_initial_mount():
    from fastapi import APIRouter, FastAPI

    app = FastAPI()
    source = APIRouter(prefix="/api/mobile/v1")

    @source.get("/initial")
    def initial_route():
        return {"source": "initial"}

    app.include_router(source)

    @source.get("/late")
    def late_route():
        return {"source": "late"}

    # FastAPI 0.141 uses a lazy include: the original router remains live,
    # so the late route is already effective and must not be mounted twice.
    assert include_missing_routes(app, source) == 0
    assert include_missing_routes(app, source) == 0
    mounted = [
        (
            getattr(route, "path", getattr(route, "path_format", None)),
            method,
        )
        for route in iter_registered_routes(app.routes)
        for method in (getattr(route, "methods", None) or ())
    ]
    assert mounted.count(("/api/mobile/v1/initial", "GET")) == 1
    assert mounted.count(("/api/mobile/v1/late", "GET")) == 1


def test_include_missing_routes_rejects_a_different_existing_endpoint_owner():
    from fastapi import APIRouter, FastAPI
    import pytest

    app = FastAPI()

    def existing():
        return {"source": "existing"}

    def conflicting():
        return {"source": "conflicting"}

    app.add_api_route("/api/mobile/v1/conflict", existing, methods=["GET"])
    source = APIRouter(prefix="/api/mobile/v1")
    source.add_api_route("/conflict", conflicting, methods=["GET"])

    with pytest.raises(RuntimeError, match="mobile route ownership conflict"):
        include_missing_routes(app, source)



def test_include_missing_routes_flattens_nested_lazy_router_prefixes():
    from fastapi import APIRouter, FastAPI

    app = FastAPI()
    root = APIRouter(prefix="/api/mobile/v1")
    patients = APIRouter(prefix="/patients")

    @patients.get("/{patient_id}/media")
    def patient_media(patient_id: int):
        return {"patient_id": patient_id}

    root.include_router(patients)
    app.include_router(root)

    assert include_missing_routes(app, root) == 0
    matches = [
        route for route in iter_registered_routes(app.routes)
        if getattr(route, "path", getattr(route, "path_format", None))
        == "/api/mobile/v1/patients/{patient_id}/media"
        and "GET" in (getattr(route, "methods", None) or set())
    ]
    assert len(matches) == 1
    assert matches[0].endpoint.__name__ == "patient_media"


def test_remove_shadowed_routes_normalizes_nested_primary_prefixes():
    from fastapi import APIRouter

    primary = APIRouter(prefix="/api/mobile/v1")
    patients = APIRouter(prefix="/patients")

    @patients.get("/{patient_id}/media")
    def canonical_media(patient_id: int):
        return {"owner": "canonical"}

    primary.include_router(patients)
    candidate = APIRouter(prefix="/api/mobile/v1")

    @candidate.api_route("/patients/{patient_id}/media", methods=["GET", "POST"])
    def adapter_media(patient_id: int):
        return {"owner": "adapter"}

    remove_shadowed_routes((primary,), candidate)

    assert route_signature(candidate) == [
        ("/patients/{patient_id}/media", frozenset({"POST"}))
    ]


def test_include_missing_routes_fails_closed_on_conflicting_existing_owners():
    from fastapi import APIRouter, FastAPI
    import pytest

    app = FastAPI()

    def first_owner():
        return {"owner": "first"}

    def second_owner():
        return {"owner": "second"}

    app.add_api_route("/api/mobile/v1/conflict", first_owner, methods=["GET"])
    app.add_api_route("/api/mobile/v1/conflict", second_owner, methods=["GET"])
    source = APIRouter(prefix="/api/mobile/v1")
    source.add_api_route("/new", lambda: {"ok": True}, methods=["GET"])

    with pytest.raises(RuntimeError, match="mobile route ownership conflict"):
        include_missing_routes(app, source)


def test_include_missing_routes_fails_closed_on_duplicate_same_owner_registration():
    from fastapi import APIRouter, FastAPI
    import pytest

    app = FastAPI()

    def shared_owner():
        return {"owner": "shared"}

    app.add_api_route("/api/mobile/v1/duplicate", shared_owner, methods=["GET"])
    app.add_api_route("/api/mobile/v1/duplicate", shared_owner, methods=["GET"])
    source = APIRouter(prefix="/api/mobile/v1")
    source.add_api_route("/new", lambda: {"ok": True}, methods=["GET"])

    with pytest.raises(RuntimeError, match="duplicate mobile route registration"):
        include_missing_routes(app, source)
