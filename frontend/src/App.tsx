import { useCallback, useEffect, useRef, useState } from 'react';
import { useSession } from './hooks/useSession';
import { useWebSocket } from './hooks/useWebSocket';
import { useAudioPipeline } from './hooks/useAudioPipeline';
import { useVideoCapture } from './hooks/useVideoCapture';
import { useConversation } from './hooks/useConversation';
import { useTTSPlayback } from './hooks/useTTSPlayback';
import { useAnnotations } from './hooks/useAnnotations';

import { StatusBar } from './components/StatusBar';
import { VideoPreview } from './components/VideoPreview';
import { AudioVisualizer } from './components/AudioVisualizer';
import { ConversationThread } from './components/ConversationThread';
import { StartButton } from './components/StartButton';
import { MediaControls } from './components/MediaControls';
import { MetricsDashboard } from './components/MetricsDashboard';

import { MediaMessage, StateMessage, TextMessage } from './types/messages';

export default function App() {
  const { sessionId } = useSession();
  const { isConnected, sendJson, onMessage } = useWebSocket(sessionId);
  const {
    videoRef, canvasRef, isCameraActive,
    startCamera, stopCamera, captureFrame,
    startSceneFramePush, stopSceneFramePush,
  } = useVideoCapture();

  const annotationCanvasRef = useRef<HTMLCanvasElement>(null);
  const { messages, handleTextMessage, clearOnInterrupt } = useConversation();

  const [isActive, setIsActive] = useState(false);
  const [isBotResponding, setIsBotResponding] = useState(false);
  const [isCapturing, setIsCapturing] = useState(false);
  const [activeSessionCount, setActiveSessionCount] = useState(1);
  const [isCameraOff, setIsCameraOff] = useState(false);
  const isCameraOffRef = useRef(false);

  // Ref bridge to avoid circular deps between TTS and audio pipeline
  const setBotSpeakingRef = useRef<((s: boolean) => void) | null>(null);

  const { enqueueAudio, stopPlayback, resetQueue } = useTTSPlayback(
    useCallback((speaking: boolean) => { setBotSpeakingRef.current?.(speaking); }, [])
  );

  const onBotInterrupt = useCallback(() => {
    stopPlayback();
    sendJson({ event: 'interrupt' });
  }, [stopPlayback, sendJson]);

  const audioPipeline = useAudioPipeline(sendJson, onBotInterrupt);
  const {
    isMicMuted,
    toggleMicMute,
    vadProb,
    speechState,
    startListening,
    stopListening,
    setBotSpeaking,
    updateFromState,
  } = audioPipeline;

  // Wire setBotSpeaking after audioPipeline is initialized
  useEffect(() => {
    setBotSpeakingRef.current = setBotSpeaking;
  }, [setBotSpeaking]);

  // Draw YOLO bounding boxes on the annotation canvas overlay
  useAnnotations(annotationCanvasRef, onMessage, isCameraActive);

  // Poll /health every 10 s for active session count (multi-session badge)
  useEffect(() => {
    const fetchCount = async () => {
      try {
        const res = await fetch('/health');
        const data = await res.json();
        setActiveSessionCount(data.active_sessions ?? 1);
      } catch { /* ignore network errors */ }
    };
    fetchCount();
    const interval = setInterval(fetchCount, 10_000);
    return () => clearInterval(interval);
  }, []);

  // Always use server-side TTS (edge-tts → WAV → WebAudio).
  // Browser speechSynthesis is unreliable (known Chrome stop-after-15s bug).
  useEffect(() => {
    if (!isConnected) return;
    sendJson({ event: 'config', tts_mode: 'server' });
  }, [isConnected, sendJson]);

  // Wire server → client message handlers
  useEffect(() => {
    const unsubState = onMessage('state', (msg) => {
      const m = msg as StateMessage;
      updateFromState(m.vad_prob, m.state);
      setIsBotResponding(m.responding);
    });

    const unsubText = onMessage('text', (msg) => {
      const m = msg as TextMessage;
      handleTextMessage(m);
    });

    const unsubMedia = onMessage('media', (msg) => {
      const m = msg as MediaMessage;
      if (m.mime === 'audio/wav') {
        enqueueAudio(m.audio, m.index);
      }
    });

    const unsubInterrupt = onMessage('interrupt', () => {
      stopPlayback();
      clearOnInterrupt();
    });

    const unsubCaptureFrame = onMessage('capture_frame', () => {
      if (isCameraOffRef.current) {
        sendJson({ event: 'frame', image: null, mime: 'image/jpeg' });
        return;
      }
      setIsCapturing(true);
      const frame = captureFrame();
      setTimeout(() => setIsCapturing(false), 300);
      sendJson({ event: 'frame', image: frame ?? null, mime: 'image/jpeg' });
    });

    return () => {
      unsubState();
      unsubText();
      unsubMedia();
      unsubInterrupt();
      unsubCaptureFrame();
    };
  }, [
    onMessage,
    updateFromState,
    handleTextMessage,
    enqueueAudio,
    stopPlayback,
    clearOnInterrupt,
    captureFrame,
    sendJson,
  ]);

  const handleToggleCamera = useCallback(() => {
    const nowOff = !isCameraOffRef.current;
    isCameraOffRef.current = nowOff;
    setIsCameraOff(nowOff);

    if (nowOff) {
      stopSceneFramePush();
      stopCamera();
      // Inform backend there is no camera frame available
      sendJson({ event: 'frame', image: null, mime: 'image/jpeg' });
    } else {
      startCamera().then(() => {
        startSceneFramePush((frame) => sendJson({ event: 'scene_frame', image: frame }));
      });
    }
  }, [stopSceneFramePush, startSceneFramePush, sendJson, startCamera, stopCamera]);

  const handleStart = useCallback(async () => {
    stopPlayback();
    isCameraOffRef.current = false;
    setIsCameraOff(false);
    await startCamera();
    await startListening();
    setIsActive(true);
    resetQueue();
    startSceneFramePush((frame) => sendJson({ event: 'scene_frame', image: frame }));
  }, [stopPlayback, startCamera, startListening, resetQueue, startSceneFramePush, sendJson]);

  const handleStop = useCallback(() => {
    stopSceneFramePush();
    stopListening();
    stopCamera();
    stopPlayback();
    setIsActive(false);
    setIsBotResponding(false);
    isCameraOffRef.current = false;
    setIsCameraOff(false);
  }, [stopSceneFramePush, stopListening, stopCamera, stopPlayback]);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100vh',
        background: '#0d1117',
        color: '#e5e7eb',
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      }}
    >
      <StatusBar
        isConnected={isConnected}
        isActive={isActive}
        isBotResponding={isBotResponding}
        sessionId={sessionId}
        sessionCount={activeSessionCount}
      />

      <div
        style={{
          flex: 1,
          display: 'grid',
          gridTemplateColumns: '340px 1fr',
          gap: '0',
          overflow: 'hidden',
        }}
      >
        {/* Left panel: camera + controls */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            padding: '16px',
            gap: '12px',
            borderRight: '1px solid #1f2937',
            overflow: 'auto',
          }}
        >
          <VideoPreview
            videoRef={videoRef}
            canvasRef={canvasRef}
            annotationCanvasRef={annotationCanvasRef}
            isCameraActive={isCameraActive}
            isCapturing={isCapturing}
          />

          <AudioVisualizer vadProb={vadProb} speechState={speechState} />

          <StartButton
            isActive={isActive}
            isConnected={isConnected}
            onStart={handleStart}
            onStop={handleStop}
          />

          <MediaControls
            isActive={isActive}
            isMicMuted={isMicMuted}
            isCameraOff={isCameraOff}
            onToggleMic={toggleMicMute}
            onToggleCamera={handleToggleCamera}
          />

          <MetricsDashboard sessionId={sessionId} />
        </div>

        {/* Right panel: conversation thread */}
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
            padding: '0',
          }}
        >
          <div
            style={{
              padding: '12px 16px',
              borderBottom: '1px solid #1f2937',
              fontSize: '13px',
              color: '#6b7280',
            }}
          >
            Conversation
          </div>
          <ConversationThread messages={messages} />
        </div>
      </div>
    </div>
  );
}
