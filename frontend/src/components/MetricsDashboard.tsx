import { useEffect, useRef, useState } from 'react';
import { ComponentHealth, PipelineMetrics } from '../types/messages';

interface DashboardEvent {
  type: string;
  session_id?: string;
  stt_latency_ms?: number;
  llm_first_token_ms?: number;
  tts_first_audio_ms?: number;
  active_sessions?: string[];
}

interface Props {
  sessionId: string;
}

export function MetricsDashboard({ sessionId }: Props) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [metrics, setMetrics] = useState<PipelineMetrics>({});
  const [health, setHealth] = useState<ComponentHealth | null>(null);
  const [activeSessions, setActiveSessions] = useState<string[]>([]);
  const esRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!isExpanded) return;

    // Fetch health status
    fetch('/health')
      .then((r) => r.json())
      .then((data) => {
        setHealth(data.components);
        setActiveSessions(data.session_ids || []);
      })
      .catch(console.error);

    // Connect to SSE for real-time metrics
    esRef.current = new EventSource('/dashboard/events');
    esRef.current.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data) as DashboardEvent;
        if (event.type === 'connected') {
          setActiveSessions(event.active_sessions || []);
        } else if (event.type === 'turn_complete' && event.session_id === sessionId) {
          setMetrics({
            stt_latency_ms: event.stt_latency_ms,
            llm_first_token_ms: event.llm_first_token_ms,
            tts_first_audio_ms: event.tts_first_audio_ms,
          });
        }
      } catch {
        // ignore parse errors
      }
    };

    return () => {
      esRef.current?.close();
    };
  }, [isExpanded, sessionId]);

  const healthColor = (status: string) => {
    if (status === 'ok') return '#10b981';
    if (status === 'disabled' || status === 'not_configured') return '#6b7280';
    return '#ef4444';
  };

  return (
    <div style={{ borderTop: '1px solid #1f2937', marginTop: '4px' }}>
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        style={{
          width: '100%',
          padding: '8px 12px',
          background: 'transparent',
          border: 'none',
          cursor: 'pointer',
          color: '#9ca3af',
          fontSize: '12px',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
        }}
      >
        <span>{isExpanded ? '▲' : '▼'}</span>
        <span>Observability Dashboard</span>
      </button>

      {isExpanded && (
        <div style={{ padding: '12px', background: '#0f172a', fontSize: '12px' }}>
          {/* Component Health */}
          {health && (
            <div style={{ marginBottom: '12px' }}>
              <div style={{ color: '#9ca3af', marginBottom: '6px', fontWeight: 600 }}>Pipeline Status</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px' }}>
                {Object.entries(health).map(([key, status]) => (
                  <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#e5e7eb' }}>
                    <div style={{ width: '7px', height: '7px', borderRadius: '50%', background: healthColor(status), flexShrink: 0 }} />
                    <span style={{ textTransform: 'capitalize' }}>{key.replace('_', ' ')}</span>
                    <span style={{ color: '#6b7280', marginLeft: 'auto' }}>{status}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Latency Metrics */}
          <div style={{ marginBottom: '12px' }}>
            <div style={{ color: '#9ca3af', marginBottom: '6px', fontWeight: 600 }}>Last Turn Latency</div>
            <MetricRow label="STT" value={metrics.stt_latency_ms} unit="ms" />
            <MetricRow label="LLM First Token" value={metrics.llm_first_token_ms} unit="ms" />
            <MetricRow label="TTS First Audio" value={metrics.tts_first_audio_ms} unit="ms" />
          </div>

          {/* Active Sessions */}
          <div>
            <div style={{ color: '#9ca3af', marginBottom: '6px', fontWeight: 600 }}>
              Active Sessions ({activeSessions.length})
            </div>
            {activeSessions.length === 0 ? (
              <div style={{ color: '#4b5563' }}>None</div>
            ) : (
              activeSessions.map((id) => (
                <div key={id} style={{ color: id === sessionId ? '#60a5fa' : '#e5e7eb', fontSize: '11px' }}>
                  {id.slice(0, 12)}... {id === sessionId ? '(you)' : ''}
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function MetricRow({ label, value, unit }: { label: string; value?: number; unit: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', color: '#e5e7eb', padding: '2px 0' }}>
      <span style={{ color: '#9ca3af' }}>{label}</span>
      <span>{value != null ? `${value}${unit}` : '—'}</span>
    </div>
  );
}
