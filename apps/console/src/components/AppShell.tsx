import React from "react";

interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="app-shell h-screen p-1 min-[321px]:p-2 sm:p-3 md:p-4 pt-1 min-[321px]:pt-1 relative overflow-hidden">
      <div className="flex h-full flex-col">{children}</div>
    </div>
  );
}
