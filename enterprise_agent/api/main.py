from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from enterprise_agent.config.settings import settings
from enterprise_agent.db.mysql import close_db
from enterprise_agent.db.redis import close_redis
from enterprise_agent.db.chroma import init_chroma
from enterprise_agent.api.routes.auth import router as auth_router
from enterprise_agent.api.routes.chat import router as chat_router
from enterprise_agent.api.routes.chat import sessions_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown"""
    # Startup
    # Initialize Chroma vector database
    init_chroma()
    yield
    # Shutdown
    await close_db()
    await close_redis()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Enterprise-level multi-user AI Agent system with LangGraph",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(sessions_router)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "name": settings.APP_NAME
    }


@app.get("/")
async def root():
    """Root endpoint - redirect to docs"""
    return {
        "message": "Enterprise Agent API",
        "docs": "/docs",
        "health": "/health"
    }


def run():
    """Run server with uvicorn"""
    import uvicorn
    uvicorn.run(
        "enterprise_agent.api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG
    )


if __name__ == "__main__":
    run()