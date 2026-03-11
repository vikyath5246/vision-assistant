import { useCallback, useEffect, useRef, useState } from 'react';
import { ServerMessage } from '../types/messages';

type MessageHandler = (message: ServerMessage) => void;

export function useWebSocket(sessionId: string) {
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const handlersRef = useRef<Map<string, MessageHandler[]>>(new Map());
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectDelayRef = useRef(1000);
  const shouldReconnectRef = useRef(true);

  const connect = useCallback(() => {
    if (!shouldReconnectRef.current) return;

    // Avoid parallel sockets for the same session
    const existing = wsRef.current;
    if (
      existing &&
      (existing.readyState === WebSocket.CONNECTING || existing.readyState === WebSocket.OPEN)
    ) {
      return;
    }

    const wsUrl = `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/${sessionId}`;
    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      if (wsRef.current !== ws) return;
      console.log('[ws] Connected');
      setIsConnected(true);
      reconnectDelayRef.current = 1000; // Reset backoff
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
        reconnectTimerRef.current = null;
      }
    };

    ws.onmessage = (evt) => {
      if (wsRef.current !== ws) return;
      try {
        const msg = JSON.parse(evt.data) as ServerMessage;
        const handlers = handlersRef.current.get(msg.event) || [];
        handlers.forEach((h) => h(msg));
        // Also call wildcard handlers
        const wildcardHandlers = handlersRef.current.get('*') || [];
        wildcardHandlers.forEach((h) => h(msg));
      } catch (e) {
        console.warn('[ws] Failed to parse message:', e);
      }
    };

    ws.onerror = (e) => {
      if (wsRef.current !== ws) return;
      console.error('[ws] Error:', e);
    };

    ws.onclose = () => {
      if (wsRef.current === ws) {
        wsRef.current = null;
        setIsConnected(false);
      }

      if (!shouldReconnectRef.current) return;

      console.log('[ws] Disconnected');
      // Exponential backoff reconnect
      reconnectTimerRef.current = setTimeout(() => {
        reconnectDelayRef.current = Math.min(reconnectDelayRef.current * 2, 10000);
        connect();
      }, reconnectDelayRef.current);
    };
  }, [sessionId]);

  useEffect(() => {
    shouldReconnectRef.current = true;
    connect();

    return () => {
      shouldReconnectRef.current = false;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
      const ws = wsRef.current;
      wsRef.current = null;
      ws?.close();
    };
  }, [connect]);

  const sendJson = useCallback((payload: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(payload));
    }
  }, []);

  const onMessage = useCallback((eventType: string, handler: MessageHandler): (() => void) => {
    const existing = handlersRef.current.get(eventType) || [];
    handlersRef.current.set(eventType, [...existing, handler]);
    return () => {
      const current = handlersRef.current.get(eventType) || [];
      handlersRef.current.set(eventType, current.filter((h) => h !== handler));
    };
  }, []);

  return { isConnected, sendJson, onMessage };
}
