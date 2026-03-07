import { useRef } from "react";
import { Send } from "lucide-react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

interface ChatInputProps {
  input: string;
  isLoading: boolean;
  error: string | null;
  responseTime: number | null;
  onInputChange: (value: string) => void;
  onSend: () => void;
}

const ChatInput = ({
  input,
  isLoading,
  error,
  responseTime,
  onInputChange,
  onSend,
}: ChatInputProps) => {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, delay: 0.1 }}
      className="border-t border-border/50 p-4 bg-background/80 backdrop-blur-sm"
    >
      {error && (
        <div className="max-w-3xl mx-auto mb-2 p-3 bg-destructive/10 border border-destructive/20 rounded-xl text-sm text-destructive">
          Error: {error}
        </div>
      )}
      {responseTime !== null && !isLoading && (
        <div className="max-w-3xl mx-auto mb-2 px-3 py-1 text-xs text-muted-foreground text-center">
          ⚡ Response time: {responseTime}s
        </div>
      )}
      {isLoading && (
        <div className="max-w-3xl mx-auto mb-2 px-3 py-1 text-xs text-muted-foreground text-center animate-pulse">
          🤖 Generating response...
        </div>
      )}
      <div className="max-w-3xl mx-auto flex gap-2 items-end">
        <Textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Message LearnLLM..."
          className="min-h-[48px] max-h-[200px] resize-none rounded-2xl bg-muted/60 border border-border/50 focus-visible:ring-1 focus-visible:ring-primary/50 focus-visible:border-primary/30 transition-all duration-200 text-sm"
          rows={1}
        />
        <Button
          size="icon"
          onClick={onSend}
          disabled={!input.trim() || isLoading}
          className="shrink-0 rounded-2xl h-12 w-12 bg-foreground text-background hover:bg-foreground/90 disabled:opacity-30 transition-all duration-200"
        >
          <Send className="h-4 w-4" />
        </Button>
      </div>
      <p className="text-[11px] text-muted-foreground text-center mt-2.5 tracking-wide">
        LearnLLM can make mistakes. Consider checking important info.
      </p>
    </motion.div>
  );
};

export default ChatInput;
