import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from uuid import uuid4

import numpy as np

from app.core.config import project_root, settings
from app.services.counting import count_bicycles
from app.services.detector import get_detector
from app.services.overlay import draw_boxes_inplace
from app.services.postprocess import postprocess_bicycle_boxes
from app.services.roi import get_roi
from app.storage.history_db import HistorySession


@dataclass
class StreamRuntime:
    running: bool
    input_url: Optional[str]
    started_at: Optional[float]
    last_update_ts: Optional[float]
    last_count: int
    frames_out: int
    error: Optional[str]


class _StderrTail:
    def __init__(self, max_lines: int = 200) -> None:
        self._buf = deque(maxlen=max_lines)
        self._stop = threading.Event()
        self._thr: Optional[threading.Thread] = None

    def start(self, pipe) -> None:
        def _run():
            try:
                for raw in iter(pipe.readline, b""):
                    if self._stop.is_set():
                        break
                    line = raw.decode("utf-8", errors="ignore").rstrip()
                    if line:
                        self._buf.append(line)
            except Exception:
                pass

        self._thr = threading.Thread(target=_run, daemon=True)
        self._thr.start()

    def stop(self) -> None:
        self._stop.set()

    def tail(self) -> str:
        return "\n".join(self._buf)


def _read_exactly(pipe, n: int) -> Optional[bytearray]:
    buf = bytearray(n)
    view = memoryview(buf)
    pos = 0
    while pos < n:
        got = pipe.readinto(view[pos:])
        if not got:
            return None
        pos += got
    return buf


