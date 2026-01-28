from threading import Lock
from typing import Any, Dict, List, Optional

import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from ultralytics import YOLO

from app.core.config import settings


class BicycleBox(BaseModel):

    model_config = ConfigDict(extra="ignore")

    x1: float = Field(..., description="Left X in pixels")
    y1: float = Field(..., description="Top Y in pixels")
    x2: float = Field(..., description="Right X in pixels")
    y2: float = Field(..., description="Bottom Y in pixels")
    conf: float = Field(..., ge=0.0, le=1.0, description="Confidence")
    cls_id: int = Field(..., description="Class id from the model")
    cls_name: str = Field(..., description="Class name")


class BicycleDetector:

    def __init__(self) -> None:
        self.model = YOLO(settings.model_name)
        self.names: Dict[int, str] = getattr(self.model, "names", {}) or {}

    def detect_bicycles(self, image: np.ndarray) -> List[BicycleBox]:
        if image is None or not isinstance(image, np.ndarray):
            raise ValueError("image must be a numpy array")

        half = bool(settings.half)
        if not str(settings.device).startswith("cuda"):
            half = False

        results = self.model.predict(
            source=image,
            conf=settings.conf_thres,
            iou=settings.iou_thres,
            device=settings.device,
            half=half,
            verbose=False,
        )

        if not results:
            return []

        r0 = results[0]
        if r0.boxes is None:
            return []

        out: List[BicycleBox] = []

        for b in r0.boxes:
            x1, y1, x2, y2 = b.xyxy[0].tolist() if b.xyxy is not None else [0, 0, 0, 0]
            conf = float(b.conf[0].item()) if b.conf is not None else 0.0
            cls_id = int(b.cls[0].item()) if b.cls is not None else -1
            cls_name = self.names.get(cls_id, str(cls_id))

            if cls_name != "bicycle":
                continue

            if settings.min_box_area > 0:
                area = max(0.0, (x2 - x1)) * max(0.0, (y2 - y1))
                if area < float(settings.min_box_area):
                    continue

            out.append(
                BicycleBox(
                    x1=float(x1),
                    y1=float(y1),
                    x2=float(x2),
                    y2=float(y2),
                    conf=float(conf),
                    cls_id=cls_id,
                    cls_name=cls_name,
                )
            )

        return out


_detector: Optional[BicycleDetector] = None
_detector_lock = Lock()


def get_detector() -> BicycleDetector:
    global _detector
    if _detector is None:
        with _detector_lock:
            if _detector is None:
                _detector = BicycleDetector()
    return _detector


def boxes_to_dicts(boxes: List[BicycleBox]) -> List[Dict[str, Any]]:
    return [b.model_dump() for b in boxes]
