"""Method-aware route deduplication for the canonical mobile API registry.

FastAPI may keep included APIRouter objects lazy. Compare source routers before
mounting, and remove only the HTTP method/path pairs already owned by an
earlier router. Multi-method routes retain any non-conflicting methods.
"""


def remove_shadowed_routes(primary_routers, candidate_router):
    """Remove method/path collisions from a candidate router in place.

    route.methods is a set on FastAPI APIRoute. Routes without an HTTP
    method set (for example WebSocket routes) are left untouched.
    """
    mounted_methods = {}
    for primary_router in primary_routers:
        for route in getattr(primary_router, "routes", ()):
            path = getattr(route, "path", None)
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
        path = getattr(route, "path", None)
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
    """Mount routes added to a router after an earlier circular import include.

    main and the native adapters import each other for shared models and auth
    helpers. If an adapter is first imported while main is still initializing,
    FastAPI may include only the routes present at that moment. Reconcile by
    prefixed path, HTTP method and endpoint source symbol, adding only missing
    operations and refusing conflicting owners.
    """
    from copy import copy
    from fastapi import APIRouter
    import inspect

    prefix = getattr(source_router, "prefix", "") or ""

    def endpoint_symbol(endpoint):
        endpoint = inspect.unwrap(endpoint)
        return (
            getattr(endpoint, "__module__", None),
            getattr(endpoint, "__qualname__", getattr(endpoint, "__name__", None)),
        )

    def full_path(route):
        path = getattr(route, "path", None)
        if not isinstance(path, str):
            path = getattr(route, "path_format", None)
        if not isinstance(path, str):
            return None
        if prefix and not path.startswith(prefix.rstrip("/") + "/"):
            return prefix.rstrip("/") + (path if path.startswith("/") else "/" + path)
        return path

    existing = {}
    for route in getattr(app, "routes", ()):
        path = getattr(route, "path", None)
        if not isinstance(path, str):
            continue
        methods = getattr(route, "methods", None) or ()
        symbol = endpoint_symbol(getattr(route, "endpoint", None))
        if methods:
            for method in methods:
                existing[(path, str(method).upper())] = symbol
        else:
            existing[(path, None)] = symbol

    missing = []
    for route in getattr(source_router, "routes", ()):
        path = full_path(route)
        if path is None:
            continue
        methods = getattr(route, "methods", None) or ()
        symbol = endpoint_symbol(getattr(route, "endpoint", None))
        if methods:
            remaining = set()
            for method in methods:
                key = (path, str(method).upper())
                owner = existing.get(key)
                if owner is None:
                    remaining.add(method)
                elif owner != symbol:
                    raise RuntimeError(
                        f"mobile route ownership conflict for {str(method).upper()} {path}: "
                        f"{owner[0]}.{owner[1]} vs {symbol[0]}.{symbol[1]}"
                    )
            if not remaining:
                continue
            cloned = copy(route)
            cloned.methods = remaining
            missing.append(cloned)
            for method in remaining:
                existing[(path, str(method).upper())] = symbol
        else:
            key = (path, None)
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
