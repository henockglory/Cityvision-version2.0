from __future__ import annotations

import dataclasses
import logging
import os
import queue
import threading
import time
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class _PendingRequest:
    frame: np.ndarray
    result: list[dict] | None = None
    event: threading.Event = dataclasses.field(default_factory=threading.Event)

COCO_CLASSES = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck",
    "boat", "traffic light", "fire hydrant", "stop sign", "parking meter", "bench",
    "bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra",
    "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove",
    "skateboard", "surfboard", "tennis racket", "bottle", "wine glass", "cup",
    "fork", "knife", "spoon", "bowl", "banana", "apple", "sandwich", "orange",
    "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse",
    "remote", "keyboard", "cell phone", "microwave", "oven", "toaster", "sink",
    "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
]

INPUT_SIZE = 640


def resolve_onnx_providers(device: str = "cuda") -> tuple[list[str], str]:
    """Prefer CUDA (RTX 4050 default); fall back to CPU with explicit log."""
    import onnxruntime as ort

    available = set(ort.get_available_providers())
    want_cuda = device.strip().lower() in ("cuda", "gpu", "0")
    if want_cuda and "CUDAExecutionProvider" in available:
        return (["CUDAExecutionProvider", "CPUExecutionProvider"], "cuda")
    if want_cuda:
        logger.warning(
            "YOLO_DEVICE=%s but CUDAExecutionProvider unavailable — using CPU. "
            "Install onnxruntime-gpu and verify nvidia-smi in WSL.",
            device,
        )
    return (["CPUExecutionProvider"], "cpu")


