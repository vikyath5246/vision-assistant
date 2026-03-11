import type { CSSProperties } from 'react';

interface Props {
  isActive: boolean;
  isMicMuted: boolean;
  isCameraOff: boolean;
  onToggleMic: () => void;
  onToggleCamera: () => void;
}

const btnStyle = (active: boolean): CSSProperties => ({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  gap: '6px',
  flex: 1,
  padding: '10px',
  borderRadius: '8px',
  border: `1px solid ${active ? '#ef4444' : '#374151'}`,
  background: active ? 'rgba(239,68,68,0.12)' : '#1f2937',
  color: active ? '#ef4444' : '#9ca3af',
  fontSize: '13px',
  fontWeight: 600,
  cursor: 'pointer',
  transition: 'all 0.15s ease',
});

export function MediaControls({ isActive, isMicMuted, isCameraOff, onToggleMic, onToggleCamera }: Props) {
  if (!isActive) return null;

  return (
    <div style={{ display: 'flex', gap: '8px' }}>
      <button style={btnStyle(isMicMuted)} onClick={onToggleMic}>
        {isMicMuted ? '🔇' : '🎤'}
        {isMicMuted ? 'Mic Off' : 'Mic On'}
      </button>
      <button style={btnStyle(isCameraOff)} onClick={onToggleCamera}>
        {isCameraOff ? '📵' : '📷'}
        {isCameraOff ? 'Cam Off' : 'Cam On'}
      </button>
    </div>
  );
}
