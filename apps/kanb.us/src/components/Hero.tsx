import * as React from "react";

type HeroProps = {
  eyebrow?: string;
  title: string;
  subtitle: string;
  actions?: React.ReactNode;
  rightPane?: React.ReactNode;
  bottomPane?: React.ReactNode;
};

export function Hero({ eyebrow, title, subtitle, actions, rightPane, bottomPane }: HeroProps): JSX.Element {
  return (
    <div className="relative isolate overflow-hidden py-16 sm:py-24">
      <div 
        className="absolute top-[20%] left-1/2 -translate-x-1/2 -translate-y-1/2 w-[800px] h-[600px] rounded-[100%] pointer-events-none z-[-1]"
        style={{
          background: "radial-gradient(ellipse at center, var(--glow-center) 0%, var(--glow-edge) 70%)",
          opacity: 0.6
        }}
      />
      <div className={`mx-auto max-w-7xl px-6 lg:px-8 ${rightPane ? 'grid gap-12 items-center sm:grid-cols-2' : 'flex flex-col items-center text-center max-w-5xl'}`}>
        <div className={`flex flex-col ${rightPane ? 'items-start text-left' : 'items-center text-center w-full'}`}>
          {eyebrow && (
            <span className="mb-6 font-mono inline-flex items-center bg-selected/10 px-3 py-1 text-sm font-medium text-selected">
              {eyebrow}
            </span>
          )}
          <h1 className="text-4xl font-bold tracking-tight text-foreground sm:text-6xl mb-6">
            {title}
          </h1>
          <p className={`text-xl leading-8 text-muted font-medium max-w-2xl ${rightPane ? '' : 'mx-auto'}`}>
            {subtitle}
          </p>
          {actions && (
            <div className={`mt-10 flex items-center gap-x-6 ${rightPane ? 'justify-start' : 'justify-center w-full'}`}>
              {actions}
            </div>
          )}
        </div>
        {rightPane && (
          <div className="relative w-full h-full flex items-center justify-center">
            {rightPane}
          </div>
        )}
      </div>
      {bottomPane && (
        <div className="mx-auto max-w-7xl px-6 lg:px-8 mt-20 w-full flex justify-center">
          {bottomPane}
        </div>
      )}
    </div>
  );
}
