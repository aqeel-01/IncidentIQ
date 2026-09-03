import { useEffect, useState } from "react";

import type { IncidentSeverity, IncidentStatus } from "@/api/types";
import {
  PAGE_SIZES,
  SEVERITIES,
  SEVERITY_LABELS,
  STATUSES,
  STATUS_LABELS,
} from "@/features/incidents/constants";

type IncidentFiltersProps = {
  projectId: number;
  severity: IncidentSeverity[];
  status: IncidentStatus[];
  pageSize: number;
  hasActiveFilters: boolean;
  onProjectChange: (projectId: number) => void;
  onToggleSeverity: (severity: IncidentSeverity) => void;
  onToggleStatus: (status: IncidentStatus) => void;
  onPageSizeChange: (pageSize: number) => void;
  onClear: () => void;
};

export function IncidentFilters({
  projectId,
  severity,
  status,
  pageSize,
  hasActiveFilters,
  onProjectChange,
  onToggleSeverity,
  onToggleStatus,
  onPageSizeChange,
  onClear,
}: IncidentFiltersProps) {
  const [projectDraft, setProjectDraft] = useState(String(projectId));

  useEffect(() => {
    setProjectDraft(String(projectId));
  }, [projectId]);

  function commitProject() {
    const parsed = Number.parseInt(projectDraft, 10);
    if (Number.isInteger(parsed) && parsed > 0 && parsed !== projectId) {
      onProjectChange(parsed);
    } else {
      setProjectDraft(String(projectId));
    }
  }

  return (
    <div className="filter-bar" role="region" aria-label="Incident filters">
      <fieldset className="filter-group">
        <legend>Status</legend>
        <div className="chip-row">
          {STATUSES.map((value) => {
            const checked = status.includes(value);
            return (
              <label
                key={value}
                className={`chip ${checked ? "chip--on" : ""}`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => onToggleStatus(value)}
                />
                {STATUS_LABELS[value]}
              </label>
            );
          })}
        </div>
      </fieldset>

      <fieldset className="filter-group">
        <legend>Severity</legend>
        <div className="chip-row">
          {SEVERITIES.map((value) => {
            const checked = severity.includes(value);
            return (
              <label
                key={value}
                className={`chip chip--${value.toLowerCase()} ${
                  checked ? "chip--on" : ""
                }`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => onToggleSeverity(value)}
                />
                {SEVERITY_LABELS[value]}
              </label>
            );
          })}
        </div>
      </fieldset>

      <div className="filter-bar__controls">
        <label className="control">
          <span>Project</span>
          <input
            className="control__input mono"
            type="number"
            min={1}
            inputMode="numeric"
            value={projectDraft}
            onChange={(event) => setProjectDraft(event.target.value)}
            onBlur={commitProject}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.currentTarget.blur();
              }
            }}
            aria-label="Project ID"
          />
        </label>

        <label className="control">
          <span>Rows</span>
          <select
            className="control__input"
            value={pageSize}
            onChange={(event) =>
              onPageSizeChange(Number.parseInt(event.target.value, 10))
            }
            aria-label="Rows per page"
          >
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>

        <button
          type="button"
          className="button button--ghost"
          onClick={onClear}
          disabled={!hasActiveFilters}
        >
          Clear filters
        </button>
      </div>
    </div>
  );
}
