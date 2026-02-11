import * as React from "react";
import type { ReactNode } from "react";
import { Link } from "gatsby";
import clsx from "clsx";

type LayoutProps = {
  children: ReactNode;
};

export function Layout({ children }: LayoutProps): JSX.Element {
  return (
    <div className="min-h-screen bg-[var(--surface)] text-slate-50">
      <header className="border-b border-white/5 bg-[var(--surface-alt)]/70 backdrop-blur">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <Link to="/" className="text-lg font-semibold tracking-wide">
            Taskulus
          </Link>
          <nav className="flex gap-6 text-sm text-slate-300">
            <Link to="/">Overview</Link>
            <a href="https://github.com/AnthusAI/Taskulus" target="_blank" rel="noreferrer">
              GitHub
            </a>
            <a href="https://taskul.us" target="_blank" rel="noreferrer">
              taskul.us
            </a>
          </nav>
        </div>
      </header>
      <main className={clsx("mx-auto w-full max-w-5xl px-6 py-16")}>
        {children}
      </main>
      <footer className="mt-12 border-t border-white/5 px-6 py-8 text-center text-sm text-slate-400">
        Built with Gatsby + Tailwind. Deploy-ready for AWS Amplify Gen 2.
      </footer>
    </div>
  );
}
