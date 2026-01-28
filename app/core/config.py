from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    model_config = SettingsConfigDict(
        env_prefix="BC_",
        env_file=".env",
        extra="ignore",
    )

    model_name: str = "yolo26m.pt"
    device: str = "cuda:0"
    half: bool = True
    conf_thres: float = 0.45
    iou_thres: float = 0.45

    infer_fps: float = 2.0
    smooth_window: int = 10

    min_box_area: int = 0

    enable_roi: bool = True

    uploads_dir: str = "data/uploads"

    db_path: str = "data/bicycle_counter.sqlite3"

    history_batch_size: int = 200

    history_stream_interval_sec: float = 1.0

    stream_width: int = 1280
    stream_height: int = 720

    stream_output_fps: float = 25.0

    stream_hls_time: float = 1.0
    stream_hls_list_size: int = 8

    stream_use_nvenc: bool = True
    stream_nvenc_preset: str = "p4"
    stream_bitrate: str = "4M"
    stream_maxrate: str = "6M"
    stream_bufsize: str = "8M"

    stream_hls_dir: str = "hls"
    stream_playlist: str = "stream.m3u8"
    stream_segment_pattern: str = "seg_%05d.ts"


settings = Settings()


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def ensure_dirs() -> None:
    root = project_root()

    (root / settings.uploads_dir).mkdir(parents=True, exist_ok=True)
