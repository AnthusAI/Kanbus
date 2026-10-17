export type OfferRung = "open-source" | "hosted" | "dedicated" | "engagement";

export type OfferAvailability = "available" | "beta" | "early-access" | "planned";

export type Offer = {
  product: "Kanbus";
  rung: OfferRung;
  title: string;
  body: string;
  price: string;
  unit?: string;
  onboarding?: string;
  availability: OfferAvailability;
  note?: string;
  cta: {
    label: string;
    href: string;
  };
};

export const ENGAGE_URL = "https://anth.us/engage/";

export const KANBUS_OFFERS: Offer[] = [
  {
    product: "Kanbus",
    rung: "open-source",
    title: "Open source",
    body: "MIT licensed. You deploy and run it.",
    price: "Free",
    availability: "available",
    cta: { label: "Get the source", href: "https://github.com/AnthusAI/Kanbus" },
  },
  {
    product: "Kanbus",
    rung: "hosted",
    title: "Hosted",
    body: "A board in Anthus's multi-tenant service. One Anthus account for every Anthus product. Anthus operates everything. Flat monthly fee per board with a hard usage allowance and no automatic overage.",
    price: "$20/mo",
    unit: "per board",
    availability: "early-access",
    cta: { label: "Start", href: ENGAGE_URL },
  },
  {
    product: "Kanbus",
    rung: "dedicated",
    title: "Dedicated",
    body: "Deployed in your AWS account. Anthus operates it and keeps it updated; we update our own deployments first. You pay AWS and model providers directly.",
    price: "$150/mo",
    onboarding: "$500 onboarding, once",
    availability: "available",
    cta: { label: "Talk to us", href: ENGAGE_URL },
  },
  {
    product: "Kanbus",
    rung: "engagement",
    title: "Engagement",
    body: "Anthus builds something for you with Kanbus and the rest of the Anthus tools, and operates it if you want. Fixed-scope pilot, then monthly.",
    price: "Quoted",
    unit: "Included in any Anthus engagement",
    availability: "available",
    cta: { label: "Talk to us", href: ENGAGE_URL },
  },
];

export const HOSTED_BETA_FOOTNOTE = "Beta accounts are free. We give 30 days' notice before billing starts.";

export const SHARED_PRICING_COPY = [
  {
    title: "Why dedicated",
    body: "Your data never leaves your account. Your own model contracts and keys. Your compliance boundary. No noisy neighbors. You keep running if Anthus disappears. The monthly fee buys updates, monitoring, and a team that has run the same deployment first: we update our own deployments before yours.",
  },
  {
    title: "Who pays",
    body: "Hosted: Anthus pays the infrastructure; model calls are bring your own key or capped by the plan. Dedicated: you pay AWS and your model providers directly; Anthus charges only the operations fee. Engagement: stated in the scope.",
  },
  {
    title: "When you stop paying",
    body: "Hosted workspaces can be exported and are kept read-only for 90 days. Dedicated deployments stay in your account untouched; we stop operating them and delete nothing.",
  },
];

export type OfferPresentation = {
  chipText?: string;
  ctaLabel: string;
  ctaHref: string;
  priceText: string;
  priceQualifier?: string;
  footnote?: string;
};

export function presentOffer(offer: Offer): OfferPresentation {
  switch (offer.availability) {
    case "available":
      return {
        ctaLabel: offer.cta.label,
        ctaHref: offer.cta.href,
        priceText: offer.price,
      };
    case "beta":
      return {
        chipText: "Beta",
        ctaLabel: "Start (beta)",
        ctaHref: offer.cta.href,
        priceText: offer.rung === "hosted" ? `Free during beta, then ${offer.price}` : offer.price,
        priceQualifier: offer.rung === "hosted" ? undefined : "beta pricing",
        footnote: offer.rung === "hosted" ? HOSTED_BETA_FOOTNOTE : undefined,
      };
    case "early-access":
      return {
        chipText: "Early access",
        ctaLabel: "Request access",
        ctaHref: ENGAGE_URL,
        priceText: offer.price,
        priceQualifier: "planned",
      };
    case "planned":
      return {
        chipText: "Planned",
        ctaLabel: "Tell us you want it",
        ctaHref: ENGAGE_URL,
        priceText: offer.price,
        priceQualifier: "planned",
      };
  }
}
