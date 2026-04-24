from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from app.database import init_db
from app.routers import api, web
import os

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    os.makedirs("uploads", exist_ok=True)
    os.makedirs("exports", exist_ok=True)
    os.makedirs("data", exist_ok=True)
    yield

app = FastAPI(title="ZATCA Invoice OCR Portal", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.include_router(web.router)
app.include_router(api.router)

@app.get("/health")
async def health():
    return {"status": "ok"}
