import * as React from "react";
import { Card, CardContent, CardHeader } from "@kanbus/ui";

const rungs = [
  {
    title: "Fork it",
    body: "Kanbus is MIT licensed. Run it in your own repository. Anthus does nothing and charges nothing.",
    price: "No cost",
  },
  {
    title: "Self-setup, managed",
    body: "Set up Kanbus in your environment; we operate the shared services and keep the deployment current.",
    price: "$20 a month",
  },
  {
    title: "Assisted setup, managed",
    body: "We configure Kanbus with you, then operate it and keep the deployment current.",
    price: "$20 a month",
    note: "and $100 once",
  },
  {
    title: "Professional services",
    body: "We adapt Kanbus workflows, integrations, or deployment to fit the way your team works.",
    price: "Quoted",
  },
];

const answers = [
  {
    question: "Will Kanbus always be free to run myself?",
    answer: "Yes. Kanbus is MIT licensed and has no per-seat license fee.",
  },
  {
    question: "What does managed mean?",
    answer: "We operate the agreed shared services, apply updates, and help keep the deployment healthy.",
  },
  {
    question: "Can I move between setup options?",
    answer: "Yes. You can begin with self-setup and add an assisted session later, or take over operation yourself.",
  },
];

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
              You can run Kanbus yourself. If you want help, Anthus can operate a shared setup, configure it with you, or adapt it to your team.
            </p>
          </div>
          <h2 id="pricing-title" className="text-4xl font-display font-bold tracking-tight text-foreground sm:text-5xl lg:text-6xl lg:leading-[0.9]">
            You choose how much we help
          </h2>
        </div>

        <div className="mt-12 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {rungs.map((rung) => (
            <Card key={rung.title} className="flex min-h-[260px] flex-col p-7 bg-card">
              <CardHeader className="p-0">
                <h3 className="text-2xl font-display font-bold tracking-tight text-foreground">{rung.title}</h3>
              </CardHeader>
              <CardContent className="flex flex-1 flex-col p-0">
                <p className="mt-5 flex-1 leading-relaxed text-muted">{rung.body}</p>
                <div className="mt-8 border-t border-border pt-5">
                  <p className="text-2xl font-display font-bold tracking-tight text-foreground">{rung.price}</p>
                  {rung.note ? <p className="mt-1 text-sm text-muted">{rung.note}</p> : null}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        <div className="mt-16 border-t border-border pt-10">
          <h3 className="text-2xl font-display font-bold tracking-tight text-foreground">Straight answers</h3>
          <div className="mt-6 grid gap-4 md:grid-cols-3">
            {answers.map((item) => (
              <Card key={item.question} className="p-6 bg-card">
                <CardHeader className="p-0">
                  <h4 className="text-lg font-bold text-foreground">{item.question}</h4>
                </CardHeader>
                <CardContent className="p-0 mt-3">
                  <p className="leading-relaxed text-muted">{item.answer}</p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
