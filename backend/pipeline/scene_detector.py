"""YOLOv8n-based background scene detector.

Uses the `ultralytics` package which handles all model loading,
preprocessing (letterboxing, normalisation) and postprocessing (NMS)
internally, so this wrapper stays thin.

The `SceneDetector` is a singleton shared across all sessions — inference
is stateless, so concurrent sessions call `process_frame_b64` safely.
"""
import asyncio
import base64
import logging
from io import BytesIO
from typing import Optional

from config import SCENE_CONFIDENCE_THRESHOLD, YOLO_MODEL_PATH
from pipeline.scene_state import Detection, SceneState

logger = logging.getLogger(__name__)


class SceneDetector:
    def __init__(self):
        from ultralytics import YOLO
        import numpy as np

        logger.info("[scene] Loading YOLOv8n from %s", YOLO_MODEL_PATH)
        self.model = YOLO(YOLO_MODEL_PATH)

        # Warm-up: one dummy inference so the first real frame isn't slow
        dummy = np.zeros((480, 640, 3), dtype=np.uint8)
        self.model(dummy, verbose=False)
        logger.info("[scene] YOLOv8n loaded and warmed up")

    # ------------------------------------------------------------------
    # Sync inference (called in executor to avoid blocking the event loop)
    # ------------------------------------------------------------------

    def _run_inference(self, image_bytes: bytes) -> SceneState:
        from PIL import Image

        img = Image.open(BytesIO(image_bytes)).convert("RGB")
        w, h = img.size

        results = self.model(img, verbose=False)[0]

        detections: list[Detection] = []
        for box in results.boxes:
            conf = float(box.conf[0])
            if conf < SCENE_CONFIDENCE_THRESHOLD:
                continue
            cls_id = int(box.cls[0])
            label = results.names[cls_id]
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            detections.append(Detection(
                label=label,
                confidence=conf,
                bbox_norm=[x1 / w, y1 / h, x2 / w, y2 / h],
            ))

        # Highest-confidence detections first
        detections.sort(key=lambda d: d.confidence, reverse=True)
        return SceneState(detections=detections)

    # ------------------------------------------------------------------
    # Async API
    # ------------------------------------------------------------------

    async def process_frame_b64(self, frame_b64: str) -> Optional[SceneState]:
        """Decode a base64 JPEG frame, run YOLO, return a SceneState."""
        try:
            image_bytes = base64.b64decode(frame_b64)
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._run_inference, image_bytes)
        except Exception as e:
            logger.error("[scene] Inference error: %s", e)
            return None
