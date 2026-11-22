"""Method-aware route deduplication for the canonical mobile API registry.

FastAPI 0.141 keeps included routers lazy. Inspect their effective route
contexts instead of assuming app.routes is a flat list of APIRoute objects.
This keeps route ownership checks correct across supported FastAPI versions
and prevents a second reconciliation pass from mounting duplicates.
"""


def iter_registered_routes(routes):
    """Yield effective routes, recursively expanding FastAPI lazy includes.

    Older FastAPI releases expose copied APIRoute objects directly. Newer
    releases expose an included-router object whose public routing behavior is
    represented by effective_candidates(). Use capability detection rather
    than importing FastAPI's private class so this helper also works with the
    older, eagerly-expanded route list.
    """
    visited_includes = set()

    def walk(items):
        for route in items or ():
            effective_candidates = getattr(route, "effective_candidates", None)
            if callable(effective_candidates):
                marker = id(route)
                if marker in visited_includes:
                    continue
                visited_includes.add(marker)
                yield from walk(effective_candidates())
                low_priority = getattr(route, "effective_low_priority_routes", None)
                if callable(low_priority):
                    yield from walk(low_priority())
                continue
            yield route

    yield from walk(routes)


def _route_path(route):
    path = getattr(route, "path", None)
    if not isinstance(path, str):
        path = getattr(route, "path_format", None)
    return path if isinstance(path, str) else None


def _endpoint_symbol(endpoint):
    import inspect

    endpoint = inspect.unwrap(endpoint)
    return (
        getattr(endpoint, "__module__", None),
        getattr(endpoint, "__qualname__", getattr(endpoint, "__name__", None)),
    )


def remove_shadowed_routes(primary_routers, candidate_router):
    """Remove method/path collisions from a candidate router in place.

    route.methods is a set on FastAPI APIRoute. Routes without an HTTP
    method set (for example WebSocket routes) are left untouched.
    """
    mounted_methods = {}
    for primary_router in primary_routers:
        for route in iter_registered_routes(getattr(primary_router, "routes", ())):
            path = _route_path(route)
            methods = getattr(route, "methods", None)
            if not isinstance(path, str) or not methods:
                continue
            mounted_methods.setdefault(path, set()).update(
                str(method).upper() for method in methods if method
            )

    routes = getattr(candidate_router, "routes", None)
    if routes is None:
        return candidate_router

    kept = []
    for route in routes:
        path = _route_path(route)
        methods = getattr(route, "methods", None)
        if not isinstance(path, str) or not methods:
            kept.append(route)
            continue

        original_methods = set(methods)
        remaining_methods = {
            method for method in original_methods
            if str(method).upper() not in mounted_methods.get(path, set())
        }
        if not remaining_methods:
            continue
        if remaining_methods != original_methods:
            route.methods = remaining_methods
        kept.append(route)

    routes[:] = kept
    return candidate_router


def include_missing_routes(app, source_router):
    """Mount routes added after an earlier include, without duplicate owners.

    FastAPI versions with lazy includes automatically expose routes added to
    the original router. Older versions snapshot the route list at include
    time. Flatten effective routes first so this function is idempotent in
    both implementations and fails closed if an existing path/method already
    has a different endpoint owner.
    """
    from copy import copy
    from fastapi import APIRouter

    prefix = getattr(source_router, "prefix", "") or ""

    def full_path(route):
        path = _route_path(route)
        if path is None:
            return None
        normalized_prefix = prefix.rstrip("/")
        if not normalized_prefix:
            return path
        if path == normalized_prefix or path.startswith(normalized_prefix + "/"):
            return path
        return normalized_prefix + (path if path.startswith("/") else "/" + path)

    existing = {}

    def remember(key, symbol):
        owner = existing.get(key)
        if owner is not None and owner != symbol:
            method, path = key
            label = f"{method} {path}" if method else path
            raise RuntimeError(
                f"mobile route ownership conflict for {label}: "
                f"{owner[0]}.{owner[1]} vs {symbol[0]}.{symbol[1]}"
            )
        existing[key] = symbol

    for route in iter_registered_routes(getattr(app, "routes", ())):
        path = _route_path(route)
        if path is None:
            continue
        methods = getattr(route, "methods", None) or ()
        symbol = _endpoint_symbol(getattr(route, "endpoint", None))
        if methods:
            for method in methods:
                remember((str(method).upper(), path), symbol)
        else:
            remember((None, path), symbol)

    missing = []
    for route in iter_registered_routes(getattr(source_router, "routes", ())):
        path = full_path(route)
        if path is None:
            continue
        methods = getattr(route, "methods", None) or ()
        symbol = _endpoint_symbol(getattr(route, "endpoint", None))
        if methods:
            remaining = set()
            for method in methods:
                normalized_method = str(method).upper()
                key = (normalized_method, path)
                owner = existing.get(key)
                if owner is None:
                    remaining.add(method)
                elif owner != symbol:
                    raise RuntimeError(
                        f"mobile route ownership conflict for {normalized_method} {path}: "
                        f"{owner[0]}.{owner[1]} vs {symbol[0]}.{symbol[1]}"
                    )
            if not remaining:
                continue
            cloned = copy(route)
            cloned.methods = remaining
            missing.append(cloned)
            for method in remaining:
                existing[(str(method).upper(), path)] = symbol
        else:
            key = (None, path)
            owner = existing.get(key)
            if owner is not None:
                if owner != symbol:
                    raise RuntimeError(
                        f"mobile route ownership conflict for {path}: "
                        f"{owner[0]}.{owner[1]} vs {symbol[0]}.{symbol[1]}"
                    )
                continue
            missing.append(copy(route))
            existing[key] = symbol

    if not missing:
        return 0

    target = APIRouter(prefix=prefix)
    target.routes.extend(missing)
    app.include_router(target)
    return len(missing)
