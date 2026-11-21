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
