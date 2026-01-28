import shutil
import time
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.core.config import project_root, settings
from app.services.counting import count_bicycles
from app.services.detector import BicycleBox, get_detector
from app.services.postprocess import postprocess_bicycle_boxes
from app.services.roi import get_roi
from app.services.video_reader import iter_video_frames
from app.storage.history_db import HistorySession

router = APIRouter(prefix="/api/count", tags=["count"])


class VideoTimelineItem(BaseModel):
    t: float = Field(..., ge=0.0, description="Timestamp (seconds)")
    count: int = Field(..., ge=0, description="Bicycle count at timestamp")
    boxes: Optional[List[BicycleBox]] = Field(
        default=None,
        description="Filtered bicycle boxes (present only if include_boxes=true)",
    )


class VideoCountResponse(BaseModel):
    avg_count: float = Field(..., ge=0.0)
    max_count: int = Field(..., ge=0)
    frames_processed: int = Field(..., ge=0)
    infer_fps: float = Field(..., gt=0.0)
    include_boxes: bool
    timeline: List[VideoTimelineItem]


def _save_upload_to_disk(file: UploadFile) -> Path:
    root = project_root()
    uploads_dir = root / settings.uploads_dir
    uploads_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename or "").suffix
    if not suffix:
        suffix = ".mp4"

    dst = uploads_dir / f"{uuid4().hex}{suffix}"

    try:
        with dst.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save upload: {e}") from e

    return dst


@router.post("/video", response_model=VideoCountResponse)
async def count_bicycles_on_video(
    file: UploadFile = File(...),
    infer_fps: Optional[float] = Query(default=None, gt=0.0),
    include_boxes: bool = Query(default=False),
) -> VideoCountResponse:
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be a video")

    video_path = _save_upload_to_disk(file)

    target_fps = float(infer_fps) if infer_fps is not None else float(settings.infer_fps)
    if target_fps <= 0:
        raise HTTPException(status_code=400, detail="infer_fps must be > 0")

    detector = get_detector()
    roi = get_roi()

    pid = uuid4().hex
    hs = HistorySession.open()
    started = time.time()

    hs.create_processing(
        pid=pid,
        kind="video",
        source=str(video_path.name),
        started_at=started,
        params={
            "infer_fps": target_fps,
            "include_boxes": include_boxes,
            "model": settings.model_name,
            "device": settings.device,
            "half": settings.half,
            "conf_thres": settings.conf_thres,
            "iou_thres": settings.iou_thres,
            "enable_roi": settings.enable_roi,
        },
    )

    timeline: List[VideoTimelineItem] = []
    counts: List[int] = []

    buf: list[tuple[float, int, Optional[dict]]] = []
    batch_n = int(settings.history_batch_size)

    try:
        for t, frame in iter_video_frames(str(video_path), infer_fps=target_fps):
            boxes = detector.detect_bicycles(frame)
            boxes = postprocess_bicycle_boxes(boxes)
            count, filtered = count_bicycles(boxes, roi=roi)

            timeline.append(
                VideoTimelineItem(
                    t=float(t),
                    count=int(count),
                    boxes=filtered if include_boxes else None,
                )
            )
            counts.append(count)

            meta = {"boxes_count": len(filtered)} if include_boxes else None
            buf.append((float(t), int(count), meta))
            if len(buf) >= batch_n:
                hs.add_timeline_points(pid=pid, points=buf)
                buf.clear()

    except Exception as e:
        if buf:
            hs.add_timeline_points(pid=pid, points=buf)
            buf.clear()
        hs.finish_processing(
            pid=pid,
            status="error",
            error=f"{e}",
            result={"frames_processed": len(counts)},
        )
        hs.close()
        raise HTTPException(status_code=400, detail=f"Failed to process video: {e}") from e

    if buf:
        hs.add_timeline_points(pid=pid, points=buf)
        buf.clear()

    frames_processed = len(counts)
    if frames_processed == 0:
        hs.finish_processing(
            pid=pid,
            status="ok",
            result={
                "frames_processed": 0,
                "infer_fps": target_fps,
                "avg_count": 0.0,
                "max_count": 0,
                "timeline_len": 0,
            },
        )
        hs.close()
        return VideoCountResponse(
            avg_count=0.0,
            max_count=0,
            frames_processed=0,
            infer_fps=target_fps,
            include_boxes=include_boxes,
            timeline=[],
        )

    avg_count = sum(counts) / frames_processed
    max_count = max(counts)

    hs.finish_processing(
        pid=pid,
        status="ok",
        result={
            "frames_processed": frames_processed,
            "infer_fps": target_fps,
            "avg_count": float(avg_count),
            "max_count": int(max_count),
            "timeline_len": len(timeline),
        },
    )
    hs.close()

    return VideoCountResponse(
        avg_count=float(avg_count),
        max_count=int(max_count),
        frames_processed=int(frames_processed),
        infer_fps=float(target_fps),
        include_boxes=bool(include_boxes),
        timeline=timeline,
    )
