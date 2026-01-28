from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import settings
from app.state.stream_state import get_stream_pipeline

router = APIRouter(prefix="/api/stream", tags=["stream"])


class StreamStartRequest(BaseModel):
    input_url: str = Field(..., min_length=3, description="RTSP URL or any FFmpeg-readable input URL")


class StreamStatusResponse(BaseModel):
    running: bool
    input_url: str | None
    hls_url: str
    started_at: float | None
    last_update_ts: float | None
    last_count: int
    frames_out: int
    error: str | None


@router.post("/start", response_model=StreamStatusResponse)
def start_stream(req: StreamStartRequest) -> StreamStatusResponse:
    pipeline = get_stream_pipeline()
    pipeline.start(req.input_url)
    st = pipeline.status()

    return StreamStatusResponse(
        running=st.running,
        input_url=st.input_url,
        hls_url=f"/hls/{settings.stream_playlist}",
        started_at=st.started_at,
        last_update_ts=st.last_update_ts,
        last_count=st.last_count,
        frames_out=st.frames_out,
        error=st.error,
    )


@router.post("/stop", response_model=StreamStatusResponse)
def stop_stream() -> StreamStatusResponse:
    pipeline = get_stream_pipeline()
    pipeline.stop()
    st = pipeline.status()

    return StreamStatusResponse(
        running=st.running,
        input_url=st.input_url,
        hls_url=f"/hls/{settings.stream_playlist}",
        started_at=st.started_at,
        last_update_ts=st.last_update_ts,
        last_count=st.last_count,
        frames_out=st.frames_out,
        error=st.error,
    )


@router.get("/status", response_model=StreamStatusResponse)
def status_stream() -> StreamStatusResponse:
    pipeline = get_stream_pipeline()
    st = pipeline.status()

    return StreamStatusResponse(
        running=st.running,
        input_url=st.input_url,
        hls_url=f"/hls/{settings.stream_playlist}",
        started_at=st.started_at,
        last_update_ts=st.last_update_ts,
        last_count=st.last_count,
        frames_out=st.frames_out,
        error=st.error,
    )
