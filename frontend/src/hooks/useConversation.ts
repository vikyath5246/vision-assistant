import { useCallback, useRef, useState } from 'react';
import { Message, TextMessage } from '../types/messages';

function makeId() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function useConversation() {
  const [messages, setMessages] = useState<Message[]>([]);
  const streamingIdRef = useRef<string | null>(null);

  const handleTextMessage = useCallback((msg: TextMessage) => {
    if (msg.role === 'user') {
      if (msg.partial) {
        // Show partial transcription in real-time
        setMessages((prev) => {
          const lastUserIdx = [...prev].reverse().findIndex((m) => m.role === 'user' && m.isPartial);
          if (lastUserIdx >= 0) {
            const realIdx = prev.length - 1 - lastUserIdx;
            const updated = [...prev];
            updated[realIdx] = { ...updated[realIdx], content: msg.text };
            return updated;
          }
          // New partial message
          return [...prev, { id: makeId(), role: 'user', content: msg.text, isPartial: true, timestamp: new Date() }];
        });
      } else if (msg.complete) {
        // Replace partial with final
        setMessages((prev) => {
          const lastPartialIdx = [...prev].reverse().findIndex((m) => m.role === 'user' && m.isPartial);
          if (lastPartialIdx >= 0) {
            const realIdx = prev.length - 1 - lastPartialIdx;
            const updated = [...prev];
            updated[realIdx] = { ...updated[realIdx], content: msg.text, isPartial: false };
            return updated;
          }
          return [...prev, { id: makeId(), role: 'user', content: msg.text, timestamp: new Date() }];
        });
      }
    } else if (msg.role === 'assistant') {
      if (msg.streaming) {
        // Assign streaming id outside the updater so it's never a side-effect
        // inside a pure setState call (React 18 Strict Mode calls updaters twice).
        if (!streamingIdRef.current) {
          streamingIdRef.current = makeId();
        }
        const id = streamingIdRef.current;
        setMessages((prev) => {
          const exists = prev.some((m) => m.id === id);
          if (exists) {
            return prev.map((m) =>
              m.id === id ? { ...m, content: m.content + msg.text } : m
            );
          }
          // First chunk: create the streaming message bubble
          return [...prev, { id, role: 'assistant', content: msg.text, isStreaming: true, timestamp: new Date() }];
        });
      } else if (msg.complete) {
        // Capture and clear ref outside the updater
        const completingId = streamingIdRef.current;
        streamingIdRef.current = null;
        setMessages((prev) => {
          if (completingId) {
            return prev.map((m) =>
              m.id === completingId ? { ...m, content: msg.text, isStreaming: false } : m
            );
          }
          // No streaming message in progress — add as a standalone bubble
          return [...prev, { id: makeId(), role: 'assistant', content: msg.text, timestamp: new Date() }];
        });
      }
    }
  }, []);

  const clearOnInterrupt = useCallback(() => {
    setMessages((prev) => {
      if (!streamingIdRef.current) return prev;
      const activeId = streamingIdRef.current;
      streamingIdRef.current = null;
      return prev.map((m) =>
        m.id === activeId ? { ...m, isStreaming: false } : m
      );
    });
  }, []);

  const clearConversation = useCallback(() => {
    setMessages([]);
    streamingIdRef.current = null;
  }, []);

  return { messages, handleTextMessage, clearOnInterrupt, clearConversation };
}
