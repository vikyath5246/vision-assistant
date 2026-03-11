import { RefObject, useEffect, useState } from 'react';

interface Props {
  videoRef: RefObject<HTMLVideoElement>;
  canvasRef: RefObject<HTMLCanvasElement>;
  annotationCanvasRef: RefObject<HTMLCanvasElement>;
  isCameraActive: boolean;
  isCapturing?: boolean; // flash indicator when frame is being captured
}

export function VideoPreview({ videoRef, canvasRef, annotationCanvasRef, isCameraActive, isCapturing }: Props) {
  const [flash, setFlash] = useState(false);

  useEffect(() => {
    if (isCapturing) {
      setFlash(true);
      const timer = setTimeout(() => setFlash(false), 300);
      return () => clearTimeout(timer);
    }
  }, [isCapturing]);

  return (
    <div
      style={{
        position: 'relative',
        width: '100%',
        aspectRatio: '4/3',
        background: '#111827',
        borderRadius: '12px',
        overflow: 'hidden',
        border: '2px solid #374151',
      }}
    >
      <video
        ref={videoRef}
        autoPlay
        muted
        playsInline
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          display: isCameraActive ? 'block' : 'none',
          transform: 'scaleX(-1)', // Mirror for natural selfie view
        }}
      />
      {!isCameraActive && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            color: '#6b7280',
            gap: '8px',
          }}
        >
          <div style={{ fontSize: '32px' }}>📷</div>
          <div style={{ fontSize: '13px' }}>Camera inactive</div>
        </div>
      )}
      {/* Frame capture flash */}
      {flash && (
        <div
          style={{
            position: 'absolute',
            inset: 0,
            background: 'rgba(255, 255, 255, 0.4)',
            pointerEvents: 'none',
            transition: 'opacity 0.3s ease',
          }}
        />
      )}
      {/* Annotation overlay canvas — same mirror transform as the video */}
      <canvas
        ref={annotationCanvasRef}
        width={640}
        height={480}
        style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          transform: 'scaleX(-1)',
          pointerEvents: 'none',
          display: isCameraActive ? 'block' : 'none',
        }}
      />
      {/* Hidden canvas for frame capture */}
      <canvas ref={canvasRef} style={{ display: 'none' }} />
    </div>
  );
}
