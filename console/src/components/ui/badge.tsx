import * as React from "react";
import { cn } from "./utils";

export const Badge = React.forwardRef<
  HTMLSpanElement,
  React.HTMLAttributes<HTMLSpanElement>
>(({ className, ...props }, ref) => (
  <span ref={ref} className={cn("badge", className)} {...props} />
));

Badge.displayName = "Badge";
