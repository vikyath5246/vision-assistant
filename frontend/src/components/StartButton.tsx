interface Props {
  isActive: boolean;
  isConnected: boolean;
  onStart: () => void;
  onStop: () => void;
}

export function StartButton({ isActive, isConnected, onStart, onStop }: Props) {
  return (
    <button
      onClick={isActive ? onStop : onStart}
      disabled={!isConnected}
      style={{
        width: '100%',
        padding: '14px',
        borderRadius: '10px',
        border: 'none',
        cursor: isConnected ? 'pointer' : 'not-allowed',
        fontWeight: 700,
        fontSize: '15px',
        transition: 'all 0.2s ease',
        background: isActive
          ? '#dc2626'
          : isConnected
          ? '#2563eb'
          : '#374151',
        color: '#fff',
        opacity: isConnected ? 1 : 0.5,
      }}
    >
      {isActive ? '⏹ Stop Conversation' : '▶ Start Conversation'}
    </button>
  );
}
