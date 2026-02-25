import * as React from "react";

type HeroProps = {
  eyebrow?: string;
  title: string;
  subtitle: string;
  actions?: React.ReactNode;
};

export function Hero({ eyebrow, title, subtitle, actions }: HeroProps): JSX.Element {
  return (
    <div className="relative isolate overflow-hidden py-16 sm:py-24">
      <div className="mx-auto max-w-4xl px-6 lg:px-8 flex flex-col items-center text-center">
        {eyebrow && (
          <span className="mb-6 inline-flex items-center rounded-full bg-selected/10 px-3 py-1 text-sm font-medium text-selected ring-1 ring-inset ring-selected/20">
            {eyebrow}
          </span>
        )}
        <h1 className="text-4xl font-bold tracking-tight text-foreground sm:text-6xl mb-4">
          {title}
        </h1>
        <p className="text-2xl leading-9 text-muted max-w-3xl font-medium">
          {subtitle}
        </p>
        {actions && (
          <div className="mt-10 flex items-center justify-center gap-x-6">
            {actions}
          </div>
        )}
      </div>
    </div>
  );
}
