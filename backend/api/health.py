from fastapi import APIRouter
from typing import Dict

router = APIRouter(tags=["Health"])

@router.get("/health/live")
async def health_live() -> Dict[str, str]:
    return {"status": "alive"}

@router.get("/health/ready")
async def health_ready() -> Dict[str, str]:
    # Future: check database, redis, minio connectivity here
    return {"status": "ready"}
