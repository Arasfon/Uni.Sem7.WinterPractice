import json
from typing import Any, List, Literal, Optional, Sequence, Tuple

import cv2
import numpy as np
from pydantic import BaseModel, Field

from app.services.detector import BicycleBox


class ROIConfig(BaseModel):

    points: List[Tuple[float, float]] = Field(..., min_length=3)


class ROIPolygon:
    def __init__(self, points: Sequence[Tuple[float, float]]) -> None:
        pts = np.array(list(points), dtype=np.float32)
        self._pts_int = pts.astype(np.int32).reshape((-1, 1, 2))

    def contains_point(self, x: float, y: float) -> bool:
        return cv2.pointPolygonTest(self._pts_int, (float(x), float(y)), False) >= 0

    def filter_boxes_by_center(self, boxes: List[BicycleBox]) -> List[BicycleBox]:
        out: List[BicycleBox] = []
        for b in boxes:
            cx = (b.x1 + b.x2) / 2.0
            cy = (b.y1 + b.y2) / 2.0
            if self.contains_point(cx, cy):
                out.append(b)
        return out


def _as_points_list(payload: Any) -> List[Tuple[float, float]]:
    if not isinstance(payload, list):
        raise ValueError("ROI must be a JSON array")

    pts: List[Tuple[float, float]] = []
    for item in payload:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            x, y = item
            pts.append((float(x), float(y)))
        elif isinstance(item, dict) and "x" in item and "y" in item:
            pts.append((float(item["x"]), float(item["y"])))
        else:
            raise ValueError("ROI points must be [x,y] pairs or {x,y} objects")

    return ROIConfig(points=pts).points


def roi_from_json(
    roi_json: str,
    roi_format: Literal["norm", "px"],
    img_w: int,
    img_h: int,
) -> Optional[ROIPolygon]:
    payload = json.loads(roi_json)
    pts = _as_points_list(payload)
    if len(pts) < 3:
        return None

    out: List[Tuple[float, float]] = []
    for x, y in pts:
        if roi_format == "norm":
            x *= img_w
            y *= img_h

        x = float(max(0, min(img_w - 1, round(x))))
        y = float(max(0, min(img_h - 1, round(y))))
        out.append((x, y))

    if len(out) < 3:
        return None
    return ROIPolygon(out)


def get_roi() -> Optional[ROIPolygon]:
    return None
