import * as React from "react";

type HeroProps = {
  eyebrow?: string;
  title: string;
  subtitle: string;
  actions?: React.ReactNode;
};

export function Hero({
  eyebrow = "Public launch in progress",
  title,
  subtitle,
  actions
}: HeroProps): JSX.Element {
  return (
    <section className="space-y-6 text-center">
      <p className="pill inline-flex">{eyebrow}</p>
      <h1 className="text-4xl font-semibold tracking-tight text-slate-50 sm:text-5xl">
        {title}
      </h1>
      <p className="mx-auto max-w-2xl text-lg text-slate-300">{subtitle}</p>
      {actions && <div className="flex justify-center gap-4">{actions}</div>}
    </section>
  );
}
