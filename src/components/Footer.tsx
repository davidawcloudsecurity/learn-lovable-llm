import { LearnLLMLogo } from "./LearnLLMLogo";
import { Mail, Github } from "lucide-react";

const footerLinks = {
  Research: [
    "LearnLLM R1",
    "LearnLLM V3",
    "LearnLLM Coder V2",
    "LearnLLM VL",
    "LearnLLM V2",
    "LearnLLM Coder",
    "LearnLLM Math",
    "LearnLLM LLM",
  ],
  Product: [
    "LearnLLM App",
    "LearnLLM Chat",
    "LearnLLM Platform",
    "API Pricing",
    "Service Status",
  ],
  "Legal & Safety": [
    "Privacy Policy",
    "Terms of Use",
    "Report Vulnerabilities",
  ],
  "Join Us": ["Job Description"],
};

const SocialIcon = ({ type }: { type: string }) => {
  switch (type) {
    case "mail":
      return <Mail className="w-5 h-5" />;
    case "github":
      return <Github className="w-5 h-5" />;
    case "x":
      return (
        <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
          <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z" />
        </svg>
      );
    default:
      return null;
  }
};

const Footer = () => {
  return (
    <footer className="border-t border-border bg-card">
      <div className="container max-w-6xl mx-auto px-6 py-12">
        <div className="grid grid-cols-1 md:grid-cols-6 gap-10">
          {/* Logo & socials */}
          <div className="md:col-span-2 flex flex-col gap-6">
            <LearnLLMLogo className="h-6" />
            <div className="flex items-center gap-4 text-muted-foreground">
              {["mail", "github", "x"].map((social) => (
                <a
                  key={social}
                  href="#"
                  className="hover:text-foreground transition-colors"
                >
                  <SocialIcon type={social} />
                </a>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              © 2026 LearnLLM. All rights reserved.
            </p>
          </div>

          {/* Link columns */}
          {Object.entries(footerLinks).map(([title, links]) => (
            <div key={title}>
              <h4 className="font-semibold text-sm text-foreground mb-4">{title}</h4>
              <ul className="space-y-2.5">
                {links.map((link) => (
                  <li key={link}>
                    <a
                      href="#"
                      className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                    >
                      {link}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>
    </footer>
  );
};

export default Footer;
