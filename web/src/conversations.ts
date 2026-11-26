// Ask EventAlpha conversations, kept in this browser's localStorage (no accounts yet).
// Everything here tolerates storage that is full, corrupt or unavailable (private mode,
// blocked site data): the chat then still works, it just isn't remembered.
import type { Explanation, WebSearch } from './components/MoveResult';
import type { MoveWindow, TickerOption } from './moveInput';

export type Turn =
  | { id: number; role: 'user'; text: string }
  | { id: number; role: 'assistant'; text?: string; result?: Explanation; options?: TickerOption[]; pending?: boolean;
      web?: WebSearch };

/** The ticker and window the chat is about, so a reopened conversation can be continued. */
export type ChatContext = { ticker?: string; name?: string; window?: MoveWindow };

export type Conversation = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  turns: Turn[];
  context: ChatContext;
  replay: boolean;
};

const KEY = 'eventalpha.conversations.v1';
export const MAX_CONVERSATIONS = 30;
const MAX_TITLE = 60;

export const newConversationId = () => `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

export function titleOf(turns: Turn[]): string {
  const first = turns.find(t => t.role === 'user');
  const text = first && first.role === 'user' ? first.text.trim() : 'New conversation';
  return text.length > MAX_TITLE ? `${text.slice(0, MAX_TITLE - 1)}…` : text;
}

function isConversation(value: unknown): value is Conversation {
  const c = value as Conversation;
  return !!c && typeof c.id === 'string' && typeof c.title === 'string' && typeof c.updatedAt === 'string'
    && Array.isArray(c.turns) && typeof c.context === 'object' && c.context !== null;
}

/** Newest first. */
export function loadConversations(): Conversation[] {
  try {
    const parsed: unknown = JSON.parse(window.localStorage.getItem(KEY) || '[]');
    return Array.isArray(parsed)
      ? parsed.filter(isConversation).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt))
      : [];
  } catch {
    return [];
  }
}

/** Writes the list, dropping the oldest conversations if the browser's quota is exceeded. */
function write(list: Conversation[]): Conversation[] {
  // Always attempt at least once, so deleting the last conversation clears storage too.
  for (let kept = list; ; kept = kept.slice(0, -1)) {
    try {
      window.localStorage.setItem(KEY, JSON.stringify(kept));
      return kept;
    } catch {
      // Full or unavailable: retry with fewer conversations, down to none.
      if (kept.length === 0) return list; // storage unusable: keep the list in memory for this visit
    }
  }
}

/** Inserts or replaces a conversation (moving it to the top); returns the stored list. */
export function saveConversation(conversation: Omit<Conversation, 'title' | 'createdAt' | 'updatedAt'>, now = new Date()): Conversation[] {
  const existing = loadConversations();
  const previous = existing.find(c => c.id === conversation.id);
  const turns = conversation.turns.filter(t => !(t.role === 'assistant' && t.pending));
  const saved: Conversation = {
    ...conversation,
    turns,
    title: titleOf(turns),
    createdAt: previous?.createdAt || now.toISOString(),
    updatedAt: now.toISOString(),
  };
  return write([saved, ...existing.filter(c => c.id !== conversation.id)].slice(0, MAX_CONVERSATIONS));
}

export function deleteConversation(id: string): Conversation[] {
  return write(loadConversations().filter(c => c.id !== id));
}
