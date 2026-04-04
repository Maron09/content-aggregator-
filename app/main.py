import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.routes.search import router as search_router
from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.info("Content Aggregator API starting up")
    yield
    # Shutdown
    logging.info("Content Aggregator API shutting down")

app = FastAPI(
    title="Content Aggregator API",
    description="Curated media search for video editors",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",          
        "https://content-aggregator-frontend-three.vercel.app/",    
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(search_router)

@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}