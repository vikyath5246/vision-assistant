interface Props {
  vadProb: number;       // 0–1
  speechState: string;   // quiet | starting | speaking | stopping
}

const stateColors: Record<string, string> = {
  quiet: '#374151',
  starting: '#f59e0b',
  speaking: '#10b981',
  stopping: '#6366f1',
};

const stateLabels: Record<string, string> = {
  quiet: 'Listening',
  starting: 'Detecting...',
  speaking: 'Speaking',
  stopping: 'Processing...',
};

export function AudioVisualizer({ vadProb, speechState }: Props) {
  const color = stateColors[speechState] ?? '#374151';
  const label = stateLabels[speechState] ?? speechState;
  const barWidth = Math.max(2, Math.round(vadProb * 100));

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 0' }}>
      <div style={{ fontSize: '12px', color: '#9ca3af', width: '90px', textAlign: 'right' }}>
        {label}
      </div>
      <div
        style={{
          flex: 1,
          height: '8px',
          background: '#1f2937',
          borderRadius: '4px',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            height: '100%',
            width: `${barWidth}%`,
            background: color,
            borderRadius: '4px',
            transition: 'width 0.08s ease, background 0.2s ease',
          }}
        />
      </div>
      <div style={{ fontSize: '11px', color: '#6b7280', width: '36px' }}>
        {Math.round(vadProb * 100)}%
      </div>
    </div>
  );
}
