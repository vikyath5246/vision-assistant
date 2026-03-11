/**
 * Draws YOLO bounding boxes on an overlay canvas whenever `annotations`
 * WebSocket events arrive from the backend.
 *
 * Coordinate note: the video element has CSS `transform: scaleX(-1)` (mirror).
 * The overlay canvas gets the same transform, so the canvas 2D coordinate space
 * is already flipped.  YOLO ran on the *unmirrored* image, so we flip x coords:
 *   canvas_x1 = (1 - box.x2) * canvasWidth
 *   canvas_width = (box.x2 - box.x1) * canvasWidth
 */
import { RefObject, useEffect, useRef } from 'react';
import { AnnotationBox, AnnotationsMessage } from '../types/messages';

// Persistent label → color mapping so colors stay stable across frames
const LABEL_COLORS: Record<string, string> = {};
const COLOR_PALETTE = [
  '#ef4444', '#3b82f6', '#10b981', '#f59e0b',
  '#8b5cf6', '#ec4899', '#06b6d4', '#84cc16',
];
let _colorIdx = 0;

function colorForLabel(label: string): string {
  if (!LABEL_COLORS[label]) {
    LABEL_COLORS[label] = COLOR_PALETTE[_colorIdx++ % COLOR_PALETTE.length];
  }
  return LABEL_COLORS[label];
}

function drawBoxes(canvas: HTMLCanvasElement, boxes: AnnotationBox[]) {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const W = canvas.width;
  const H = canvas.height;
  ctx.clearRect(0, 0, W, H);

  for (const box of boxes) {
    // Flip x coordinates to match the mirrored canvas transform
    const x1 = (1 - box.x2) * W;
    const y1 = box.y1 * H;
    const bw = (box.x2 - box.x1) * W;
    const bh = (box.y2 - box.y1) * H;

    const color = colorForLabel(box.label);
    const label = `${box.label} ${Math.round(box.confidence * 100)}%`;

    // Bounding box stroke
    ctx.strokeStyle = color;
    ctx.lineWidth = 2;
    ctx.strokeRect(x1, y1, bw, bh);

    // Label chip background
    ctx.font = 'bold 12px sans-serif';
    const textW = ctx.measureText(label).width;
    const chipH = 18;
    const chipY = y1 > chipH ? y1 - chipH : y1 + 2;
    ctx.fillStyle = color;
    ctx.fillRect(x1, chipY, textW + 8, chipH);

    // Label text
    ctx.fillStyle = '#ffffff';
    ctx.fillText(label, x1 + 4, chipY + chipH - 4);
  }
}

export function useAnnotations(
  canvasRef: RefObject<HTMLCanvasElement>,
  onMessage: (event: string, handler: (msg: unknown) => void) => () => void,
  isCameraActive: boolean,
) {
  const fadeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const unsub = onMessage('annotations', (raw) => {
      const msg = raw as AnnotationsMessage;
      const canvas = canvasRef.current;
      if (!canvas || !isCameraActive) return;

      drawBoxes(canvas, msg.boxes);

      // Auto-clear after 3 seconds of no new frames
      if (fadeTimerRef.current) clearTimeout(fadeTimerRef.current);
      fadeTimerRef.current = setTimeout(() => {
        const c = canvasRef.current;
        if (c) c.getContext('2d')?.clearRect(0, 0, c.width, c.height);
      }, 3000);
    });

    return () => {
      unsub();
      if (fadeTimerRef.current) {
        clearTimeout(fadeTimerRef.current);
        fadeTimerRef.current = null;
      }
    };
  }, [canvasRef, onMessage, isCameraActive]);
}
