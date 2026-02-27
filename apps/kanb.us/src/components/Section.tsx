import * as React from "react";

type SectionProps = {
  title: string;
  subtitle?: string;
  variant?: "default" | "alt";
  children: React.ReactNode;
};

const Section = ({ title, subtitle, variant = "default", children }: SectionProps) => {
  return (
    <section className={`py-14 md:py-20 w-full ${variant === 'alt' ? 'bg-region-alt' : 'bg-background'}`}>
      <div className="max-w-7xl mx-auto px-6 lg:px-8 space-y-6">
        <div className="max-w-3xl space-y-3">
          <h2 className="text-3xl font-display font-bold tracking-tight text-foreground sm:text-4xl">
            {title}
          </h2>
          {subtitle && (
            <p className="text-lg text-muted leading-relaxed">{subtitle}</p>
          )}
        </div>
        {children}
      </div>
    </section>
  );
};

export default Section;
