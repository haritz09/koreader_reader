from fastapi import APIRouter

from api.routes.progress import router as progress_router
from api.routes.ebooks import router as ebooks_router

api_router = APIRouter(prefix="/api")

api_router.include_router(progress_router, prefix="/v1")
api_router.include_router(ebooks_router, prefix="/v1")
