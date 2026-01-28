from dataclasses import dataclass
from typing import Generator, Optional, Tuple

import cv2
import numpy as np

from app.core.config import settings


@dataclass(frozen=True)
class VideoMeta:
    fps: float
    frame_count: int
    width: int
    height: int
    duration_s: float


def get_video_meta(cap: cv2.VideoCapture) -> VideoMeta:
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

    duration_s = 0.0
    if fps > 0 and frame_count > 0:
        duration_s = frame_count / fps

    return VideoMeta(
        fps=fps,
        frame_count=frame_count,
        width=width,
        height=height,
        duration_s=duration_s,
    )


def iter_video_frames(
    video_path: str,
    infer_fps: Optional[float] = None,
    max_frames: Optional[int] = None,
) -> Generator[Tuple[float, np.ndarray], None, VideoMeta]:
    target_fps = float(infer_fps if infer_fps is not None else settings.infer_fps)
    if target_fps <= 0:
        raise ValueError("infer_fps must be > 0")

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Failed to open video: {video_path}")

    meta = get_video_meta(cap)

    video_fps = meta.fps if meta.fps > 0 else None

    step_s = 1.0 / target_fps
    next_t = 0.0

    yielded = 0
    frame_idx = 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                break

            if video_fps is not None:
                t = frame_idx / video_fps
            else:
                t = float(cap.get(cv2.CAP_PROP_POS_MSEC) or 0.0) / 1000.0

            if t + 1e-9 >= next_t:
                yield (t, frame)
                yielded += 1
                next_t += step_s

                if max_frames is not None and yielded >= max_frames:
                    break

            frame_idx += 1

    finally:
        cap.release()

    return meta
