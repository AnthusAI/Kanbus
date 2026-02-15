import * as React from "react";
import { Card, CardContent, CardHeader } from "@kanbus/ui";

type HeroProps = {
  eyebrow?: string;
  title: string;
  subtitle: string;
  actions?: React.ReactNode;
};

export function Hero({ eyebrow, title, subtitle, actions }: HeroProps): JSX.Element {
  return (
    <Card className="relative isolate overflow-hidden ring-1 ring-border bg-card shadow-card">
      <CardHeader className="flex flex-col items-center gap-4 text-center">
        <h1 className="text-4xl sm:text-5xl font-display font-bold tracking-tight text-foreground leading-tight">
          {title}
        </h1>
        <p className="text-lg leading-8 text-muted max-w-2xl">{subtitle}</p>
      </CardHeader>
      {actions && (
        <CardContent className="flex items-center justify-center gap-4 pb-10">
          {actions}
        </CardContent>
      )}
    </Card>
  );
}
