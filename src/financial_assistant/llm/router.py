"""Deterministic routing. Frontier is never a fallback."""
from .model_registry import RoutingError, available, guard_egress, resolve_model


def route_model(models, route, selected, *, explicit_frontier=False, health=available):
    workspace = resolve_model(models, selected) if route != 'frontier' else None
    if route == 'frontier':
        if not explicit_frontier:
            raise RoutingError('explicit_required', 'Frontier comparison must be explicitly requested')
        candidates = [m for m in models if 'frontier' in m.roles]
    elif route == 'analysis':
        candidates = [workspace] if workspace and 'analysis' in workspace.roles else []
    elif route == 'interaction':
        candidates = [m for m in models if 'interaction' in m.roles and m.locality == 'local']
        if workspace and workspace.locality == 'local' and 'analysis' in workspace.roles and workspace not in candidates:
            candidates.append(workspace)
    else:
        raise RoutingError('invalid_route', 'Unknown route')
    if not candidates:
        raise RoutingError('not_configured', f'No eligible {route} model configured')
    for model in candidates:
        guard_egress(model)
        if health(model):
            return model
    raise RoutingError('unavailable', f'Configured {route} model is unavailable')
