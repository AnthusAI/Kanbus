import * as React from "react";
import { Menu, X } from "lucide-react";
import { AnimatedKanbanIcon } from "./AnimatedKanbanIcon";

const navigation = [
  { label: "What Is This?", href: "/what-is-this" },
  { label: "Philosophy", href: "/philosophy" },
  { label: "Features", href: "/features" },
  { label: "Getting Started", href: "/getting-started" }
];

// Desktop shows only first-class items; Philosophy stays available in mobile menu
const desktopNavigation = navigation.filter((item) => item.label !== "Philosophy");

type LayoutProps = {
  children: React.ReactNode;
};

const Layout = ({ children }: LayoutProps) => {
  const [mobileOpen, setMobileOpen] = React.useState(false);
  return (
    <div className="min-h-screen flex flex-col bg-background text-foreground font-sans">
      <style>{`
        .footer-compact { line-height: 0.5; }
      `}</style>
      <header className="sticky top-0 z-50 w-full bg-card/90 backdrop-blur supports-[backdrop-filter]:backdrop-blur">
        <div className="max-w-7xl mx-auto px-6 lg:px-8 h-16 flex items-center justify-between">
          <nav className="flex items-center gap-6 w-full">
            <a
              href="/"
              className="hover:text-selected hover:drop-shadow-[0_0_2px_rgba(var(--text-selected-rgb),0.4)] transition-all duration-300 flex items-baseline gap-[3px]"
            >
              <span className="text-[25px] leading-none font-black tracking-[3px]" style={{ WebkitTextStroke: "1px currentColor" }}>
                <span className="text-muted">KAN</span><span className="text-foreground">BUS</span>
              </span>
              <AnimatedKanbanIcon className="w-[19px] h-[19px]" />
            </a>
            <div className="ml-auto flex items-center gap-3">
              {desktopNavigation.map((item) => (
                <a
                  key={item.href}
                  href={item.href}
                  className="hidden md:block text-sm font-medium text-muted hover:text-foreground transition-colors"
                >
                  {item.label}
                </a>
              ))}
              <a
                href="https://github.com/AnthusAI/Kanbus"
                className="hidden md:inline-flex text-muted hover:text-foreground transition-colors"
              >
                <span className="sr-only">GitHub</span>
                <svg
                  className="h-5 w-5"
                  fill="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    fillRule="evenodd"
                    d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
                    clipRule="evenodd"
                  />
                </svg>
              </a>
              <button
                type="button"
                className="md:hidden inline-flex items-center justify-center rounded-md/70 p-2 text-muted hover:text-foreground hover:border-border transition-colors bg-card"
                aria-label="Toggle navigation"
                onClick={() => setMobileOpen((open) => !open)}
              >
                {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
              </button>
            </div>
          </nav>
        </div>
        {mobileOpen ? (
          <div className="md:hidden bg-card">
            <div className="max-w-7xl mx-auto px-6 py-4 space-y-3">
              {navigation.map((item) => (
                <a
                  key={item.href}
                  href={item.href}
                  className="block text-sm font-medium text-muted hover:text-foreground transition-colors"
                  onClick={() => setMobileOpen(false)}
                >
                  {item.label}
                </a>
              ))}
              <a
                href="https://github.com/AnthusAI/Kanbus"
                className="block text-sm font-medium text-muted hover:text-foreground transition-colors"
              >
                GitHub
              </a>
            </div>
          </div>
        ) : null}
      </header>

      <main className="flex-1 w-full flex flex-col">
        {children}
      </main>

      <footer className="bg-footer-bg py-8 md:py-12">
        <div className="max-w-7xl mx-auto px-6 lg:px-8">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-x-8 gap-y-8 md:gap-y-6">
            <div className="col-span-2 text-muted">
              <ul className="grid grid-cols-1 sm:grid-cols-2 gap-y-0 gap-x-8 text-sm text-muted footer-compact">
                <li className="font-semibold col-span-1 sm:col-span-2 opacity-75">Features</li>
                <li><a href="/features/core-management" className="text-muted hover:text-selected block">Core Management</a></li>
                <li><a href="/features/kanban-board" className="text-muted hover:text-selected block">Kanban Board</a></li>
                <li><a href="/features/jira-sync" className="text-muted hover:text-selected block">Jira Sync</a></li>
                <li><a href="/features/local-tasks" className="text-muted hover:text-selected block">Local Tasks</a></li>
                <li><a href="/features/virtual-projects" className="text-muted hover:text-selected block">Virtual Projects</a></li>
                <li><a href="/features/beads-compatibility" className="text-muted hover:text-selected block">Beads Mode</a></li>
                <li><a href="/features/vscode-plugin" className="text-muted hover:text-selected block">VS Code Plugin</a></li>
                <li><a href="/features/integrated-wiki" className="text-muted hover:text-selected block">Integrated Wiki</a></li>
                <li><a href="/features/policy-as-code" className="text-muted hover:text-selected block">Policy as Code</a></li>
              </ul>
            </div>
            
            <div className="col-span-2 flex flex-col h-full text-muted">
              <div className="grid grid-cols-2 gap-x-8">
                <div className="col-span-1">
                  <ul className="grid gap-y-0 text-sm text-muted footer-compact">
                    <li className="font-semibold opacity-75">Reference</li>
                    <li><a href="/what-is-this" className="text-muted hover:text-selected block">What Is This?</a></li>
                    <li><a href="/architecture" className="text-muted hover:text-selected block">Architecture</a></li>
                    <li><a href="/docs" className="text-muted hover:text-selected block">Documentation</a></li>
                    <li><a href="/philosophy" className="text-muted hover:text-selected block">Philosophy</a></li>
                  </ul>
                </div>
                <div className="col-span-1 md:text-right">
                  <ul className="grid gap-y-0 text-sm text-muted footer-compact">
                    <li className="font-semibold opacity-75">Community</li>
                    <li><a href="https://github.com/AnthusAI/Kanbus" className="text-muted hover:text-selected block md:inline-block">GitHub</a></li>
                  </ul>
                </div>
              </div>
              
              <ul className="mt-auto grid gap-y-0 text-sm text-muted footer-compact">
                <li className="flex items-center gap-2 justify-start md:justify-end">
                  <span className="whitespace-nowrap">Free and open-source software</span>
                  <a
                    href="https://github.com/AnthusAI/Kanbus"
                    className="text-muted hover:text-foreground transition-colors shrink-0"
                    aria-label="Kanbus on GitHub"
                  >
                    <svg
                      className="h-4 w-4"
                      fill="currentColor"
                      viewBox="0 0 24 24"
                      aria-hidden="true"
                    >
                      <path
                        fillRule="evenodd"
                        d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"
                        clipRule="evenodd"
                      />
                    </svg>
                  </a>
                </li>
                <li className="text-left md:text-right">
                  <a
                    href="https://anth.us/ryan/"
                    className="text-muted hover:text-foreground transition-colors whitespace-nowrap block md:inline-block"
                  >
                    by Ryan Porter
                  </a>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
};

export default Layout;
