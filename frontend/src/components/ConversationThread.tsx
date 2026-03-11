import { useEffect, useRef } from 'react';
import { Message } from '../types/messages';
import { MessageBubble } from './MessageBubble';

interface Props {
  messages: Message[];
}

export function ConversationThread({ messages }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div
      style={{
        flex: 1,
        overflowY: 'auto',
        padding: '16px 0',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {messages.length === 0 ? (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100%',
            color: '#6b7280',
            fontSize: '14px',
            textAlign: 'center',
            padding: '24px',
          }}
        >
          Point your camera at something and start talking.
          <br />
          The assistant will respond in the chat.
        </div>
      ) : (
        messages.map((msg) => <MessageBubble key={msg.id} message={msg} />)
      )}
      <div ref={bottomRef} />
    </div>
  );
}
