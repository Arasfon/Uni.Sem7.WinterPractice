import time
from typing import List, Literal, Optional
from uuid import uuid4

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.counting import count_bicycles
from app.services.detector import BicycleBox, get_detector
from app.services.postprocess import postprocess_bicycle_boxes
from app.services.roi import ROIPolygon, roi_from_json
from app.storage.history_db import HistorySession

router = APIRouter(prefix="/api/count", tags=["count"])


class PhotoCountResponse(BaseModel):
    count: int = Field(..., ge=0)
    boxes: List[BicycleBox]


@router.post("/photo", response_model=PhotoCountResponse)
async def count_bicycles_on_photo(
    file: UploadFile = File(...),
    roi_enabled: bool = Form(False),
    roi: Optional[str] = Form(None),
    roi_format: Literal["norm", "px"] = Form("norm"),
) -> PhotoCountResponse:
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image")

    pid = uuid4().hex
    hs = HistorySession.open()
    started = time.time()

    hs.create_processing(
        pid=pid,
        kind="photo",
        source=file.filename or "upload",
        started_at=started,
        params={
            "roi_enabled": bool(roi_enabled),
            "roi_format": roi_format,
            "enable_roi": settings.enable_roi,
            "model": settings.model_name,
            "device": settings.device,
            "half": settings.half,
            "conf_thres": settings.conf_thres,
            "iou_thres": settings.iou_thres,
        },
    )

    try:
        raw = await file.read()
        data = np.frombuffer(raw, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Failed to decode image")

        h, w = img.shape[:2]

        detector = get_detector()
        boxes = detector.detect_bicycles(img)
        boxes = postprocess_bicycle_boxes(boxes)

        roi_poly: ROIPolygon | None = None
        if settings.enable_roi and roi_enabled and roi:
            roi_poly = roi_from_json(roi, roi_format, w, h)

        count, filtered_boxes = count_bicycles(boxes, roi=roi_poly)

        hs.finish_processing(
            pid=pid,
            status="ok",
            result={
                "count": int(count),
                "boxes_count": len(filtered_boxes),
                "width": int(w),
                "height": int(h),
            },
        )

        return PhotoCountResponse(count=count, boxes=filtered_boxes)

    except Exception as e:
        hs.finish_processing(pid=pid, status="error", error=str(e))
        raise HTTPException(status_code=400, detail=f"Failed to process image: {e}") from e
    finally:
        hs.close()
