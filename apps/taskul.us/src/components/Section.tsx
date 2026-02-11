import * as React from "react";

type SectionProps = {
  title: string;
  subtitle?: string;
  variant?: "default" | "alt";
  children: React.ReactNode;
};

const Section = ({ title, subtitle, variant = "default", children }: SectionProps) => {
  const className = variant === "alt" ? "section alt" : "section";

  return (
    <section className={className}>
      <h2>{title}</h2>
      {subtitle ? <p>{subtitle}</p> : null}
      {children}
    </section>
  );
};

export default Section;
