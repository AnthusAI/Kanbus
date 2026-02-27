import * as React from "react";
import Layout from "./Layout";

type SidebarLink = {
  label: string;
  href: string;
  isHeader?: boolean;
};

const sidebarLinks: SidebarLink[] = [
  { label: "Overview", href: "/docs" },
  { label: "CLI Reference", href: "/docs/cli" },
  { label: "Configuration", href: "/docs/configuration" },
  { label: "Directory Structure", href: "/docs/directory-structure" },
  { label: "Features", href: "#", isHeader: true },
  { label: "Core Management", href: "/docs/features/core-management" },
  { label: "Kanban Board", href: "/docs/features/kanban-board" },
  { label: "Jira Sync", href: "/docs/features/jira-sync" },
  { label: "Local Tasks", href: "/docs/features/local-tasks" },
  { label: "Virtual Projects", href: "/docs/features/virtual-projects" },
  { label: "Beads Mode", href: "/docs/features/beads-compatibility" },
  { label: "VS Code Plugin", href: "/docs/features/vscode-plugin" },
  { label: "Policy as Code", href: "/docs/features/policy-as-code" }
];

type DocsLayoutProps = {
  children: React.ReactNode;
  currentPath?: string;
};

const DocsLayout = ({ children, currentPath }: DocsLayoutProps) => {
  return (
    <Layout>
      <div className="max-w-7xl mx-auto px-6 lg:px-8 py-12 w-full flex flex-col md:flex-row gap-12">
        <aside className="md:w-64 flex-shrink-0">
          <nav className="sticky top-24">
            <h3 className="text-sm font-semibold text-foreground mb-4 tracking-wider uppercase">
              Documentation
            </h3>
            <ul className="space-y-2">
              {sidebarLinks.map((link) => {
                if (link.isHeader) {
                  return (
                    <li key={link.label} className="pt-4">
                      <h4 className="text-xs font-semibold text-muted tracking-wider uppercase px-3">
                        {link.label}
                      </h4>
                    </li>
                  );
                }
                // Determine if active. For overview, exact match, others prefix match
                const isActive = currentPath === link.href || (link.href !== "/docs" && currentPath?.startsWith(link.href));
                return (
                  <li key={link.href}>
                    <a
                      href={link.href}
                      className={`block px-3 py-2 text-sm rounded-md transition-all border-l-2 ${
                        isActive
                          ? "bg-selected/10 text-selected font-medium border-selected"
                          : "text-muted hover:text-foreground hover:bg-card-muted/50 border-transparent"
                      }`}
                    >
                      {link.label}
                    </a>
                  </li>
                );
              })}
            </ul>
          </nav>
        </aside>

        <div className="flex-1 min-w-0 space-y-12">
          {children}
        </div>
      </div>
    </Layout>
  );
};

export default DocsLayout;
