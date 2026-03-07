import { motion } from "framer-motion";
import { LearnLLMLogo } from "./LearnLLMLogo";

const Navbar = () => {
  return (
    <motion.nav
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
      className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 md:px-10 py-4 bg-background/70 backdrop-blur-xl border-b border-border/50"
    >
      <a href="/" className="flex items-center gap-2 hover-scale">
        <LearnLLMLogo className="h-6 w-auto" />
      </a>
      <div className="flex items-center gap-6">
        <a
          href="/chat"
          className="story-link text-sm font-medium text-foreground/80 hover:text-foreground transition-colors"
        >
          <span>Get LearnLLM App</span>
        </a>
        <a
          href="#"
          className="text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          中文
        </a>
      </div>
    </motion.nav>
  );
};

export default Navbar;
