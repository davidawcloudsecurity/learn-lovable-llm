import { useState } from "react";
import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import { tokenizeOrdered } from "@/lib/tokenizer";

type Message = { role: "user" | "assistant"; content: string };

interface ChatMessageProps {
  message: Message;
  index: number;
}

const ChatMessage = ({ message, index }: ChatMessageProps) => {
  const isUser = message.role === "user";
  const [showTokens, setShowTokens] = useState(false);

  const tokens = isUser ? tokenizeOrdered(message.content) : [];

  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: Math.min(index * 0.05, 0.2) }}
      className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}
    >
      {!isUser && (
        <div className="shrink-0 w-8 h-8 rounded-full bg-primary flex items-center justify-center shadow-sm">
          <span className="text-primary-foreground text-xs font-bold font-display">
            LL
          </span>
        </div>
      )}
      <div className="max-w-[80%]">
        <div
          className={`rounded-2xl px-4 py-3 ${
            isUser
              ? "bg-foreground text-background rounded-br-md"
              : "bg-muted/80 text-foreground border border-border/50 rounded-bl-md"
          }`}
        >
          {!isUser ? (
            <div className="prose prose-sm dark:prose-invert max-w-none [&_p]:leading-relaxed [&_code]:text-xs [&_code]:bg-background/50 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded">
              <ReactMarkdown>{message.content}</ReactMarkdown>
            </div>
          ) : (
            <p className="text-sm whitespace-pre-wrap leading-relaxed">
              {message.content}
            </p>
          )}
        </div>

        {/* Token dict toggle for user messages */}
        {isUser && tokens.length > 0 && (
          <div className="mt-1.5">
            <button
              onClick={() => setShowTokens(!showTokens)}
              className="text-[11px] text-muted-foreground hover:text-foreground transition-colors px-1"
            >
              {showTokens ? "▾ Hide tokens" : "▸ Show tokens"} ({tokens.length})
            </button>

            {showTokens && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                transition={{ duration: 0.2 }}
                className="mt-1 p-2.5 rounded-xl bg-muted/60 border border-border/40 font-mono text-xs"
              >
                <div className="text-muted-foreground mb-1.5">
                  {"{"} <span className="text-[10px] italic">word → token_id</span>
                </div>
                <div className="space-y-0.5 pl-2">
                  {tokens.map(([word, id], i) => (
                    <div key={i} className="flex gap-1">
                      <span className="text-emerald-500">"{word}"</span>
                      <span className="text-muted-foreground">:</span>
                      <span className="text-amber-500">{id}</span>
                      {i < tokens.length - 1 && (
                        <span className="text-muted-foreground">,</span>
                      )}
                    </div>
                  ))}
                </div>
                <div className="text-muted-foreground">{"}"}</div>
              </motion.div>
            )}
          </div>
        )}
      </div>
    </motion.div>
  );
};

export default ChatMessage;
