"use client";
import { useState, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { sendChat, ChatMessage } from "@/lib/api";

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;
    const userMsg: ChatMessage = { role: "user", content: text };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setLoading(true);
    try {
      // send full history so multi-turn conversation works
      const history = [...messages, userMsg];
      const data = await sendChat(history, "user_001");
      setMessages((m) => [...m, {
        role: "assistant",
        content: data.reply ?? `⚠️ ${data.error ?? "No response"}`,
      }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", content: "Error reaching the server." }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col h-[calc(100vh-4rem)] max-w-2xl mx-auto">
      <ScrollArea className="flex-1 p-4 space-y-4">
        {messages.length === 0 && (
          <p className="text-center text-muted-foreground mt-10">
            Hi! Tell me your budget, ask what you have left, or ask where to buy something cheap.
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div className={`max-w-[80%] rounded-2xl px-4 py-2 text-sm whitespace-pre-wrap ${
              m.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted"
            }`}>
              {m.content}
            </div>
          </div>
        ))}
        {loading && <div className="text-muted-foreground text-sm">ScholarSense is thinking…</div>}
        <div ref={bottomRef} />
      </ScrollArea>
      <div className="p-4 flex gap-2 border-t">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
          placeholder="e.g., Set my budget $80 from June 10 to July 10..."
        />
        <Button onClick={handleSend} disabled={loading}>Send</Button>
      </div>
    </div>
  );
}
