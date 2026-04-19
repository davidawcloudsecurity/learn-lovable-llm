import { motion } from "framer-motion";
import { Plus, MessageSquare, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LearnLLMLogo } from "@/components/LearnLLMLogo";
import type { SessionEntry } from "@/lib/session-storage";

interface ChatSidebarProps {
  sessions: SessionEntry[];
  activeSessionId: string | null;
  onNewChat: () => void;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
}

const ChatSidebar = ({
  sessions,
  activeSessionId,
  onNewChat,
  onSelectSession,
  onDeleteSession,
}: ChatSidebarProps) => {
  return (
    <aside className="hidden md:flex w-64 flex-col border-r border-border/50 bg-card/50 backdrop-blur-sm">
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="p-4 border-b border-border/50"
      >
        <Button
          variant="outline"
          className="w-full justify-start gap-2 rounded-xl hover:bg-primary/10 hover:border-primary/30 transition-all duration-200"
          onClick={onNewChat}
        >
          <Plus className="h-4 w-4" />
          <span className="font-display">New Chat</span>
        </Button>
      </motion.div>

      <div className="flex-1 p-3 overflow-y-auto">
        <p className="text-xs text-muted-foreground px-2 py-1 font-medium tracking-wide uppercase">
          Chat History
        </p>
        {sessions.length === 0 ? (
          <p className="text-xs text-muted-foreground px-2 py-3 italic">
            No previous chats yet
          </p>
        ) : (
          <div className="space-y-1 mt-1">
            {sessions.map((s) => (
              <motion.div
                key={s.id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.2 }}
                className={`group flex items-center gap-2 px-3 py-2.5 rounded-xl text-sm cursor-pointer transition-colors duration-200 ${
                  s.id === activeSessionId
                    ? "bg-accent text-foreground"
                    : "hover:bg-accent/50 text-muted-foreground hover:text-foreground"
                }`}
                onClick={() => onSelectSession(s.id)}
              >
                <MessageSquare className="h-4 w-4 shrink-0" />
                <span className="truncate flex-1">{s.preview}</span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDeleteSession(s.id);
                  }}
                  className="opacity-0 group-hover:opacity-100 transition-opacity p-1 hover:text-destructive"
                  aria-label="Delete chat"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </motion.div>
            ))}
          </div>
        )}
      </div>

      <div className="p-4 border-t border-border/50">
        <a href="/" className="flex items-center gap-2 hover-scale">
          <LearnLLMLogo className="h-5 w-auto" />
        </a>
      </div>
    </aside>
  );
};

export default ChatSidebar;
