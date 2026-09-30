from fastapi import APIRouter

from api.routes.ebooks import router as ebooks_router
from api.routes.graph import router as graph_router
from api.routes.progress import router as progress_router

api_router = APIRouter(prefix="/api")

api_router.include_router(progress_router, prefix="/v1")
api_router.include_router(ebooks_router, prefix="/v1")
api_router.include_router(graph_router, prefix="/v1")
