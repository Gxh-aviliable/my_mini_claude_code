import logging
import os
from contextlib import asynccontextmanager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from enterprise_agent.api.routes.auth import router as auth_router
from enterprise_agent.api.routes.chat import router as chat_router
from enterprise_agent.api.routes.chat import sessions_router
from enterprise_agent.config.settings import settings
from enterprise_agent.db.chroma import init_chroma
from enterprise_agent.db.mysql import close_db, init_db
from enterprise_agent.db.redis import close_redis


logger = logging.getLogger("enterprise_agent")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan - startup and shutdown"""
    # Startup
    # LangSmith tracing (optional — only enables if API key is configured)
    if settings.LANGSMITH_API_KEY:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.LANGSMITH_API_KEY
        os.environ["LANGCHAIN_PROJECT"] = settings.LANGSMITH_PROJECT
        logger.info("LangSmith tracing enabled (project: %s)", settings.LANGSMITH_PROJECT)

    logger.info("Initializing MySQL tables...")
    await init_db()
    logger.info("MySQL tables ready")

    logger.info("Initializing Chroma vector database (downloading embedding model on first run)...")
    init_chroma()
    logger.info("Chroma vector database ready")

    logger.info("Initializing Redis checkpointer...")
    from enterprise_agent.core.agent.graph import setup_checkpointer
    await setup_checkpointer()
    logger.info("Redis checkpointer ready")

    logger.info("Application startup complete")
    yield
    # Shutdown
    logger.info("Shutting down...")
    await close_db()
    await close_redis()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Enterprise-level multi-user AI Agent system with LangGraph",
    lifespan=lifespan
)

# CORS middleware
origins_str = settings.CORS_ORIGINS
if origins_str:
    origins = [o.strip() for o in origins_str.split(",") if o.strip()]
else:
    origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(sessions_router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all exception handler to prevent stack trace leaks."""
    logging.exception("Unhandled exception: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


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