"""AI Multimodal Flood Disaster Response DataLake (FDR) — India Scale.

FastAPI application entry point. Bootstraps the orchestrator and registers
the REST + WebSocket API endpoints.
"""
import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.api.endpoints import router
from app.api.history import router as history_router
from app.api.official import router as official_router
from app.api.citizen import router as citizen_router
from app.api.news import router as news_router
from app.api.places import router as places_router
from app.api.ai import router as ai_router
from app.orchestrator import orchestrator, background_live_data

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "Full-stack near-real-time AI Multimodal Flood Disaster Response DataLake "
        "covering all of India, integrating IMD, CWC, ISRO, NDMA, and citizen data sources."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.include_router(history_router, prefix="/api")
app.include_router(official_router, prefix="/api")
app.include_router(citizen_router, prefix="/api")
app.include_router(news_router, prefix="/api")
app.include_router(places_router, prefix="/api")
app.include_router(ai_router, prefix="/api")


@app.on_event("startup")
async def on_startup():
    await orchestrator.bootstrap()
    asyncio.create_task(background_live_data(interval_seconds=settings.LIVE_REFRESH_SECONDS))


@app.get("/")
async def root():
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs",
        "api": "/api",
        "regional_score": orchestrator._current.get("regional", {}).get("score", 0),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)