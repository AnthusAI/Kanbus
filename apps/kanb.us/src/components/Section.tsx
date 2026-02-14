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
    <section className={clsx(
        "py-16 md:py-24",
        variant === "alt" ? "bg-slate-50 dark:bg-slate-900/50 -mx-4 px-4 sm:-mx-6 sm:px-6 lg:-mx-8 lg:px-8 rounded-3xl my-8" : ""
    )}>
      <div className="max-w-3xl mb-12">
        <h2 className="text-3xl font-heading font-bold tracking-tight text-slate-900 dark:text-white sm:text-4xl">
            {title}
        </h2>
        {subtitle && (
            <p className="mt-4 text-lg text-slate-600 dark:text-slate-400">
                {subtitle}
            </p>
        )}
      </div>
      {children}
    </section>
  );
};

export default Section;
