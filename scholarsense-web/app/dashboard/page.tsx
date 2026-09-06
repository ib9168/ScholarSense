"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { readBudget, Budget } from "@/lib/api";

export default function DashboardPage() {
  const [budget, setBudget] = useState<Budget | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    readBudget("user_001").then(setBudget).catch((e) => setError(e instanceof Error ? e.message : "Failed to load budget"));
  }, []);

  if (error) return <p className="p-8 text-red-500">{error}</p>;
  if (!budget) return <p className="p-8 text-muted-foreground">Loading…</p>;

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <h1 className="text-2xl font-bold">Budget Dashboard</h1>

      {(budget.warnings?.length ?? 0) > 0 && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 text-amber-900 p-4 space-y-1">
          {(budget.warnings ?? []).map((w, i) => <p key={i}>⚠️ {w}</p>)}
        </div>
      )}

      <Card>
        <CardHeader><CardTitle>Total: ${budget.totalSpent?.toFixed(2)} spent of ${budget.totalBudget?.toFixed(2)}</CardTitle></CardHeader>
        <CardContent>
          <Progress value={budget.totalBudget ? (budget.totalSpent! / budget.totalBudget) * 100 : 0} />
          <p className="text-sm text-muted-foreground mt-2">
            {budget.elapsedPct ?? 0}% of your timeline elapsed
          </p>
        </CardContent>
      </Card>

      <div className="grid gap-4 md:grid-cols-2">
        {budget.categories.map((c) => (
          <Card key={c.name}>
            <CardHeader><CardTitle className="capitalize">{c.name}</CardTitle></CardHeader>
            <CardContent>
              <Progress value={c.spentPct ?? 0} />
              <p className="text-sm mt-2">
                ${c.spent.toFixed(2)} of ${c.budget.toFixed(2)} —
                <span className="text-muted-foreground"> ${c.remaining?.toFixed(2)} left</span>
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      <p className="text-sm text-muted-foreground">
        Timeline: {budget.timeline?.start} → {budget.timeline?.end}
      </p>
      <Link href="/" className="text-sm underline">← Back to chat</Link>
    </div>
  );
}
