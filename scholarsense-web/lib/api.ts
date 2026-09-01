const BASE = process.env.NEXT_PUBLIC_API_URL;

export interface BudgetCategory {
  name: string;
  budget: number;
  spent: number;
  remaining?: number;
  spentPct?: number;
}

export interface Budget {
  userId?: string;
  timeline?: { start: string; end: string };
  categories: BudgetCategory[];
  totalBudget?: number;
  totalSpent?: number;
  elapsedPct?: number;
  warnings?: string[];
  message?: string;
}

export interface WatchItem {
  product: string;
  alertThresholdPrice: number;
  lastCheckedPrice: number | null;
  lastCheckedAt: string | null;
}

export async function readBudget(userId: string): Promise<Budget> {
  const res = await fetch(`${BASE}/read_budget/${userId}`);
  if (!res.ok) throw new Error(`read_budget failed: ${res.status}`);
  return res.json();
}

export async function getWatchlist(userId: string): Promise<{ watchlist: WatchItem[] }> {
  const res = await fetch(`${BASE}/get_watchlist/${userId}`);
  if (!res.ok) throw new Error(`get_watchlist failed: ${res.status}`);
  return res.json();
}

export async function addToWatchlist(userId: string, product: string, threshold: number) {
  const res = await fetch(`${BASE}/add_to_watchlist`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ userId, product, alertThresholdPrice: threshold }),
  });
  if (!res.ok) throw new Error(`add_to_watchlist failed: ${res.status}`);
  return res.json();
}

export async function checkWatchlist(userId: string) {
  const res = await fetch(`${BASE}/check_watchlist/${userId}`);
  if (!res.ok) throw new Error(`check_watchlist failed: ${res.status}`);
  return res.json();
}

export interface ChatMessage { role: "user" | "assistant"; content: string; }

export async function sendChat(messages: ChatMessage[], userId: string) {
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, userId }),
  });
  if (!res.ok) throw new Error(`chat failed: ${res.status}`);
  return res.json(); // { reply } or { error }
}
