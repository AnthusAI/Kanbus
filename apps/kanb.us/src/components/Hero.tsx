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
    <div className="relative isolate overflow-hidden">
        <div className="mx-auto max-w-2xl text-center py-16 sm:py-20 lg:py-24">
          <div className="hidden sm:mb-8 sm:flex sm:justify-center">
            <div className="relative rounded-full px-3 py-1 text-sm leading-6 text-slate-600 dark:text-slate-400 ring-1 ring-slate-900/10 dark:ring-white/10 hover:ring-slate-900/20 dark:hover:ring-white/20 transition-all">
              {eyebrow}
            </div>
          </div>
          <h1 className="text-4xl font-heading font-bold tracking-tight text-slate-900 dark:text-white sm:text-6xl">
            {title}
          </h1>
          <p className="mt-6 text-lg leading-8 text-slate-600 dark:text-slate-300">
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
