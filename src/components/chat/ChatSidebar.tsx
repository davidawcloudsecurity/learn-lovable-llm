import { motion } from "framer-motion";
import { Plus, MessageSquare } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LearnLLMLogo } from "@/components/LearnLLMLogo";

interface ChatSidebarProps {
  firstMessage?: string;
  onNewChat: () => void;
}

const ChatSidebar = ({ firstMessage, onNewChat }: ChatSidebarProps) => {
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

      <div className="flex-1 p-3">
        <p className="text-xs text-muted-foreground px-2 py-1 font-medium tracking-wide uppercase">
          Today
        </p>
        {firstMessage && (
          <motion.div
            initial={{ opacity: 0, x: -10 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.3, delay: 0.1 }}
            className="flex items-center gap-2 px-3 py-2.5 rounded-xl bg-accent/50 text-sm text-foreground mt-1 cursor-pointer hover:bg-accent transition-colors duration-200"
          >
            <MessageSquare className="h-4 w-4 shrink-0 text-muted-foreground" />
            <span className="truncate">{firstMessage.slice(0, 30)}...</span>
          </motion.div>
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
