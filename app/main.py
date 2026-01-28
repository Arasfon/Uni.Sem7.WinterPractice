from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes.photo import router as photo_router
from app.api.routes.report import router as report_router
from app.api.routes.stream import router as stream_router
from app.api.routes.video import router as video_router
from app.core.config import ensure_dirs, project_root, settings
from app.state.stream_state import get_stream_pipeline
from app.storage.history_db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_dirs()
    init_db()

    yield

    get_stream_pipeline().stop()


app = FastAPI(
    title="Bicycle Counter",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(photo_router)
app.include_router(video_router)
app.include_router(stream_router)
app.include_router(report_router)

static_dir = project_root() / "app" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

hls_dir = project_root() / settings.stream_hls_dir
hls_dir.mkdir(parents=True, exist_ok=True)
app.mount("/hls", StaticFiles(directory=str(hls_dir)), name="hls")


@app.get("/", response_class=HTMLResponse)
def root():
    index = project_root() / "app" / "static" / "index.html"
    if index.exists():
        return FileResponse(index)
    return HTMLResponse("<h2>static/index.html not found</h2>")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": settings.model_name,
        "device": settings.device,
    }


@app.get("/photo")
def photo_page():
    return FileResponse(static_dir / "photo.html")


@app.get("/video")
def video_page():
    return FileResponse(static_dir / "video.html")


@app.get("/stream")
def stream_page():
    return FileResponse(static_dir / "stream.html")
