import { useCallback, useRef, useState } from 'react';

export function useVideoCapture() {
  const [isCameraActive, setIsCameraActive] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const sceneIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const startCamera = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { width: 640, height: 480, facingMode: 'environment' }
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setIsCameraActive(true);
    } catch (e) {
      console.error('[video] Failed to start camera:', e);
    }
  }, []);

  const stopCamera = useCallback(() => {
    // Stop background scene push before tearing down the camera
    if (sceneIntervalRef.current) {
      clearInterval(sceneIntervalRef.current);
      sceneIntervalRef.current = null;
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setIsCameraActive(false);
  }, []);

  const captureFrame = useCallback((): string | null => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || !isCameraActive) return null;

    const ctx = canvas.getContext('2d');
    if (!ctx) return null;

    canvas.width = 640;
    canvas.height = 480;
    ctx.drawImage(video, 0, 0, 640, 480);

    // JPEG at quality 0.7: good balance of size and image quality
    const dataUrl = canvas.toDataURL('image/jpeg', 0.7);
    return dataUrl.split(',')[1]; // Return base64 part only
  }, [isCameraActive]);

  /**
   * Start pushing scene frames to the backend every `intervalMs` milliseconds.
   * Call `onFrame` with the base64 JPEG string each tick.
   * Safe to call multiple times — won't create duplicate intervals.
   */
  const startSceneFramePush = useCallback(
    (onFrame: (base64: string) => void, intervalMs = 1500) => {
      if (sceneIntervalRef.current) return;
      sceneIntervalRef.current = setInterval(() => {
        const frame = captureFrame();
        if (frame) onFrame(frame);
      }, intervalMs);
    },
    [captureFrame],
  );

  const stopSceneFramePush = useCallback(() => {
    if (sceneIntervalRef.current) {
      clearInterval(sceneIntervalRef.current);
      sceneIntervalRef.current = null;
    }
  }, []);

  return {
    videoRef,
    canvasRef,
    isCameraActive,
    startCamera,
    stopCamera,
    captureFrame,
    startSceneFramePush,
    stopSceneFramePush,
  };
}
