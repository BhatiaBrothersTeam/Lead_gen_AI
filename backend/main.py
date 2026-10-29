import os
import logging
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Load environment variables from .env, then .env.local (matching the Vite
# frontend's own cascade, where a .local file wins) for SSO-related secrets.
load_dotenv()
load_dotenv(".env.local", override=True)

from backend.database.connection import init_db_pool, close_db_pool
from backend.services.database import initialize_tables
from backend.api.routes.leads import router as leads_router
from backend.api.routes.auth import router as auth_router

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize DB Pool and tables
    dsn = os.getenv("DATABASE_URL", "postgres://postgres:root@localhost:5432/Lead_DB")
    logger.info("Initializing PostgreSQL pool...")
    await init_db_pool(dsn=dsn)
    
    logger.info("Initializing database schemas...")
    try:
        await initialize_tables()
        logger.info("Database schemas initialized successfully.")
    except Exception as err:
        logger.error(f"Error initializing database schemas: {err}")
        
    yield
    
    # Shutdown: Close DB Pool
    logger.info("Closing PostgreSQL pool...")
    await close_db_pool()
    logger.info("PostgreSQL pool closed.")

app = FastAPI(
    title="LeadGen AI - FastAPI Backend",
    version="2.4",
    lifespan=lifespan
)

# CORS configuration
# The Staff Portal's origin (PORTAL_URL) is added so its "Sign out of all
# apps" button can call our /api/auth/logout cross-origin with credentials.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://leadgenerationagent.vercel.app",
        "https://lead-generation-agent-two.vercel.app",
        "http://localhost:5173",
        os.getenv("PORTAL_URL", "http://localhost:3000"),
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include B2B scanner routing APIs
app.include_router(leads_router)
app.include_router(auth_router)

# Healthcheck
@app.get("/health")
async def health():
    return {"status": "ok", "service": "LeadGen AI Backend"}

# Production client bundle serving logic (Vite dist)
# Check if static dist files exist, and mount them if so
dist_path = os.path.join(os.getcwd(), "dist")
if os.path.exists(dist_path):
    logger.info(f"Vite static distribution path found at: {dist_path}. Mounting static files.")
    
    # Standard static files mount (CSS, JS, images, etc.)
    # Mount at /assets, /static, etc., but serve index.html via catch_all for React Router compatibility
    app.mount("/assets", StaticFiles(directory=os.path.join(dist_path, "assets")), name="assets")
    
    # Serving single page application index fallback on root or any frontend route
    @app.get("/{catchall:path}")
    async def catch_all(catchall: str):
        # Ignore API routes to let them fall back to 404 naturally
        if catchall.startswith("api/") or catchall == "api" or catchall == "health":
            raise HTTPException(status_code=404, detail="Not Found")
            
        index_file = os.path.join(dist_path, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Index file not found")
else:
    logger.info("Vite distribution path not found. Running in API-only dev server mode.")
