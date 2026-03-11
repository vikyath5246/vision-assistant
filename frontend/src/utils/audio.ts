/**
 * Audio encoding/decoding utilities
 * Ported from offline-voice-ai/index.html
 */

export function float32ToBase64(buffer: Float32Array): string {
  const bytes = new Uint8Array(buffer.buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

export function base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

export async function decodeWavToAudioBuffer(
  base64wav: string,
  audioCtx: AudioContext
): Promise<AudioBuffer> {
  const arrayBuffer = base64ToArrayBuffer(base64wav);
  return audioCtx.decodeAudioData(arrayBuffer);
}
