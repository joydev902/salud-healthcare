from fastapi import APIRouter

from app.api.v1 import admin, auth, health, imports, members, opportunities, reference

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(imports.router)
api_router.include_router(reference.router)
api_router.include_router(members.router)
api_router.include_router(opportunities.router)
api_router.include_router(admin.router)
