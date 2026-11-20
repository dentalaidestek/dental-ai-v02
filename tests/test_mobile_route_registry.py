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
