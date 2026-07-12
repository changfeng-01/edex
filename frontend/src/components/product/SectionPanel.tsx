import type { ReactNode } from "react";

export function SectionPanel({ title, description, children, label }: { title: string; description?: string; children: ReactNode; label?: string }) {
  return (
    <section className="section-panel" aria-label={label || title}>
      <div className="section-heading">
        <h2>{title}</h2>
        {description ? <p>{description}</p> : null}
      </div>
      {children}
    </section>
  );
}
