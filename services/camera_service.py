"""Camera management service optimized for Raspberry Pi 3 B+.

Responsibilities:
- Initialize and validate camera configuration
- Provide a low-latency capture loop that always exposes the latest frame
- Lightweight test mode for health checks and optional debug frame saving
- Graceful shutdown, reconnect logic, and safety protections
- Camera version checking and hardware diagnostics

Design notes:
- A single-frame slot (latest frame) is used to avoid queue buildup and copies.
- A short-grace reconnect loop prevents dead capture streams from stalling.
- Pre-flight diagnostics check OpenCV version, camera availability, and capabilities.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any

from pathlib import Path

import cv2
import numpy as np

import configs

logger = logging.getLogger(__name__)


@dataclass
class CameraConfig:
    device: int = configs.CAMERA_DEVICE
    width: int = 640
    height: int = 480
    fps: int = 30
    buffer_size: int = 1  # keep only the newest frame
    frame_format: str = "bgr"  # or 'rgb'
    read_timeout: float = 3.0  # seconds to wait for a first frame

    def __post_init__(self) -> None:
        if not isinstance(self.device, int) or self.device < 0:
            raise ValueError(f"Camera device must be a non-negative integer, got {self.device}")
        if not isinstance(self.width, int) or self.width <= 0:
            raise ValueError(f"Camera width must be a positive integer, got {self.width}")
        if not isinstance(self.height, int) or self.height <= 0:
            raise ValueError(f"Camera height must be a positive integer, got {self.height}")
        if not isinstance(self.fps, int) or self.fps <= 0 or self.fps > 60:
            raise ValueError(f"Camera fps must be an integer between 1 and 60, got {self.fps}")
        if not isinstance(self.buffer_size, int) or self.buffer_size <= 0 or self.buffer_size > 5:
            raise ValueError(f"Camera buffer_size must be an integer between 1 and 5, got {self.buffer_size}")
        if self.frame_format not in {"bgr", "rgb"}:
            raise ValueError(f"Camera frame_format must be 'bgr' or 'rgb', got {self.frame_format}")
        if not isinstance(self.read_timeout, (int, float)) or self.read_timeout <= 0:
            raise ValueError(f"Camera read_timeout must be positive, got {self.read_timeout}")


class CameraVersion:
    """OpenCV version info and camera capability checks."""
    
    @staticmethod
    def get_opencv_version() -> str:
        """Return OpenCV version string."""
        return cv2.__version__
    
    @staticmethod
    def get_opencv_major_minor() -> Tuple[int, int]:
        """Return major and minor version as tuple."""
        parts = cv2.__version__.split('.')
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        return (major, minor)
    
    @staticmethod
    def check_v4l2_support() -> bool:
        """Check if VideoCapture uses v4l2 backend (Linux/RPi)."""
        try:
            cap = cv2.VideoCapture(0)
            backend = cap.get(cv2.CAP_PROP_BACKEND)
            cap.release()
            # CAP_V4L2 = 200
            return backend == 200
        except Exception:
            return False
    
    @staticmethod
    def get_camera_properties(device: int = 0) -> Dict[str, Any]:
        """Probe camera device for supported properties."""
        props = {
            "device": device,
            "is_available": False,
            "frame_count": 0,
            "fps": 0.0,
            "width": 0,
            "height": 0,
            "backend": "unknown",
            "can_set_fps": False,
            "can_set_resolution": False,
            "first_frame_time_ms": None,
            "error": None,
        }
        
        try:
            cap = cv2.VideoCapture(device)
            if not cap.isOpened():
                props["error"] = "Failed to open VideoCapture"
                return props
            
            props["is_available"] = True
            props["frame_count"] = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            props["fps"] = cap.get(cv2.CAP_PROP_FPS)
            props["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            props["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            props["backend"] = int(cap.get(cv2.CAP_PROP_BACKEND))
            
            # Test setting FPS
            cap.set(cv2.CAP_PROP_FPS, 30)
            props["can_set_fps"] = cap.get(cv2.CAP_PROP_FPS) > 0
            
            # Test setting resolution
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            props["can_set_resolution"] = (w > 0 and h > 0)
            
            # Measure first frame latency
            t0 = time.time()
            for _ in range(10):
                ok, frame = cap.read()
                if ok:
                    props["first_frame_time_ms"] = (time.time() - t0) * 1000
                    break
            
            cap.release()
        except Exception as exc:
            props["error"] = str(exc)
        
        return props


class CameraService:
    """Camera service providing a low-latency newest-frame buffer.

    Usage:
    - create instance
    - call `start()` to begin capture thread
    - use `get_latest(copy=False)` to obtain newest frame reference
    - call `stop()` to shutdown and release resources
    
    For troubleshooting, call:
    - `diagnose()` to check OpenCV version and camera hardware
    - `benchmark_first_frame()` to measure actual startup latency
    """

    def __init__(self, config: Optional[CameraConfig] = None):
        self.config = config or CameraConfig()
        self._capture: Optional[cv2.VideoCapture] = None
        self._capture_lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._frame_lock = threading.Lock()
        self._latest_frame: Optional[np.ndarray] = None
        self._latest_ts: Optional[float] = None
        self._latest_frame_id: int = 0
        self._opened = False
        self._first_frame_timestamp: Optional[float] = None

    def diagnose(self) -> Dict[str, Any]:
        """Run comprehensive diagnostics on camera and OpenCV setup.
        
        Returns a dict with:
        - opencv_version: OpenCV version string
        - camera_available: bool
        - camera_properties: dict of hardware capabilities
        - first_frame_latency_ms: measured startup time
        - recommendations: list of improvement suggestions
        """
        logger.info("=== CAMERA DIAGNOSTIC REPORT ===")
        
        report = {
            "opencv_version": CameraVersion.get_opencv_version(),
            "opencv_major_minor": CameraVersion.get_opencv_major_minor(),
            "v4l2_backend": CameraVersion.check_v4l2_support(),
            "camera_device": self.config.device,
            "camera_properties": CameraVersion.get_camera_properties(self.config.device),
            "first_frame_latency_ms": None,
            "recommendations": [],
        }
        
        logger.info(f"OpenCV Version: {report['opencv_version']}")
        logger.info(f"Camera Device: /dev/video{self.config.device}")
        logger.info(f"Using v4l2 backend: {report['v4l2_backend']}")
        
        props = report["camera_properties"]
        if props.get("error"):
            logger.error(f"Camera Error: {props['error']}")
            report["recommendations"].append(
                f"Camera device /dev/video{self.config.device} failed to open: {props['error']}"
            )
        else:
            logger.info(f"Camera FPS: {props.get('fps', 'unknown')}")
            logger.info(f"Camera Resolution: {props.get('width')}x{props.get('height')}")
            logger.info(f"First Frame Latency: {props.get('first_frame_time_ms'):.1f}ms")
            report["first_frame_latency_ms"] = props.get("first_frame_time_ms")
            
            if not props.get("can_set_fps"):
                report["recommendations"].append(
                    "Camera driver may not support FPS configuration; performance may vary"
                )
            if not props.get("can_set_resolution"):
                report["recommendations"].append(
                    "Camera driver may not support resolution changes; using driver defaults"
                )
            
            if props.get("first_frame_time_ms", 999) > 2000:
                report["recommendations"].append(
                    f"High first-frame latency ({props.get('first_frame_time_ms'):.0f}ms); "
                    "consider lower resolution or reducing FPS"
                )
        
        for rec in report["recommendations"]:
            logger.warning(f"  * {rec}")
        
        logger.info("=== END DIAGNOSTIC REPORT ===\n")
        return report

    def benchmark_first_frame(self, trials: int = 3) -> float:
        """Measure actual time to get first frame (useful for tuning timeout).
        
        Runs multiple trials and returns the median latency in seconds.
        """
        logger.info(f"Benchmarking first-frame latency ({trials} trials)...")
        latencies = []
        
        for trial in range(trials):
            try:
                self.stop()  # ensure clean state
                time.sleep(0.2)
                
                t0 = time.time()
                self.start()
                got_frame = self.wait_for_first_frame(timeout=10.0)
                elapsed = time.time() - t0
                
                if got_frame:
                    latencies.append(elapsed)
                    logger.info(f"  Trial {trial + 1}: {elapsed:.2f}s")
                else:
                    logger.warning(f"  Trial {trial + 1}: timeout after {elapsed:.2f}s")
            except Exception as exc:
                logger.exception(f"  Trial {trial + 1}: exception {exc}")
        
        if latencies:
            latencies.sort()
            median = latencies[len(latencies) // 2]
            logger.info(f"Median latency: {median:.2f}s; recommend timeout >= {median * 1.5:.2f}s")
            return median
        else:
            logger.error("All trials failed; cannot determine latency")
            return 999.0

    def _open_capture(self) -> bool:
        logger.info(f"Opening camera device {self.config.device}")
        cap = cv2.VideoCapture(self.config.device)
        if not cap.isOpened():
            logger.warning("cv2.VideoCapture failed to open")
            return False
        # Apply best-effort settings; drivers may ignore unsupported values
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(self.config.width))
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(self.config.height))
        cap.set(cv2.CAP_PROP_FPS, int(self.config.fps))
        try:
            # buffer size hint for v4l2 backends
            cap.set(cv2.CAP_PROP_BUFFERSIZE, int(self.config.buffer_size))
        except Exception:
            pass
        with self._capture_lock:
            self._capture = cap
            self._opened = True
        return True

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._capture_loop, name="camera-capture", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout)
        with self._capture_lock:
            if self._capture:
                try:
                    self._capture.release()
                except Exception:
                    pass
                self._capture = None
        self._opened = False

    def _capture_loop(self) -> None:
        backoff = 0.5
        last_open_attempt = 0.0
        frames_captured = 0
        loop_start_time = time.time()
        
        while not self._stop_event.is_set():
            with self._capture_lock:
                cap = self._capture
                opened = self._opened
            if not cap or not opened:
                now = time.time()
                if now - last_open_attempt < backoff:
                    time.sleep(0.05)
                    continue
                last_open_attempt = now
                if not self._open_capture():
                    logger.warning("Camera open failed, retrying")
                    time.sleep(backoff)
                    backoff = min(5.0, backoff * 1.5)
                    continue
                backoff = 0.5
                frames_captured = 0
                loop_start_time = time.time()
                with self._capture_lock:
                    cap = self._capture
            if cap is None:
                continue
            try:
                # read is usually blocking and efficient in native code
                success, frame = cap.read()
                if not success or frame is None:
                    logger.warning("Camera read failure, attempting reconnect")
                    try:
                        cap.release()
                    except Exception:
                        pass
                    with self._capture_lock:
                        self._capture = None
                        self._opened = False
                    time.sleep(0.1)
                    continue

                # Store frame reference to single-slot buffer; avoid copies
                with self._frame_lock:
                    self._latest_frame = frame
                    self._latest_ts = time.time()
                    self._latest_frame_id += 1
                    
                    # Track first frame timestamp for diagnostics
                    if self._first_frame_timestamp is None:
                        self._first_frame_timestamp = time.time() - loop_start_time
                        logger.info(f"First frame captured in {self._first_frame_timestamp*1000:.1f}ms")
                
                frames_captured += 1

            except Exception as exc:  # defensive: do not let thread die
                logger.exception("Camera capture loop exception: %s", exc)
                with self._capture_lock:
                    if self._capture:
                        try:
                            self._capture.release()
                        except Exception:
                            pass
                        self._capture = None
                        self._opened = False
                time.sleep(0.5)

        # cleanup when stopping
        with self._capture_lock:
            if self._capture:
                try:
                    self._capture.release()
                except Exception:
                    pass
                self._capture = None
        logger.info(f"Camera capture thread stopped (captured {frames_captured} frames)")

    def is_available(self) -> bool:
        # quick non-blocking probe: try to open and read a single frame
        probe_cap = cv2.VideoCapture(self.config.device)
        try:
            if not probe_cap.isOpened():
                return False
            # try a quick read with timeout guard
            t0 = time.time()
            while time.time() - t0 < self.config.read_timeout:
                ok, _ = probe_cap.read()
                if ok:
                    return True
            return False
        finally:
            try:
                probe_cap.release()
            except Exception:
                pass

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive() and self._opened

    def get_last_frame_age(self) -> Optional[float]:
        with self._frame_lock:
            if self._latest_ts is None:
                return None
            return time.time() - self._latest_ts

    def wait_for_first_frame(self, timeout: float = 5.0) -> bool:
        """Wait for the first frame with diagnostic logging.
        
        Args:
            timeout: Maximum seconds to wait for first frame
            
        Returns:
            True if first frame received, False if timeout or stopped
        """
        logger.info(f"Waiting for first frame (timeout={timeout:.1f}s)...")
        start = time.time()
        last_log = start
        log_interval = 1.0
        
        while time.time() - start < timeout:
            if self.get_latest(copy=False) is not None:
                elapsed = time.time() - start
                logger.info(f"First frame received in {elapsed:.2f}s")
                return True
            
            if self._stop_event.is_set():
                logger.warning("wait_for_first_frame: stop event set, aborting")
                return False
            
            # Log progress every second
            now = time.time()
            if now - last_log >= log_interval:
                elapsed_so_far = now - start
                logger.debug(f"Waiting... {elapsed_so_far:.1f}s elapsed (thread alive: {self._thread and self._thread.is_alive()})")
                last_log = now
            
            time.sleep(0.05)
        
        # Timeout occurred
        elapsed = time.time() - start
        logger.error(f"Timeout waiting for first frame after {elapsed:.2f}s")
        
        # Log diagnostic info
        if self._thread is None or not self._thread.is_alive():
            logger.error("  -> Camera thread is NOT running")
        else:
            logger.error("  -> Camera thread is running but no frames received")
            with self._capture_lock:
                if self._capture is None:
                    logger.error("     VideoCapture is None")
                elif not self._opened:
                    logger.error("     VideoCapture not opened")
        
        return False

    def get_latest(self, copy: bool = False) -> Optional[Tuple[np.ndarray, float]]:
        """Return (frame, timestamp) of the newest frame or None.

        If `copy` is True a deep copy of the frame is returned. For lowest
        latency and memory use, keep `copy=False` and treat the returned
        numpy array as read-only.
        """
        with self._frame_lock:
            if self._latest_frame is None:
                return None
            frame = self._latest_frame
            timestamp = float(self._latest_ts)
        if self.config.frame_format == "rgb":
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            if copy:
                return (frame.copy(), timestamp)
            return (frame, timestamp)
        if copy:
            return (frame.copy(), timestamp)
        return (frame, timestamp)

    def get_latest_metadata(self, copy: bool = False) -> Optional[tuple[ np.ndarray, float, int]]:
        """Return (frame, timestamp, frame_id) for the newest frame or None."""
        with self._frame_lock:
            if self._latest_frame is None:
                return None
            frame = self._latest_frame
            timestamp = float(self._latest_ts)
            frame_id = self._latest_frame_id
        if self.config.frame_format == "rgb":
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            if copy:
                return (frame.copy(), timestamp, frame_id)
            return (frame, timestamp, frame_id)
        if copy:
            return (frame.copy(), timestamp, frame_id)
        return (frame, timestamp, frame_id)

    def test_mode(self, run_seconds: float = 5.0, save_debug_frame: Optional[Path] = None) -> None:
        """Run a lightweight capture test printing FPS and optionally saving a frame.

        This method runs independently (blocking) and is safe to use without
        the model service. It helps validate camera health and basic timing.
        """
        logger.info("Starting camera test mode")
        self.start()
        try:
            start = time.time()
            last_report = start
            report_interval = 1.0
            frames = 0
            frames_since_report = 0
            saved = False
            while time.time() - start < run_seconds:
                res = self.get_latest(copy=True)
                if res is None:
                    time.sleep(0.01)
                    continue
                frame, ts = res
                frames += 1
                frames_since_report += 1
                if save_debug_frame and not saved:
                    try:
                        cv2.imwrite(str(save_debug_frame), frame)
                        saved = True
                        logger.info("Saved debug frame to %s", save_debug_frame)
                    except Exception:
                        logger.exception("Failed to save debug frame")
                now = time.time()
                if now - last_report >= report_interval:
                    fps = frames_since_report / max(1e-6, now - last_report)
                    logger.info("Camera test FPS=%.2f total_frames=%d", fps, frames)
                    last_report = now
                    frames_since_report = 0
                time.sleep(0.001)

            elapsed = max(1e-6, time.time() - start)
            logger.info("Camera test complete: frames=%d elapsed=%.2fs fps=%.2f", frames, elapsed, frames / elapsed)
        finally:
            self.stop()

    def __enter__(self) -> "CameraService":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()


if __name__ == "__main__":
    # simple smoke test when run directly
    logging.basicConfig(level=logging.INFO)
    cam = CameraService()
    try:
        cam.test_mode(run_seconds=4.0, save_debug_frame=Path("debug_frame.jpg"))
    finally:
        cam.stop()
