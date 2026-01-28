from typing import Iterable

import cv2
import numpy as np

from app.services.detector import BicycleBox


def draw_boxes_inplace(frame_bgr: np.ndarray, boxes: Iterable[BicycleBox]) -> None:
    for b in boxes:
        x1, y1, x2, y2 = int(b.x1), int(b.y1), int(b.x2), int(b.y2)

        cv2.rectangle(frame_bgr, (x1, y1), (x2, y2), (0, 255, 0), 2)

        label = f"{b.cls_name} {b.conf:.2f}"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        y0 = max(0, y1 - th - 6)
        cv2.rectangle(frame_bgr, (x1, y0), (x1 + tw + 6, y0 + th + 6), (0, 0, 0), -1)
        cv2.putText(
            frame_bgr,
            label,
            (x1 + 3, y0 + th + 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )
