import { motion } from "framer-motion";

const AnnouncementBanner = () => {
  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2, duration: 0.4 }}
      className="w-full bg-ds-banner-bg py-2.5 text-center border-b border-border/50"
    >
      <a
        href="#"
        className="text-sm text-muted-foreground hover:text-foreground transition-colors inline-flex items-center gap-1.5 group"
      >
        <span>🎉</span>
        <span>
          Launching LearnLLM-V3.2 — Reasoning-first models built for agents. Now available on web, app & API.{" "}
          <span className="text-primary font-medium group-hover:underline">Click for details →</span>
        </span>
      </a>
    </motion.div>
  );
};

export default AnnouncementBanner;
