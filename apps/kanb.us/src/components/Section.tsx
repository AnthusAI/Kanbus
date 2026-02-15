import * as React from "react";
import clsx from "clsx";

type SectionProps = {
  title: string;
  subtitle?: string;
  variant?: "default" | "alt";
  children: React.ReactNode;
};

const Section = ({ title, subtitle, variant = "default", children }: SectionProps) => {
  return (
    <section className="py-14 md:py-20">
      <div
        className={clsx(
          "rounded-3xl shadow-card px-6 sm:px-10 py-12 space-y-6 bg-card",
          variant === "alt" ? "bg-column" : "bg-card"
        )}
      >
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
