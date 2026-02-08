import { DeepSeekLogo } from "./DeepSeekLogo";

const HeroSection = () => {
  return (
    <section className="relative ds-wave-overlay ds-gradient-bg min-h-[80vh] flex flex-col items-center justify-center px-4 pt-24">
      <div className="relative z-10 flex flex-col items-center gap-6 animate-fade-in-up">
        <DeepSeekLogo variant="large" className="text-7xl md:text-8xl lg:text-[6.5rem]" />

        <p className="text-2xl md:text-3xl font-light text-muted-foreground tracking-wide">
          Into the unknown
        </p>

        <div className="flex flex-col sm:flex-row gap-4 mt-8 w-full max-w-2xl px-4">
          <a
            href="/chat"
            className="flex-1 group bg-card rounded-xl border border-border p-6 ds-card-hover"
          >
            <h3 className="text-lg font-semibold text-primary mb-2">Start Now</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Free access to DeepSeek-V3.2.
              <br />
              Experience the intelligent model.
            </p>
          </a>

          <a
            href="#"
            className="flex-1 group bg-card rounded-xl border border-border p-6 ds-card-hover"
          >
            <h3 className="text-lg font-semibold text-primary mb-2">Access API</h3>
            <p className="text-sm text-muted-foreground leading-relaxed">
              Build with the latest DeepSeek models.
              <br />
              Powerful models, smooth experience.
            </p>
          </a>
        </div>
      </div>
    </section>
  );
};

export default HeroSection;
