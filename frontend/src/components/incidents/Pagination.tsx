import { formatNumber } from "@/utils/format";

type PaginationProps = {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
};

export function Pagination({
  page,
  pageSize,
  total,
  onPageChange,
}: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const first = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const last = Math.min(page * pageSize, total);

  return (
    <nav className="pagination" aria-label="Pagination">
      <p className="pagination__summary">
        {total === 0
          ? "No results"
          : `Showing ${formatNumber(first)}–${formatNumber(last)} of ${formatNumber(total)}`}
      </p>
      <div className="pagination__controls">
        <button
          type="button"
          className="button button--ghost"
          onClick={() => onPageChange(1)}
          disabled={page <= 1}
          aria-label="First page"
        >
          «
        </button>
        <button
          type="button"
          className="button button--ghost"
          onClick={() => onPageChange(page - 1)}
          disabled={page <= 1}
        >
          Previous
        </button>
        <span className="pagination__page mono">
          {page} / {totalPages}
        </span>
        <button
          type="button"
          className="button button--ghost"
          onClick={() => onPageChange(page + 1)}
          disabled={page >= totalPages}
        >
          Next
        </button>
        <button
          type="button"
          className="button button--ghost"
          onClick={() => onPageChange(totalPages)}
          disabled={page >= totalPages}
          aria-label="Last page"
        >
          »
        </button>
      </div>
    </nav>
  );
}
