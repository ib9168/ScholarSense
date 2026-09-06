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

async function request<T>(path: string, options?: RequestInit, base = BASE): Promise<T> {
  const { signal: callerSignal, ...rest } = options ?? {};
  const timeout = AbortSignal.timeout(120_000);
  const signal = callerSignal
    ? AbortSignal.any([callerSignal, timeout])
    : timeout;
  let res: Response;
  try {
    res = await fetch(`${base}${path}`, { ...rest, signal });
  } catch (err) {
    const isTimeout = err instanceof Error && err.name === "TimeoutError";
    throw new Error(
      isTimeout
        ? `${path} timed out after 120s`
        : `${path} failed: could not reach server`
    );
  }

  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json() as { error?: string; detail?: string };
      detail = body.error ?? (typeof body.detail === "string" ? body.detail : "");
    } catch { /* body not JSON — use status only */ }
    throw new Error(`${path} failed: ${res.status}${detail ? ` — ${detail}` : ""}`);
  }

  try {
    return (await res.json()) as T;
  } catch {
    throw new Error(`${path} failed: invalid JSON response`);
  }
}

export async function readBudget(userId: string): Promise<Budget> {
  return request<Budget>(`/read_budget/${userId}`);
}

export async function getWatchlist(userId: string): 
  Promise<{ watchlist: WatchItem[] }> {
  return request<{ watchlist: WatchItem[] }>(`/get_watchlist/${userId}`);
}

export async function addToWatchlist(
  userId: string,
  product: string,
  threshold: number
) {
  return request(`/add_to_watchlist`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ userId, product, alertThresholdPrice: threshold }),
  });
}
export interface CheckWatchlistResult {
  alerts: Array<{ message?: string; product?: string }>;
}

export async function checkWatchlist(userId: string) {
  return request<CheckWatchlistResult>(`/check_watchlist/${userId}`);
}

export interface ChatMessage { role: "user" | "assistant"; content: string; }

export async function sendChat(messages: ChatMessage[], userId: string) {
  return request<{ reply?: string; error?: string }>("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, userId }),
  }, "");
}
