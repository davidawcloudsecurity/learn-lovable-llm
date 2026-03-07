import { useState, useRef, useEffect } from "react";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LearnLLMLogo } from "@/components/LearnLLMLogo";
import { streamChatResponse } from "@/lib/chat-api";
import ChatSidebar from "@/components/chat/ChatSidebar";
import ChatEmptyState from "@/components/chat/ChatEmptyState";
import ChatMessage from "@/components/chat/ChatMessage";
import ChatInput from "@/components/chat/ChatInput";

type Message = { role: "user" | "assistant"; content: string };

const Chat = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [responseTime, setResponseTime] = useState<number | null>(null);
  const [elapsedTime, setElapsedTime] = useState<number>(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;

    const userMsg: Message = { role: "user", content: trimmed };
    const updatedMessages = [...messages, userMsg];
    setMessages(updatedMessages);
    setInput("");
    setIsLoading(true);
    setError(null);
    setResponseTime(null);
    setElapsedTime(0);

    const startTime = performance.now();
    let firstTokenTime: number | null = null;
    let tickCount = 0;

    // Start the stopwatch timer
    timerRef.current = setInterval(() => {
      tickCount++;
      setElapsedTime(tickCount);
    }, 1000);

    let assistantSoFar = "";

    const upsert = (chunk: string) => {
      if (firstTokenTime === null) firstTokenTime = performance.now();
      assistantSoFar += chunk;
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last?.role === "assistant") {
          return prev.map((m, i) =>
            i === prev.length - 1 ? { ...m, content: assistantSoFar } : m
          );
        }
        return [...prev, { role: "assistant", content: assistantSoFar }];
      });
    };

    const onDone = () => {
      const endTime = performance.now();
      const totalTime = ((endTime - startTime) / 1000).toFixed(2);
      const timeToFirstToken = firstTokenTime ? ((firstTokenTime - startTime) / 1000).toFixed(2) : null;
      
      // Stop the timer
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      
      setResponseTime(parseFloat(totalTime));
      setIsLoading(false);
      setElapsedTime(0);
      
      console.log(`Response completed in ${totalTime}s (first token: ${timeToFirstToken}s)`);
    };

    const onError = (err: string) => {
      // Stop the timer on error
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      
      setError(err);
      setIsLoading(false);
      setElapsedTime(0);
    };

    await streamChatResponse(updatedMessages, upsert, onDone, onError);
  };

  const handleNewChat = () => {
    setMessages([]);
    setInput("");
    setError(null);
    setResponseTime(null);
  };

  const isEmpty = messages.length === 0;

  return (
    <div className="flex h-screen bg-background">
      <ChatSidebar
        firstMessage={messages[0]?.content}
        onNewChat={handleNewChat}
      />

      <main className="flex-1 flex flex-col min-w-0">
        {/* Mobile header */}
        <header className="md:hidden flex items-center justify-between p-3 border-b border-border/50 bg-background/80 backdrop-blur-sm">
          <LearnLLMLogo className="h-5 w-auto" />
          <Button variant="ghost" size="icon" onClick={handleNewChat} className="rounded-xl">
            <Plus className="h-5 w-5" />
          </Button>
        </header>

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto">
          {isEmpty ? (
            <ChatEmptyState />
          ) : (
            <div className="max-w-3xl mx-auto py-6 px-4 space-y-5">
              {messages.map((msg, i) => (
                <ChatMessage key={i} message={msg} index={i} />
              ))}
              {isLoading && messages[messages.length - 1]?.role !== "assistant" && (
                <div className="flex gap-3">
                  <div className="shrink-0 w-8 h-8 rounded-full bg-primary flex items-center justify-center shadow-sm">
                    <span className="text-primary-foreground text-xs font-bold font-display">LL</span>
                  </div>
                  <div>
                    <div className="bg-muted rounded-2xl px-4 py-3">
                      <div className="flex gap-1">
                        <span className="w-2 h-2 rounded-full bg-muted-foreground/50 animate-pulse" />
                        <span className="w-2 h-2 rounded-full bg-muted-foreground/50 animate-pulse delay-100" />
                        <span className="w-2 h-2 rounded-full bg-muted-foreground/50 animate-pulse delay-200" />
                      </div>
                    </div>
                    <div className="mt-1 px-2 text-xs text-muted-foreground">
                      {Math.floor(elapsedTime)}s
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        <ChatInput
          input={input}
          isLoading={isLoading}
          error={error}
          responseTime={responseTime}
          onInputChange={setInput}
          onSend={handleSend}
        />
      </main>
    </div>
  );
};

export default Chat;
