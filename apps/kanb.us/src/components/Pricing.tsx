import * as React from "react";
import { Card, CardContent, CardHeader } from "@kanbus/ui";
import { KANBUS_OFFERS, SHARED_PRICING_COPY, presentOffer } from "../content/offers";

export function Pricing() {
  return (
    <section id="pricing" aria-labelledby="pricing-title" className="py-14 md:py-20 bg-region-alt">
      <div className="max-w-7xl mx-auto px-6 lg:px-8">
        <div className="grid gap-8 lg:grid-cols-[0.85fr_1.15fr] lg:items-end">
          <div>
            <span className="inline-flex items-center rounded-full border border-selected/50 bg-selected/10 px-3 py-1 font-mono text-sm font-medium text-selected">
              Delegated responsibility
            </span>
            <p className="mt-6 max-w-lg text-lg leading-relaxed text-muted">
              You can run Kanbus yourself. If you want help, Anthus can host a board for you, operate a dedicated deployment in your AWS account, or build on Kanbus as part of an engagement.
            </p>
          </div>
          <h2 id="pricing-title" className="text-4xl font-display font-bold tracking-tight text-foreground sm:text-5xl lg:text-6xl lg:leading-[0.9]">
            You choose how much we help
          </h2>
        </div>

        <div className="mt-12 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {KANBUS_OFFERS.map((offer) => {
            const presentation = presentOffer(offer);
            const ctaIsExternal = presentation.ctaHref.startsWith("http");
            return (
              <Card key={offer.rung} className="flex min-h-[260px] flex-col p-7 bg-card">
                <CardHeader className="p-0">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <h3 className="text-2xl font-display font-bold tracking-tight text-foreground">{offer.title}</h3>
                    {presentation.chipText ? (
                      <span className="inline-flex items-center rounded-full border border-selected/50 bg-selected/10 px-2.5 py-0.5 font-mono text-xs font-medium uppercase tracking-[0.08em] text-selected">
                        {presentation.chipText}
                      </span>
                    ) : null}
                  </div>
                </CardHeader>
                <CardContent className="flex flex-1 flex-col p-0">
                  <p className="mt-5 flex-1 leading-relaxed text-muted">{offer.body}</p>
                  <div className="mt-8 border-t border-border pt-5">
                    <p className="text-2xl font-display font-bold tracking-tight text-foreground">
                      {presentation.priceText}
                      {presentation.priceQualifier ? (
                        <span className="ml-2 font-sans text-sm font-normal text-muted">{presentation.priceQualifier}</span>
                      ) : null}
                    </p>
                    {offer.unit ? <p className="mt-1 text-sm text-muted">{offer.unit}</p> : null}
                    {offer.onboarding ? <p className="mt-1 text-sm text-muted">{offer.onboarding}</p> : null}
                    {offer.note ? <p className="mt-1 text-sm text-muted">{offer.note}</p> : null}
                    {presentation.footnote ? <p className="mt-1 text-sm text-muted">{presentation.footnote}</p> : null}
                    <a
                      href={presentation.ctaHref}
                      target={ctaIsExternal ? "_blank" : undefined}
                      rel={ctaIsExternal ? "noopener noreferrer" : undefined}
                      className="cta-button mt-5 px-5 py-2.5 text-sm transition-all hover:brightness-95"
                    >
                      {presentation.ctaLabel}
                    </a>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>

        <div className="mt-16 border-t border-border pt-10">
          <h3 className="text-2xl font-display font-bold tracking-tight text-foreground">Straight answers</h3>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            {SHARED_PRICING_COPY.map((item) => (
              <Card key={item.title} className="p-6 bg-card">
                <CardHeader className="p-0">
                  <h4 className="text-lg font-bold text-foreground">{item.title}</h4>
                </CardHeader>
                <CardContent className="p-0 mt-3">
                  <p className="leading-relaxed text-muted">{item.body}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
