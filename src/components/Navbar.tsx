import { DeepSeekLogo } from "./DeepSeekLogo";

const Navbar = () => {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between px-6 md:px-10 py-4 bg-background/80 backdrop-blur-md">
      <a href="/" className="flex items-center gap-2">
        <DeepSeekLogo className="h-6 w-auto" />
      </a>
      <div className="flex items-center gap-4">
        <a
          href="#"
          className="text-sm font-medium text-foreground/80 hover:text-foreground transition-colors"
        >
          Get DeepSeek App
        </a>
        <a
          href="#"
          className="text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          中文
        </a>
      </div>
    </nav>
  );
};

export default Navbar;
