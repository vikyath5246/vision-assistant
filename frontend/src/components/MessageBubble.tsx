import { Message } from '../types/messages';

interface Props {
  message: Message;
}

export function MessageBubble({ message }: Props) {
  const isUser = message.role === 'user';

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: isUser ? 'flex-end' : 'flex-start',
        marginBottom: '12px',
        padding: '0 8px',
      }}
    >
      <div
        style={{
          maxWidth: '70%',
          padding: '10px 14px',
          borderRadius: isUser ? '18px 18px 4px 18px' : '18px 18px 18px 4px',
          background: isUser ? '#2563eb' : '#374151',
          color: '#fff',
          fontSize: '14px',
          lineHeight: '1.5',
          opacity: message.isPartial ? 0.7 : 1,
          fontStyle: message.isPartial ? 'italic' : 'normal',
          position: 'relative',
        }}
      >
        {!isUser && (
          <div style={{ fontSize: '11px', color: '#9ca3af', marginBottom: '4px', fontWeight: 600 }}>
            Assistant
            {message.isStreaming && (
              <span style={{ marginLeft: '6px', animation: 'pulse 1s infinite' }}>...</span>
            )}
          </div>
        )}
        <div>{message.content || (message.isPartial ? '...' : '')}</div>
        <div style={{ fontSize: '11px', color: 'rgba(255,255,255,0.5)', marginTop: '4px', textAlign: 'right' }}>
          {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>
    </div>
  );
}
