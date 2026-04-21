"""WebSocket route — real-time event streaming.

The WebSocket endpoint is registered differently from regular HTTP routes
(no ``APIRouter``). The ``register_routes`` helper skips this module via a
``hasattr(mod, "router")`` check.

Implementation deferred to KUI-35.
"""
