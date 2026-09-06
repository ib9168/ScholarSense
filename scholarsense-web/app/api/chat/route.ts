import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.NEXT_PUBLIC_API_URL;

export async function POST(req: NextRequest) {
  const body = await req.json();

  let res: Response;
  try {
    res = await fetch(`${API_URL}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(120_000),
    });
  } catch (err) {
    const isTimeout = err instanceof Error && err.name === "TimeoutError";
    return NextResponse.json(
      {
        error: isTimeout
          ? "The server took too long to respond. Please try again."
          : "Could not reach the server. Please try again shortly.",
      },
      { status: 502 }
    );
  }

  let data: unknown;
  try {
    data = await res.json();
  } catch {
    return NextResponse.json(
      { error: "Server returned an unexpected response. Please try again." },
      { status: 502 }
    );
  }

  return NextResponse.json(data, { status: res.status });
}