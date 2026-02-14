import React from "react";

interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="h-screen p-3 relative overflow-hidden">
      <div className="flex h-full flex-col">{children}</div>
    </div>
  );
}
