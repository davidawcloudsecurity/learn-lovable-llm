interface LearnLLMLogoProps {
  className?: string;
  variant?: "small" | "large";
}

export const LearnLLMLogo = ({ className = "", variant = "small" }: LearnLLMLogoProps) => {
  if (variant === "large") {
    return (
      <h1 className={`ds-wordmark font-bold tracking-tight select-none ${className}`}>
        learnllm
      </h1>
    );
  }

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" className="text-primary">
        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="1.5" />
        <path
          d="M8 12C8 9.5 10 7 12 7C14 7 15 8.5 15 10C15 12 12 13 12 15"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
        />
        <circle cx="12" cy="18" r="0.75" fill="currentColor" />
      </svg>
      <span className="ds-wordmark font-semibold text-lg tracking-tight">learnllm</span>
    </div>
  );
};
