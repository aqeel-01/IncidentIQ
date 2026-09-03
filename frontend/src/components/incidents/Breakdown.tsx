import { formatNumber } from "@/utils/format";

type BreakdownRow<K extends string> = {
  key: K;
  label: string;
  count: number;
};

type BreakdownProps<K extends string> = {
  title: string;
  rows: BreakdownRow<K>[];
  total: number;
  selected: readonly K[];
  variant: "severity" | "status";
  onToggle: (key: K) => void;
};

export function Breakdown<K extends string>({
  title,
  rows,
  total,
  selected,
  variant,
  onToggle,
}: BreakdownProps<K>) {
  return (
    <section className="panel breakdown">
      <h2>{title}</h2>
      <ul className="breakdown__list">
        {rows.map((row) => {
          const share = total > 0 ? (row.count / total) * 100 : 0;
          const active = selected.includes(row.key);
          return (
            <li key={row.key}>
              <button
                type="button"
                className={`breakdown__row ${active ? "breakdown__row--on" : ""}`}
                onClick={() => onToggle(row.key)}
                aria-pressed={active}
                title={`Filter by ${row.label}`}
              >
                <span className="breakdown__label">{row.label}</span>
                <span className="breakdown__bar" aria-hidden="true">
                  <span
                    className={`breakdown__fill breakdown__fill--${variant} breakdown__fill--${row.key.toLowerCase()}`}
                    style={{ width: `${share}%` }}
                  />
                </span>
                <span className="breakdown__count mono">
                  {formatNumber(row.count)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
