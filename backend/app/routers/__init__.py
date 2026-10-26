from .informes import router as informes_router
from .tarifas import router as tarifas_router
from .tickets import router as tickets_router

__all__ = ["informes_router", "tarifas_router", "tickets_router"]
