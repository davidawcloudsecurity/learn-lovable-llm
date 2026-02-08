const AnnouncementBanner = () => {
  return (
    <div className="w-full bg-ds-banner-bg py-2.5 text-center">
      <a
        href="#"
        className="text-sm text-muted-foreground hover:text-foreground transition-colors inline-flex items-center gap-1.5"
      >
        <span>🎉</span>
        <span>
          Launching DeepSeek-V3.2 — Reasoning-first models built for agents. Now available on web, app & API.{" "}
          <span className="text-primary font-medium">Click for details.</span>
        </span>
      </a>
    </div>
  );
};

export default AnnouncementBanner;
