from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

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
    ) -> None:
        self.model_path = Path(model_path)
        self.conf_threshold = conf_threshold
        self.iou_threshold = iou_threshold
        self.device = device
        self._session = None
        self._input_name: str | None = None
        self.active_provider: str = "none"

    def load(self) -> None:
        if not self.model_path.exists():
            logger.warning("ONNX model not found at %s; inference returns empty", self.model_path)
            return
        try:
            import onnxruntime as ort

            providers, label = resolve_onnx_providers(self.device)
            self._session = ort.InferenceSession(str(self.model_path), providers=providers)
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

        blob, sx, sy = self.preprocess(frame)
        outputs = self._session.run(None, {self._input_name: blob})
        return self._postprocess(outputs[0], sx, sy)

    def benchmark_fps(self, frames: int = 30) -> float:
        """Measure inference FPS on synthetic frames."""
        if self._session is None:
            return 0.0
        import time

        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        for _ in range(5):
            self.detect(frame)
        start = time.perf_counter()
        for _ in range(frames):
            self.detect(frame)
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
