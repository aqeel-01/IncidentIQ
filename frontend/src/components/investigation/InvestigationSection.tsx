import type { ReactNode } from "react";

type InvestigationSectionProps = {
  id: string;
  title: string;
  description?: string;
  count?: number;
  aside?: ReactNode;
  children: ReactNode;
};

export function InvestigationSection({
  id,
  title,
  description,
  count,
  aside,
  children,
}: InvestigationSectionProps) {
  return (
    <section id={id} className="panel investigation-section">
      <header className="investigation-section__header">
        <div>
          <div className="investigation-section__title-row">
            <h2>{title}</h2>
            {count !== undefined ? (
              <span className="section-count mono">{count}</span>
            ) : null}
          </div>
          {description ? (
            <p className="investigation-section__description">{description}</p>
          ) : null}
        </div>
        {aside}
      </header>
      {children}
    </section>
  );
}

export function SectionEmpty({
  children,
  pending = false,
}: {
  children: ReactNode;
  pending?: boolean;
}) {
  return (
    <div className={`section-empty ${pending ? "section-empty--pending" : ""}`}>
      <span className="section-empty__icon" aria-hidden="true">
        {pending ? "…" : "—"}
      </span>
      <p>{children}</p>
    </div>
  );
}