class YoloOnnxDetector:
    """YOLOv8n object detector using ONNX Runtime. Returns empty when model missing."""

    def __init__(
        self,
        model_path: str | Path,
        conf_threshold: float = 0.25,
        iou_threshold: float = 0.45,
        device: str = "cuda",
        max_batch_size: int | None = None,
    ) -> None:
        self.model_path = Path(model_path)
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.device = device
        self._session = None
        self._input_name: str | None = None
        self.active_provider: str = "none"

        # A single ONNX session is shared by every camera's inference thread once
        # RTSP ingest is decoupled from inference (WorkerManager thread pool).
        # session.run() is not guaranteed thread-safe across providers, so every
        # call — single or batched — goes through this lock.
        self._run_lock = threading.Lock()

        # Opportunistic multi-camera micro-batching: concurrent detect() calls
        # arriving within a short window are coalesced into one detect_batch()
        # session.run(), amortizing GPU launch/transfer overhead across cameras
        # instead of paying it once per camera per frame.
        self._microbatch_enabled = os.environ.get("YOLO_MICROBATCH", "1") != "0"
        self._batch_window_sec = float(os.environ.get("YOLO_BATCH_WINDOW_MS", "12")) / 1000.0
        # Priority: explicit constructor arg (hardware tier's settings.batch_size)
        # > YOLO_MAX_BATCH_SIZE env var > hardcoded fallback. This is what makes
        # the hardware_profile tier table's "Batch" column an actual runtime limit
        # instead of a number that only ever lived in documentation.
        if max_batch_size is not None:
            self._max_batch_size = max(1, int(max_batch_size))
        else:
            self._max_batch_size = max(1, int(os.environ.get("YOLO_MAX_BATCH_SIZE", "16")))
        self._batch_queue: queue.Queue[_PendingRequest] = queue.Queue()
        self._batch_thread: threading.Thread | None = None
        self._batch_thread_lock = threading.Lock()

    def load(self) -> None:
        if not self.model_path.exists():
            logger.warning("ONNX model not found at %s; inference returns empty", self.model_path)
            return
        try:
            import onnxruntime as ort

            providers, label = resolve_onnx_providers(self.device)
            try:
                self._session = ort.InferenceSession(str(self.model_path), providers=providers)
            except Exception as cuda_err:
                if "CUDAExecutionProvider" in providers:
                    logger.warning(
                        "YOLO CUDA init failed (%s) — retrying CPUExecutionProvider",
                        cuda_err,
                    )
                    self._session = ort.InferenceSession(
                        str(self.model_path), providers=["CPUExecutionProvider"]
                    )
                    label = "cpu"
                else:
                    raise
            self._input_name = self._session.get_inputs()[0].name
            active = self._session.get_providers()
            self.active_provider = active[0] if active else label
            logger.info(
                "Loaded YOLO ONNX from %s (device=%s, provider=%s)",
                self.model_path,
                label,
                self.active_provider,
            )
        except Exception:
            logger.exception("Failed to load ONNX model")
            self._session = None
            self.active_provider = "none"

    @property
    def is_loaded(self) -> bool:
        return self._session is not None

    @property
    def uses_cuda(self) -> bool:
        return "CUDA" in self.active_provider

    def preprocess(self, frame: np.ndarray) -> tuple[np.ndarray, float, float]:
        h, w = frame.shape[:2]
        scale = min(INPUT_SIZE / w, INPUT_SIZE / h)
        new_w, new_h = int(w * scale), int(h * scale)
        resized = np.zeros((INPUT_SIZE, INPUT_SIZE, 3), dtype=np.uint8)
        import cv2

        cropped = cv2.resize(frame, (new_w, new_h))
        resized[:new_h, :new_w] = cropped
        blob = resized.astype(np.float32) / 255.0
        blob = blob.transpose(2, 0, 1)[np.newaxis, ...]
        return blob, scale, scale

    def detect(self, frame: np.ndarray) -> list[dict]:
        if self._session is None:
            return []
        if not self._microbatch_enabled:
            return self._detect_single(frame)

        self._ensure_batch_thread()
        req = _PendingRequest(frame=frame)
        self._batch_queue.put(req)
        if not req.event.wait(timeout=2.0):
            logger.warning("YOLO microbatch timeout — falling back to direct detect()")
            return self._detect_single(frame)
        return req.result or []

    def _detect_single(self, frame: np.ndarray) -> list[dict]:
        blob, sx, sy = self.preprocess(frame)
        with self._run_lock:
            outputs = self._session.run(None, {self._input_name: blob})
        return self._postprocess(outputs[0], sx, sy)

    def _ensure_batch_thread(self) -> None:
        if self._batch_thread is not None and self._batch_thread.is_alive():
            return
        with self._batch_thread_lock:
            if self._batch_thread is not None and self._batch_thread.is_alive():
                return
            self._batch_thread = threading.Thread(
                target=self._batch_loop, daemon=True, name="yolo-microbatch",
            )
            self._batch_thread.start()

    def _batch_loop(self) -> None:
        """Dedicated dispatcher: coalesces concurrent detect() calls from every
        camera's inference thread into detect_batch() calls, then wakes each
        waiting caller with its own slice of the batched result."""
        while True:
            try:
                first = self._batch_queue.get(timeout=5.0)
            except queue.Empty:
                continue
            batch = [first]
            deadline = time.monotonic() + self._batch_window_sec
            while len(batch) < self._max_batch_size:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    batch.append(self._batch_queue.get(timeout=remaining))
                except queue.Empty:
                    break
            frames = [r.frame for r in batch]
            try:
                results = self.detect_batch(frames)
            except Exception:
                logger.exception("YOLO microbatch inference failed (batch_size=%d)", len(frames))
                results = [[] for _ in frames]
            for r, res in zip(batch, results):
                r.result = res
                r.event.set()

    def preprocess_batch(
        self, frames: list[np.ndarray]
    ) -> tuple[np.ndarray, list[tuple[float, float]]]:
        """Letterbox + stack multiple frames into a single (N,3,640,640) blob."""
        blobs = []
        scales: list[tuple[float, float]] = []
        for frame in frames:
            blob, sx, sy = self.preprocess(frame)
            blobs.append(blob)
            scales.append((sx, sy))
        if not blobs:
            return np.empty((0, 3, INPUT_SIZE, INPUT_SIZE), dtype=np.float32), scales
        return np.concatenate(blobs, axis=0), scales

    def detect_batch(self, frames: list[np.ndarray]) -> list[list[dict]]:
        """Run inference on several frames in ONE session call.

        Batching amortizes the GPU launch/transfer overhead across cameras and
        materially raises throughput on multi-stream deployments versus calling
        ``detect`` per frame. Falls back to empty results when no model is loaded.
        """
        if self._session is None or not frames:
            return [[] for _ in frames]

        blob, scales = self.preprocess_batch(frames)
        with self._run_lock:
            outputs = self._session.run(None, {self._input_name: blob})[0]
        # Normalize to a per-image iterable along the batch dimension.
        batched = outputs if outputs.ndim == 3 else outputs[np.newaxis, ...]
        results: list[list[dict]] = []
        for i in range(len(frames)):
            single = batched[i] if i < len(batched) else batched[-1]
            sx, sy = scales[i]
            results.append(self._postprocess(single, sx, sy))
        return results

    def benchmark_fps(self, frames: int = 30) -> float:
        """Measure raw single-frame inference FPS on synthetic frames.

        Bypasses the micro-batching queue on purpose — this reports the model's
        intrinsic per-call throughput on the active provider (used by /health/gpu),
        not the coalescing latency that only pays off under real multi-camera load.
        """
        if self._session is None:
            return 0.0

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        for _ in range(5):
            self._detect_single(frame)
        start = time.perf_counter()
        for _ in range(frames):
            self._detect_single(frame)
        elapsed = time.perf_counter() - start
        return frames / elapsed if elapsed > 0 else 0.0

    def _postprocess(
        self, output: np.ndarray, scale_x: float, scale_y: float
    ) -> list[dict]:
        if output.ndim == 3:
            output = output[0]
        if output.shape[0] == 84:
            output = output.T

        boxes: list[dict] = []
        for row in output:
            scores = row[4:]
            class_id = int(np.argmax(scores))
            confidence = float(scores[class_id])
            if confidence < self.conf_threshold:
                continue

            cx, cy, bw, bh = row[:4]
            x = (cx - bw / 2) / scale_x
            y = (cy - bh / 2) / scale_y
            w = bw / scale_x
            h = bh / scale_y
            class_name = COCO_CLASSES[class_id] if class_id < len(COCO_CLASSES) else str(class_id)
            boxes.append(
                {
                    "class_id": class_id,
                    "class_name": class_name,
                    "confidence": confidence,
                    "bbox": {"x": float(x), "y": float(y), "width": float(w), "height": float(h)},
                }
            )

        return self._nms(boxes)

    def _nms(self, boxes: list[dict]) -> list[dict]:
        if not boxes:
            return []
        boxes = sorted(boxes, key=lambda b: b["confidence"], reverse=True)
        kept: list[dict] = []
        while boxes:
            best = boxes.pop(0)
            kept.append(best)
            boxes = [b for b in boxes if self._iou(best["bbox"], b["bbox"]) < self.iou_threshold]
        return kept

    @staticmethod
    def _iou(a: dict, b: dict) -> float:
        ax1, ay1 = a["x"], a["y"]
        ax2, ay2 = ax1 + a["width"], ay1 + a["height"]
        bx1, by1 = b["x"], b["y"]
        bx2, by2 = bx1 + b["width"], by1 + b["height"]
        inter_x1 = max(ax1, bx1)
        inter_y1 = max(ay1, by1)
        inter_x2 = min(ax2, bx2)
        inter_y2 = min(ay2, by2)
        inter = max(0, inter_x2 - inter_x1) * max(0, inter_y2 - inter_y1)
        union = a["width"] * a["height"] + b["width"] * b["height"] - inter
        return inter / union if union > 0 else 0.0
