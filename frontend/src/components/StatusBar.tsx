interface Props {
  isConnected: boolean;
  isActive: boolean;    // conversation started
  isBotResponding: boolean;
  sessionId: string;
  sessionCount?: number; // number of active sessions across all tabs
}

export function StatusBar({ isConnected, isActive, isBotResponding, sessionId, sessionCount }: Props) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '8px 16px',
        background: '#111827',
        borderBottom: '1px solid #1f2937',
        fontSize: '12px',
        color: '#9ca3af',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
        <div
          style={{
            width: '8px',
            height: '8px',
            borderRadius: '50%',
            background: isConnected ? '#10b981' : '#ef4444',
          }}
        />
        <span>{isConnected ? 'Connected' : 'Disconnected'}</span>
      </div>

      <div style={{ fontWeight: 600, color: '#e5e7eb', fontSize: '13px' }}>
        Vision Assistant
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        {isActive && (
          <span
            style={{
              padding: '2px 8px',
              borderRadius: '9999px',
              background: isBotResponding ? '#1d4ed8' : '#065f46',
              color: '#fff',
              fontSize: '11px',
            }}
          >
            {isBotResponding ? 'Responding' : 'Listening'}
          </span>
        )}
        {sessionCount !== undefined && sessionCount > 1 && (
          <span
            style={{
              padding: '2px 8px',
              borderRadius: '9999px',
              background: '#374151',
              color: '#9ca3af',
              fontSize: '11px',
            }}
          >
            {sessionCount} sessions active
          </span>
        )}
        <span style={{ color: '#4b5563' }}>
          Session: {sessionId.slice(0, 8)}...
        </span>
      </div>
    </div>
  );
}
