import { useCallback, useEffect, useRef } from 'react';

interface UseStreamingSpeechOptions {
  lang?: string;
  onSpeakingChange?: (speaking: boolean) => void;
}

const SENTENCE_DELIMITERS = new Set(['.', '!', '?', '\n']);

export function useStreamingSpeech(options: UseStreamingSpeechOptions = {}) {
  const synthRef = useRef<SpeechSynthesis | null>(null);
  const queueRef = useRef<string[]>([]);
  const bufferRef = useRef('');
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);
  const speakingRef = useRef(false);

  const isSupported =
    typeof window !== 'undefined' &&
    typeof window.speechSynthesis !== 'undefined' &&
    typeof SpeechSynthesisUtterance !== 'undefined';

  const setSpeaking = useCallback((speaking: boolean) => {
    if (speakingRef.current === speaking) return;
    speakingRef.current = speaking;
    options.onSpeakingChange?.(speaking);
  }, [options]);

  const speakNext = useCallback(() => {
    const synth = synthRef.current;
    if (!synth) return;

    const text = queueRef.current.shift();
    if (!text) {
      utteranceRef.current = null;
      setSpeaking(false);
      return;
    }

    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = options.lang ?? 'en-US';
    utterance.onend = () => {
      if (utteranceRef.current !== utterance) return;
      utteranceRef.current = null;
      speakNext();
    };
    utterance.onerror = () => {
      if (utteranceRef.current !== utterance) return;
      utteranceRef.current = null;
      speakNext();
    };

    utteranceRef.current = utterance;
    setSpeaking(true);
    synth.speak(utterance);
  }, [options.lang, setSpeaking]);

  const enqueueSpeak = useCallback((text: string) => {
    const cleaned = text.trim();
    if (!isSupported || !cleaned) return;

    queueRef.current.push(cleaned);
    if (!utteranceRef.current) {
      speakNext();
    }
  }, [isSupported, speakNext]);

  const flushCompleteSentences = useCallback(() => {
    let buffer = bufferRef.current;
    while (buffer.length > 0) {
      let splitIndex = -1;
      for (let i = 0; i < buffer.length; i += 1) {
        if (SENTENCE_DELIMITERS.has(buffer[i])) {
          splitIndex = i;
          break;
        }
      }

      if (splitIndex === -1) break;

      const sentence = buffer.slice(0, splitIndex + 1).trim();
      buffer = buffer.slice(splitIndex + 1);
      if (sentence) enqueueSpeak(sentence);
    }

    bufferRef.current = buffer;
  }, [enqueueSpeak]);

  const onStreamChunk = useCallback((chunk: string) => {
    if (!isSupported || !chunk) return;
    bufferRef.current += chunk;
    flushCompleteSentences();
  }, [isSupported, flushCompleteSentences]);

  const onStreamComplete = useCallback((fullText?: string) => {
    if (!isSupported) return;

    flushCompleteSentences();
    const trailing = bufferRef.current.trim();
    if (trailing) {
      enqueueSpeak(trailing);
      bufferRef.current = '';
      return;
    }

    // Fallback for cases where stream events were skipped and only complete arrived.
    if (!utteranceRef.current && queueRef.current.length === 0 && fullText?.trim()) {
      enqueueSpeak(fullText);
    }
  }, [enqueueSpeak, flushCompleteSentences, isSupported]);

  const interrupt = useCallback(() => {
    bufferRef.current = '';
    queueRef.current = [];
    utteranceRef.current = null;
    synthRef.current?.cancel();
    setSpeaking(false);
  }, [setSpeaking]);

  useEffect(() => {
    if (!isSupported) return undefined;
    synthRef.current = window.speechSynthesis;
    return () => {
      synthRef.current?.cancel();
      synthRef.current = null;
      queueRef.current = [];
      bufferRef.current = '';
      utteranceRef.current = null;
      setSpeaking(false);
    };
  }, [isSupported, setSpeaking]);

  return {
    isSupported,
    onStreamChunk,
    onStreamComplete,
    interrupt,
  };
}
