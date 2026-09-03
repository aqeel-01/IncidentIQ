import { formatNumber } from "@/utils/format";

type StatCardProps = {
  label: string;
  value: number | null;
  hint: string;
  tone?: "default" | "danger" | "accent";
  active?: boolean;
  loading?: boolean;
  onClick?: () => void;
};

export function StatCard({
  label,
  value,
  hint,
  tone = "default",
  active = false,
  loading = false,
  onClick,
}: StatCardProps) {
  const className = [
    "stat-card",
    `stat-card--${tone}`,
    active ? "stat-card--active" : "",
    onClick ? "stat-card--interactive" : "",
  ]
    .filter(Boolean)
    .join(" ");

  const body = (
    <>
      <span className="stat-card__label">{label}</span>
      <span className="stat-card__value mono" aria-busy={loading}>
        {loading || value === null ? (
          <span className="stat-card__skeleton" aria-label="Loading" />
        ) : (
          formatNumber(value)
        )}
      </span>
      <span className="stat-card__hint">{hint}</span>
    </>
  );

  if (onClick) {
    return (
      <button
        type="button"
        className={className}
        onClick={onClick}
        aria-pressed={active}
      >
        {body}
      </button>
    );
  }

  return <div className={className}>{body}</div>;
}
