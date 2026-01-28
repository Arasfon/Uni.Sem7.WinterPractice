from collections import deque
from statistics import median
from typing import Deque, List, Optional, Tuple

from app.core.config import settings
from app.services.detector import BicycleBox
from app.services.roi import ROIPolygon


def filter_boxes(
    boxes: List[BicycleBox],
    roi: Optional[ROIPolygon] = None,
) -> List[BicycleBox]:
    if roi is not None:
        boxes = roi.filter_boxes_by_center(boxes)

    return boxes


def count_bicycles(
    boxes: List[BicycleBox],
    roi: Optional[ROIPolygon] = None,
) -> Tuple[int, List[BicycleBox]]:
    filtered = filter_boxes(boxes, roi=roi)
    return len(filtered), filtered


class MedianSmoother:

    def __init__(self, window: int = 10) -> None:
        if window <= 0:
            raise ValueError("window must be > 0")
        self.window = window
        self.buf: Deque[int] = deque(maxlen=window)

    def update(self, value: int) -> int:
        self.buf.append(int(value))
        return int(median(self.buf)) if self.buf else int(value)

    def reset(self) -> None:
        self.buf.clear()


class StreamCounter:

    def __init__(self, roi: Optional[ROIPolygon] = None) -> None:
        self.roi = roi
        self.smoother = MedianSmoother(window=settings.smooth_window)

    def update(self, boxes: List[BicycleBox]) -> Tuple[int, int, List[BicycleBox]]:
        raw_count, filtered = count_bicycles(boxes, roi=self.roi)
        smoothed = self.smoother.update(raw_count)
        return raw_count, smoothed, filtered

    def reset(self) -> None:
        self.smoother.reset()
