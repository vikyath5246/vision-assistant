"""Dataclasses for background scene detection state."""
from dataclasses import dataclass, field
from typing import List
import time


@dataclass
class Detection:
    label: str
    confidence: float
    bbox_norm: List[float]  # [x1, y1, x2, y2] normalized 0..1


@dataclass
class SceneState:
    detections: List[Detection] = field(default_factory=list)
    timestamp: float = field(default_factory=time.monotonic)

    def to_context_string(self) -> str:
        """Compact text injected into the LLM user message."""
        if not self.detections:
            return ""
        parts = [f"{d.label} ({d.confidence:.2f})" for d in self.detections[:10]]
        return "Current visible objects: " + ", ".join(parts)

    def to_annotation_payload(self) -> List[dict]:
        """Serialisable list of boxes sent to the frontend."""
        return [
            {
                "label": d.label,
                "confidence": round(d.confidence, 2),
                "x1": d.bbox_norm[0],
                "y1": d.bbox_norm[1],
                "x2": d.bbox_norm[2],
                "y2": d.bbox_norm[3],
            }
            for d in self.detections
        ]
