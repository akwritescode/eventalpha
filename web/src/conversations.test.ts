import { deleteConversation, loadConversations, MAX_CONVERSATIONS, saveConversation, titleOf } from './conversations';

const KEY = 'eventalpha.conversations.v1';
const convo = (id: string, text = `question ${id}`) => ({
  id, context: { ticker: 'NVDA' }, replay: false,
  turns: [{ id: 0, role: 'user' as const, text }, { id: 1, role: 'assistant' as const, text: 'answer' }],
});

beforeEach(() => window.localStorage.clear());
afterEach(() => jest.restoreAllMocks());

test('saves newest first, keeps createdAt on update, and drops pending replies', () => {
  saveConversation(convo('a'), new Date('2026-11-24T10:00:00Z'));
  saveConversation(convo('b'), new Date('2026-11-24T11:00:00Z'));
  const updated = saveConversation({ ...convo('a'), turns: [...convo('a').turns,
    { id: 2, role: 'user', text: 'more' }, { id: 3, role: 'assistant', pending: true }] }, new Date('2026-11-24T12:00:00Z'));
  expect(updated.map(c => c.id)).toEqual(['a', 'b']);
  expect(updated[0].createdAt).toBe('2026-11-24T10:00:00.000Z');
  expect(updated[0].turns).toHaveLength(3);
  expect(loadConversations().map(c => c.id)).toEqual(['a', 'b']);
});

test('titles come from the first question, shortened', () => {
  expect(titleOf(convo('a', 'Why did NVDA move?').turns)).toBe('Why did NVDA move?');
  expect(titleOf(convo('a', 'x'.repeat(80)).turns)).toHaveLength(60);
});

test('keeps at most MAX_CONVERSATIONS and deletes by id', () => {
  for (let i = 0; i < MAX_CONVERSATIONS + 3; i++) saveConversation(convo(`c${i}`), new Date(Date.UTC(2026, 10, 24, 0, i)));
  expect(loadConversations()).toHaveLength(MAX_CONVERSATIONS);
  expect(deleteConversation('c32').map(c => c.id)).not.toContain('c32');
});

test('deleting the last conversation clears storage', () => {
  saveConversation(convo('only'));
  expect(deleteConversation('only')).toEqual([]);
  expect(loadConversations()).toEqual([]);
});

test('ignores corrupt storage and drops the oldest conversations when the quota is full', () => {
  window.localStorage.setItem(KEY, '{not json');
  expect(loadConversations()).toEqual([]);
  window.localStorage.setItem(KEY, JSON.stringify([{ id: 1 }, null, 'x']));
  expect(loadConversations()).toEqual([]);

  saveConversation(convo('old'), new Date('2026-11-24T10:00:00Z'));
  // Only a single conversation fits: the first write (two conversations) fails, the retry succeeds.
  const setItem = jest.spyOn(Storage.prototype, 'setItem').mockImplementation((_key, value) => {
    if (JSON.parse(value).length > 1) throw new DOMException('full', 'QuotaExceededError');
  });
  const kept = saveConversation(convo('new'), new Date('2026-11-24T11:00:00Z'));
  expect(kept.map(c => c.id)).toEqual(['new']);
  expect(setItem).toHaveBeenCalledTimes(2);
});
