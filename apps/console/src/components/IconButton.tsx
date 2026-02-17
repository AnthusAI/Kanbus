import React from "react";

interface IconButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
}

export function IconButton({ icon: Icon, label, className = "", ...buttonProps }: IconButtonProps) {
  const baseClasses =
    "flex items-center justify-center rounded-full bg-[var(--column)] px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-muted h-8";

  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={`${baseClasses}${className ? ` ${className}` : ""}`}
      {...buttonProps}
    >
      <Icon className="h-4 w-4" />
    </button>
  );
}

