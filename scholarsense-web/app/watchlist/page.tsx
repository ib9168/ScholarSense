"use client";
import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { getWatchlist, addToWatchlist, checkWatchlist, WatchItem } from "@/lib/api";

// Placeholder until Clerk auth is wired up in Step 4
const USER_ID = "user_001";

export default function WatchlistPage() {
  const [items, setItems] = useState<WatchItem[]>([]);
  const [product, setProduct] = useState("");
  const [threshold, setThreshold] = useState("");
  const [alerts, setAlerts] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getWatchlist(USER_ID)
      .then((data) => { if (!cancelled) setItems(data.watchlist ?? []); })
      .catch(console.error);
    return () => { cancelled = true; };
  }, []);

  async function refresh() {
    const data = await getWatchlist(USER_ID);
    setItems(data.watchlist ?? []);
  }

  async function handleAdd() {
    const parsed = parseFloat(threshold);
    if (!product.trim() || !isFinite(parsed) || parsed <= 0) return;
    setBusy(true);
    setError(null);
    try {
      await addToWatchlist(USER_ID, product.trim(), parsed);
      setProduct(""); setThreshold("");
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add item. Please try again.");
    } finally { setBusy(false); }
  }

  async function handleCheck() {
    setBusy(true); setAlerts([]); setError(null);
    try {
      const data = await checkWatchlist(USER_ID);
      const messages = (data.alerts ?? [])
        .map((a) => a.message ?? a.product)
        .filter((msg): msg is string => typeof msg === "string");
      setAlerts(messages);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to check prices. Please try again.");
    } finally { setBusy(false); }
  }

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <h1 className="text-2xl font-bold">Price Watchlist</h1>

      {error && (
        <div className="rounded-lg border border-red-300 bg-red-50 text-red-900 p-3 text-sm">
          {error}
        </div>
      )}

      <Card>
        <CardHeader><CardTitle>Add item to watch</CardTitle></CardHeader>
        <CardContent className="flex gap-2">
          <Input placeholder="Product name" value={product} onChange={(e) => setProduct(e.target.value)} />
          <Input placeholder="Alert at $" type="number" step="0.01" min="0.01" className="w-32"
                 value={threshold} onChange={(e) => setThreshold(e.target.value)} />
          <Button onClick={handleAdd} disabled={busy}>Add</Button>
        </CardContent>
      </Card>

      <div className="rounded-lg border">
        <table className="w-full text-sm">
          <thead className="bg-muted">
            <tr>
              <th className="text-left p-2">Product</th>
              <th className="text-left p-2">Alert at</th>
              <th className="text-left p-2">Last price</th>
              <th className="text-left p-2">Last checked</th>
            </tr>
          </thead>
          <tbody>
            {items.map((it) => (
              <tr key={it.product} className="border-t">
                <td className="p-2">{it.product}</td>
                <td className="p-2">{it.alertThresholdPrice != null ? `$${it.alertThresholdPrice.toFixed(2)}` : "—"}</td>
                <td className="p-2">{it.lastCheckedPrice != null ? `$${it.lastCheckedPrice.toFixed(2)}` : "—"}</td>
                <td className="p-2">{it.lastCheckedAt ? new Date(it.lastCheckedAt).toLocaleString() : "—"}</td>
              </tr>
            ))}
            {items.length === 0 && (
              <tr><td colSpan={4} className="p-4 text-center text-muted-foreground">No items yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <Button onClick={handleCheck} disabled={busy}>Check prices now</Button>

      {alerts.length > 0 && (
        <div className="rounded-lg border border-green-300 bg-green-50 text-green-900 p-4 space-y-1">
          {alerts.map((a) => <p key={a}>🔔 {a}</p>)}
        </div>
      )}
    </div>
  );
}
