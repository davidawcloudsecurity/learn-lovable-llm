import { motion } from "framer-motion";
import { LearnLLMLogo } from "@/components/LearnLLMLogo";

const ChatEmptyState = () => {
  return (
    <div className="h-full flex flex-col items-center justify-center gap-5 px-4">
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      >
        <LearnLLMLogo variant="large" className="text-5xl md:text-6xl" />
      </motion.div>
      <motion.p
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2, duration: 0.4 }}
        className="text-lg text-muted-foreground font-display"
      >
        How can I help you today?
      </motion.p>
    </div>
  );
};

export default ChatEmptyState;
