/**
 * Audio capture pipeline: mic → AudioWorklet → 512-sample Float32 chunks → WebSocket
 * Ported from offline-voice-ai/index.html
 */
import { useCallback, useRef, useState } from 'react';
import { float32ToBase64 } from '../utils/audio';

const SAMPLE_RATE = 16000;
const CHUNK_SIZE = 512;
// Barge-in: if correlation with TTS > this threshold, user is speaking over bot
const BARGE_IN_CORR_THRESHOLD = 0.3;
const BARGE_IN_MIC_RMS_THRESHOLD = 0.01;

export function useAudioPipeline(
  sendJson: (payload: object) => void,
  onBotInterrupt?: () => void
) {
  const [isListening, setIsListening] = useState(false);
  const [vadProb, setVadProb] = useState(0);
  const [speechState, setSpeechState] = useState<string>('quiet');

  const audioCtxRef = useRef<AudioContext | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  const processorNodeRef = useRef<ScriptProcessorNode | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const isBotSpeakingRef = useRef(false);
  const accumulatorRef = useRef<Float32Array>(new Float32Array(0));

  const startListening = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: SAMPLE_RATE,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });
      micStreamRef.current = stream;

      const ctx = new AudioContext({ sampleRate: SAMPLE_RATE });
      audioCtxRef.current = ctx;

      // Load AudioWorklet for echo correlation (optional - falls back gracefully)
      let workletLoaded = false;
      try {
        await ctx.audioWorklet.addModule('/correlator.worklet.js');
        workletLoaded = true;
      } catch (e) {
        console.warn('[audio] AudioWorklet not available, skipping echo detection');
      }

      const micSource = ctx.createMediaStreamSource(stream);

      if (workletLoaded) {
        const correlator = new AudioWorkletNode(ctx, 'correlator');
        workletNodeRef.current = correlator;

        correlator.port.onmessage = (e) => {
          const { corr, micRms } = e.data as { corr: number; micRms: number; refRms: number };
          // Barge-in detection: user speaking while bot is playing TTS
          if (isBotSpeakingRef.current && corr > BARGE_IN_CORR_THRESHOLD && micRms > BARGE_IN_MIC_RMS_THRESHOLD) {
            console.log('[audio] Barge-in detected, interrupting bot');
            sendJson({ event: 'interrupt' });
            isBotSpeakingRef.current = false;
            onBotInterrupt?.();
          }
        };

        micSource.connect(correlator);
      }

      // ScriptProcessor to accumulate and send audio chunks
      const scriptProcessor = ctx.createScriptProcessor(CHUNK_SIZE, 1, 1);
      processorNodeRef.current = scriptProcessor;

      scriptProcessor.onaudioprocess = (e) => {
        const inputData = e.inputBuffer.getChannelData(0);
        const chunk = new Float32Array(inputData);

        // Accumulate until we have a full CHUNK_SIZE worth
        const combined = new Float32Array(accumulatorRef.current.length + chunk.length);
        combined.set(accumulatorRef.current);
        combined.set(chunk, accumulatorRef.current.length);
        accumulatorRef.current = combined;

        while (accumulatorRef.current.length >= CHUNK_SIZE) {
          const toSend = accumulatorRef.current.slice(0, CHUNK_SIZE);
          accumulatorRef.current = accumulatorRef.current.slice(CHUNK_SIZE);
          sendJson({ event: 'media', audio: float32ToBase64(toSend) });
        }
      };

      micSource.connect(scriptProcessor);
      scriptProcessor.connect(ctx.destination);

      setIsListening(true);
      sendJson({ event: 'start' });
    } catch (e) {
      console.error('[audio] Failed to start microphone:', e);
    }
  }, [sendJson, onBotInterrupt]);

  const stopListening = useCallback(() => {
    sendJson({ event: 'stop' });
    setIsListening(false);

    processorNodeRef.current?.disconnect();
    processorNodeRef.current = null;

    workletNodeRef.current?.disconnect();
    workletNodeRef.current = null;

    micStreamRef.current?.getTracks().forEach((t) => t.stop());
    micStreamRef.current = null;

    audioCtxRef.current?.close();
    audioCtxRef.current = null;

    accumulatorRef.current = new Float32Array(0);
  }, [sendJson]);

  const setBotSpeaking = useCallback((speaking: boolean) => {
    isBotSpeakingRef.current = speaking;
  }, []);

  const updateFromState = useCallback((vad: number, state: string) => {
    setVadProb(vad);
    setSpeechState(state);
  }, []);

  return {
    isListening,
    vadProb,
    speechState,
    startListening,
    stopListening,
    setBotSpeaking,
    updateFromState
  };
}
