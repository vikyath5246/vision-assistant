/**
 * TTS audio playback queue
 * Plays WAV audio chunks in order as they arrive from server
 * Ported from offline-voice-ai/index.html playback logic
 */
import { useCallback, useRef, useState } from 'react';
import { decodeWavToAudioBuffer } from '../utils/audio';

interface QueueItem {
  index: number;
  audioBuffer: AudioBuffer;
}

export function useTTSPlayback(onBotSpeakingChange?: (speaking: boolean) => void) {
  const [isPlaying, setIsPlaying] = useState(false);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const queueRef = useRef<QueueItem[]>([]);
  const playingRef = useRef(false);
  const nextIndexRef = useRef(0);
  const stopRequestedRef = useRef(false);
  const sourceRef = useRef<AudioBufferSourceNode | null>(null);

  const stopCurrentSource = useCallback(() => {
    const source = sourceRef.current;
    sourceRef.current = null;
    if (!source) return;
    source.onended = null;
    try {
      source.stop();
    } catch {
      // Ignore invalid-state stop calls.
    }
  }, []);

  const getOrCreateAudioCtx = useCallback((): AudioContext => {
    if (!audioCtxRef.current || audioCtxRef.current.state === 'closed') {
      audioCtxRef.current = new AudioContext();
    }
    if (audioCtxRef.current.state === 'suspended') {
      audioCtxRef.current.resume();
    }
    return audioCtxRef.current;
  }, []);

  const playNext = useCallback(() => {
    if (stopRequestedRef.current) {
      stopCurrentSource();
      queueRef.current = [];
      nextIndexRef.current = 0;
      playingRef.current = false;
      setIsPlaying(false);
      onBotSpeakingChange?.(false);
      return;
    }

    const sorted = queueRef.current.sort((a, b) => a.index - b.index);
    const next = sorted.find((item) => item.index === nextIndexRef.current);

    if (!next) {
      playingRef.current = false;
      setIsPlaying(false);
      onBotSpeakingChange?.(false);
      return;
    }

    queueRef.current = queueRef.current.filter((item) => item !== next);
    nextIndexRef.current++;

    const ctx = getOrCreateAudioCtx();
    const source = ctx.createBufferSource();
    sourceRef.current = source;
    source.buffer = next.audioBuffer;
    source.connect(ctx.destination);

    source.onended = () => {
      if (sourceRef.current === source) {
        sourceRef.current = null;
      }
      playNext();
    };

    source.start();
  }, [getOrCreateAudioCtx, onBotSpeakingChange, stopCurrentSource]);

  const enqueueAudio = useCallback(async (base64wav: string, index: number) => {
    if (stopRequestedRef.current) return;
    stopRequestedRef.current = false;

    try {
      // Server starts each assistant turn at index 0.
      // Reset ordering so a new response never waits on stale indices.
      if (index === 0) {
        stopCurrentSource();
        queueRef.current = [];
        nextIndexRef.current = 0;
        playingRef.current = false;
        setIsPlaying(false);
        onBotSpeakingChange?.(false);
      }

      const ctx = getOrCreateAudioCtx();
      const audioBuffer = await decodeWavToAudioBuffer(base64wav, ctx);
      queueRef.current.push({ index, audioBuffer });

      if (!playingRef.current) {
        playingRef.current = true;
        setIsPlaying(true);
        onBotSpeakingChange?.(true);
        playNext();
      }
    } catch (e) {
      console.error('[tts] Failed to decode WAV:', e);
    }
  }, [getOrCreateAudioCtx, playNext, onBotSpeakingChange, stopCurrentSource]);

  const stopPlayback = useCallback(() => {
    stopRequestedRef.current = true;
    stopCurrentSource();
    queueRef.current = [];
    nextIndexRef.current = 0;
    playingRef.current = false;
    setIsPlaying(false);
    onBotSpeakingChange?.(false);

    // Reset stop flag after brief delay so next TTS can play
    setTimeout(() => {
      stopRequestedRef.current = false;
    }, 200);
  }, [onBotSpeakingChange, stopCurrentSource]);

  const resetQueue = useCallback(() => {
    queueRef.current = [];
    nextIndexRef.current = 0;
    stopRequestedRef.current = false;
  }, []);

  return { isPlaying, enqueueAudio, stopPlayback, resetQueue };
}
