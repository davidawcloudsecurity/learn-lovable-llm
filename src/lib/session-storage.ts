/**
 * Session storage for chat history.
 * Saves the list of past sessions (id + preview) to localStorage
 * so the sidebar survives page refreshes.
 */

const STORAGE_KEY = "learnllm_sessions";

export interface SessionEntry {
  id: string;
  preview: string;      // first user message (truncated)
  createdAt: number;    // Unix timestamp
  updatedAt: number;    // Unix timestamp
}

export function loadSessions(): SessionEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as SessionEntry[];
    // Most recent first
    return parsed.sort((a, b) => b.updatedAt - a.updatedAt);
  } catch {
    return [];
  }
}

export function saveSession(entry: SessionEntry): void {
  const existing = loadSessions().filter((s) => s.id !== entry.id);
  const updated = [entry, ...existing];
  localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
}

export function removeSession(id: string): void {
  const filtered = loadSessions().filter((s) => s.id !== id);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(filtered));
}

export function clearAllSessions(): void {
  localStorage.removeItem(STORAGE_KEY);
}
