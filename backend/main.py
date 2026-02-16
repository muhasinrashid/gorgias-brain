from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from contextlib import asynccontextmanager
from backend.database import engine, Base
from backend.routers import ingest, inference, audit
from backend.config import get_settings

# Note: Production migration should be handled by Alembic, not create_all
# For local SQLite testing, we auto-create tables:
import os
if os.getenv("DATABASE_URL", "").startswith("sqlite"):
    Base.metadata.create_all(bind=engine)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load resources
    print("Starting Universal Support Brain API...")
    yield
    print("Shutting down...")

settings = get_settings()

app = FastAPI(title=settings.PROJECT_NAME, version=settings.VERSION, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ingest.router, prefix="/ingest", tags=["Ingestion"])
app.include_router(inference.router, prefix="/v1", tags=["Inference"])
app.include_router(audit.router, prefix="/audit", tags=["Audit"])

@app.get("/")
def read_root():
    return {"message": "Universal Support Brain is active."}

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
