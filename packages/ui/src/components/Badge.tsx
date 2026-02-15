import * as React from "react";
import { cn } from "../utils/cn";

export const Badge = React.forwardRef<
  HTMLSpanElement,
  React.HTMLAttributes<HTMLSpanElement>
>(({ className, ...props }, ref) => (
  <span
    ref={ref}
    className={cn(
      "badge inline-flex items-center gap-2 px-3 py-2 uppercase tracking-[0.08em]",
      className
    )}
    {...props}
  />
));

Badge.displayName = "Badge";
