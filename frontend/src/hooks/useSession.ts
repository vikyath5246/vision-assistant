import { useState } from 'react';
import { getOrCreateSessionId } from '../utils/session';

export function useSession() {
  const [sessionId] = useState<string>(() => getOrCreateSessionId());
  return { sessionId };
}
