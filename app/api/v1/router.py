"""API v1 router composition."""

from fastapi import APIRouter
from app.api.v1.endpoints import health, papers

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(papers.router, prefix="/papers", tags=["Papers"])