class StreamPipeline:

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self._dec_tail: Optional[_StderrTail] = None
        self._enc_tail: Optional[_StderrTail] = None

        self._decode_proc: Optional[subprocess.Popen] = None
        self._encode_proc: Optional[subprocess.Popen] = None

        self._rt = StreamRuntime(
            running=False,
            input_url=None,
            started_at=None,
            last_update_ts=None,
            last_count=0,
            frames_out=0,
            error=None,
        )

    def status(self) -> StreamRuntime:
        with self._lock:
            return StreamRuntime(**self._rt.__dict__)

    def start(self, input_url: str) -> None:
        with self._lock:
            if self._rt.running:
                self._stop_locked()

            self._rt = StreamRuntime(
                running=True,
                input_url=input_url,
                started_at=time.time(),
                last_update_ts=None,
                last_count=0,
                frames_out=0,
                error=None,
            )

            self._stop_event.clear()

            out_dir = project_root() / settings.stream_hls_dir
            out_dir.mkdir(parents=True, exist_ok=True)
            self._clean_hls_dir(out_dir)

            self._thread = threading.Thread(
                target=self._run,
                args=(input_url, out_dir),
                daemon=True,
            )
            self._thread.start()

    def _graceful_stop_processes(
        self,
        dec: Optional[subprocess.Popen],
        enc: Optional[subprocess.Popen],
    ) -> None:
        if enc is not None:
            try:
                if enc.stdin:
                    try:
                        enc.stdin.flush()
                    except Exception:
                        pass
                    try:
                        enc.stdin.close()
                    except Exception:
                        pass
            except Exception:
                pass

        if dec is not None:
            try:
                dec.terminate()
            except Exception:
                pass

        for p in (dec, enc):
            if p is None:
                continue
            try:
                p.wait(timeout=2.0)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass

    def stop(self) -> None:
        with self._lock:
            if not self._rt.running and self._thread is None:
                return

            self._stop_event.set()
            t = self._thread
            self._thread = None

            dec = self._decode_proc
            enc = self._encode_proc

        self._graceful_stop_processes(dec, enc)

        if t is not None:
            try:
                t.join(timeout=3.0)
            except Exception:
                pass

        with self._lock:
            self._decode_proc = None
            self._encode_proc = None
            self._rt.running = False
            self._rt.input_url = None

            out_dir = project_root() / settings.stream_hls_dir
            out_dir.mkdir(parents=True, exist_ok=True)
            self._clean_hls_dir(out_dir)

    def _stop_locked(self) -> None:
        self._stop_event.set()

        for p in (self._decode_proc, self._encode_proc):
            if p is None:
                continue
            try:
                p.terminate()
            except Exception:
                pass

        t = self._thread
        self._thread = None
        if t is not None:
            try:
                t.join(timeout=3.0)
            except Exception:
                pass

        for p in (self._decode_proc, self._encode_proc):
            if p is None:
                continue
            try:
                p.kill()
            except Exception:
                pass

        self._decode_proc = None
        self._encode_proc = None

        self._rt.running = False
        self._rt.input_url = None

    def _clean_hls_dir(self, out_dir: Path) -> None:
        for p in out_dir.glob("*.ts"):
            try:
                p.unlink()
            except Exception:
                pass
        pl = out_dir / settings.stream_playlist
        if pl.exists():
            try:
                pl.unlink()
            except Exception:
                pass

    def _spawn_decode(self, input_url: str, width: int, height: int, out_fps: float) -> subprocess.Popen:
        vf = f"fps={out_fps},scale={width}:{height}"

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-loglevel",
            "warning",
            "-rtsp_transport",
            "tcp",
            "-i",
            input_url,
            "-an",
            "-sn",
            "-dn",
            "-vf",
            vf,
            "-pix_fmt",
            "bgr24",
            "-f",
            "rawvideo",
            "pipe:1",
        ]

        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=10**7,
        )

    def _spawn_encode_hls(self, out_dir: Path, width: int, height: int, out_fps: float) -> subprocess.Popen:
        playlist = out_dir / settings.stream_playlist
        seg_pattern = out_dir / settings.stream_segment_pattern

        gop = max(1, int(round(out_fps * settings.stream_hls_time)))

        if settings.stream_use_nvenc:
            vcodec = [
                "-c:v",
                "h264_nvenc",
                "-preset",
                settings.stream_nvenc_preset,
                "-profile:v",
                "main",
            ]
        else:
            vcodec = [
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-tune",
                "zerolatency",
                "-profile:v",
                "main",
            ]

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "bgr24",
            "-s",
            f"{width}x{height}",
            "-r",
            str(out_fps),
            "-i",
            "pipe:0",
            "-vf",
            "format=yuv420p",
            *vcodec,
            "-rc",
            "vbr" if settings.stream_use_nvenc else "vbr",
            "-b:v",
            settings.stream_bitrate,
            "-maxrate",
            settings.stream_maxrate,
            "-bufsize",
            settings.stream_bufsize,
            "-g",
            str(gop),
            "-keyint_min",
            str(gop),
            "-sc_threshold",
            "0",
            "-f",
            "hls",
            "-hls_time",
            str(settings.stream_hls_time),
            "-hls_list_size",
            str(settings.stream_hls_list_size),
            "-hls_flags",
            "delete_segments+append_list+omit_endlist+independent_segments+temp_file",
            "-hls_segment_filename",
            str(seg_pattern),
            str(playlist),
        ]

        return subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=10**7,
        )

    def _run(self, input_url: str, out_dir: Path) -> None:
        width = int(settings.stream_width)
        height = int(settings.stream_height)
        out_fps = float(settings.stream_output_fps)
        infer_fps = float(settings.infer_fps)

        hs: HistorySession | None = None
        pid: str | None = None
        started_at: float | None = None

        try:
            if out_fps <= 0 or infer_fps <= 0:
                raise RuntimeError("stream_output_fps and infer_fps must be > 0")

            if out_fps < infer_fps:
                raise RuntimeError("stream_output_fps must be >= infer_fps")

            detect_every = max(1, int(round(out_fps / infer_fps)))

            hs = HistorySession.open()
            pid = uuid4().hex

            with self._lock:
                started_at = self._rt.started_at

            hs.create_processing(
                pid=pid,
                kind="stream",
                source=input_url,
                started_at=started_at,
                params={
                    "infer_fps": infer_fps,
                    "out_fps": out_fps,
                    "width": width,
                    "height": height,
                    "model": settings.model_name,
                    "device": settings.device,
                    "half": settings.half,
                    "conf_thres": settings.conf_thres,
                    "iou_thres": settings.iou_thres,
                    "enable_roi": settings.enable_roi,
                    "hls_time": settings.stream_hls_time,
                    "hls_list_size": settings.stream_hls_list_size,
                    "use_nvenc": settings.stream_use_nvenc,
                },
            )

            last_db_write = 0.0
            interval = float(settings.history_stream_interval_sec)
            if interval <= 0:
                interval = 1.0

            detector = get_detector()
            roi = get_roi()

            last_boxes = []
            last_count = 0
            frame_size = width * height * 3

            dec = self._spawn_decode(input_url, width, height, out_fps)
            enc = self._spawn_encode_hls(out_dir, width, height, out_fps)

            self._decode_proc = dec
            self._encode_proc = enc

            if dec.stderr is not None:
                self._dec_tail = _StderrTail()
                self._dec_tail.start(dec.stderr)
            if enc.stderr is not None:
                self._enc_tail = _StderrTail()
                self._enc_tail.start(enc.stderr)

            if dec.stdout is None or enc.stdin is None:
                raise RuntimeError("ffmpeg pipes not available")

            frame_idx = 0

            while not self._stop_event.is_set():
                raw = _read_exactly(dec.stdout, frame_size)
                if raw is None:
                    if self._stop_event.is_set():
                        break

                    rc = dec.poll()
                    dec_log = self._dec_tail.tail() if self._dec_tail else ""
                    enc_log = self._enc_tail.tail() if self._enc_tail else ""
                    raise RuntimeError(
                        "decoder ended (EOF)\n"
                        f"decoder_rc={rc}\n"
                        f"--- decoder stderr tail ---\n{dec_log}\n"
                        f"--- encoder stderr tail ---\n{enc_log}"
                    )

                if self._stop_event.is_set():
                    break

                frame = np.frombuffer(raw, dtype=np.uint8).reshape((height, width, 3))

                if frame_idx % detect_every == 0:
                    boxes = detector.detect_bicycles(frame)
                    boxes = postprocess_bicycle_boxes(boxes)
                    count, filtered = count_bicycles(boxes, roi=roi)

                    last_boxes = filtered
                    last_count = int(count)

                    now = time.time()
                    with self._lock:
                        self._rt.last_update_ts = now
                        self._rt.last_count = last_count

                    if started_at is None:
                        started_at = now

                    if (now - last_db_write) >= interval:
                        t_rel = now - started_at
                        try:
                            hs.add_timeline_points(pid=pid, points=[(float(t_rel), last_count, None)])
                        except Exception:
                            pass
                        last_db_write = now

                if last_boxes:
                    draw_boxes_inplace(frame, last_boxes)

                try:
                    enc.stdin.write(frame.tobytes())
                except Exception as e:
                    raise RuntimeError(f"encoder stdin write failed: {e}") from e

                frame_idx += 1
                with self._lock:
                    self._rt.frames_out = frame_idx

        except Exception as e:
            self._set_error(str(e))

        finally:
            try:
                if self._encode_proc and self._encode_proc.stdin:
                    try:
                        self._encode_proc.stdin.flush()
                    except Exception:
                        pass
            except Exception:
                pass

            for p in (self._decode_proc, self._encode_proc):
                if p is None:
                    continue
                try:
                    p.terminate()
                except Exception:
                    pass
                try:
                    p.wait(timeout=2.0)
                except Exception:
                    try:
                        p.kill()
                    except Exception:
                        pass

            self._decode_proc = None
            self._encode_proc = None

            if self._dec_tail:
                self._dec_tail.stop()
            if self._enc_tail:
                self._enc_tail.stop()

            try:
                if hs is not None and pid is not None:
                    st = self.status()
                    err = st.error
                    status = "error" if err else ("stopped" if self._stop_event.is_set() else "ok")

                    hs.finish_processing(
                        pid=pid,
                        status=status,
                        error=err,
                        result={
                            "frames_out": int(st.frames_out),
                            "last_count": int(st.last_count),
                            "last_update_ts": st.last_update_ts,
                        },
                    )

            except Exception as e:
                print(f"[stream_pipeline] history finalize failed: {e}", flush=True)
            finally:
                try:
                    if hs is not None:
                        hs.close()
                except Exception:
                    pass

            self._mark_stopped()

    def _set_error(self, msg: str) -> None:
        with self._lock:
            self._rt.error = msg

    def _mark_stopped(self) -> None:
        with self._lock:
            self._rt.running = False
