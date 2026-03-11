/**
 * TypeScript interfaces for all WebSocket message types
 */

// ---- Server → Client ----

export interface StateMessage {
  event: 'state';
  state: 'quiet' | 'starting' | 'speaking' | 'stopping';
  vad_prob: number;
  listening: boolean;
  responding: boolean;
  segments: number;
}

export interface TextMessage {
  event: 'text';
  role: 'user' | 'assistant';
  text: string;
  partial?: boolean;
  complete?: boolean;
  streaming?: boolean;
  segment_id?: number;
}

export interface MediaMessage {
  event: 'media';
  mime: string;
  audio: string; // base64 WAV
  index: number;
}

export interface MetricsMessage {
  event: 'metrics';
  metrics: {
    stt?: { status?: string; segment_id?: number; latency_ms?: number };
    llm?: { first_token_ms?: number };
    tts?: { first_audio_ms?: number };
  };
}

export interface ErrorMessage {
  event: 'error';
  message: string;
  step: string;
}

export interface SpeechEventMessage {
  event: 'speech_start' | 'speech_end' | 'interrupt' | 'capture_frame';
}

export interface AnnotationBox {
  label: string;
  confidence: number;
  x1: number; // normalized 0..1 (unmirrored)
  y1: number;
  x2: number;
  y2: number;
}

export interface AnnotationsMessage {
  event: 'annotations';
  boxes: AnnotationBox[];
  timestamp: number;
}

export type ServerMessage =
  | StateMessage
  | TextMessage
  | MediaMessage
  | MetricsMessage
  | ErrorMessage
  | SpeechEventMessage
  | AnnotationsMessage;

// ---- Client state ----

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  isStreaming?: boolean;
  isPartial?: boolean;
  timestamp: Date;
}

export interface PipelineMetrics {
  stt_latency_ms?: number;
  llm_first_token_ms?: number;
  tts_first_audio_ms?: number;
}

export interface ComponentHealth {
  vad: string;
  transcriber: string;
  vision_api: string;
  tts: string;
  database: string;
}
