import { useEffect } from "react";

import { getIncidentSummary, listIncidents } from "@/api/incidents";
import { Breakdown } from "@/components/incidents/Breakdown";
import { IncidentFilters } from "@/components/incidents/IncidentFilters";
import { IncidentsTable } from "@/components/incidents/IncidentsTable";
import { Pagination } from "@/components/incidents/Pagination";
import { StatCard } from "@/components/incidents/StatCard";
import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import {
  RECENT_WINDOW_HOURS,
  SEVERITIES,
  SEVERITY_LABELS,
  STATUSES,
  STATUS_LABELS,
} from "@/features/incidents/constants";
import { useIncidentFilters } from "@/features/incidents/useIncidentFilters";
import { useAsync } from "@/hooks/useAsync";
import { formatNumber } from "@/utils/format";

export function IncidentsPage() {
  const {
    filters,
    preset,
    hasActiveFilters,
    setPage,
    setPageSize,
    setProjectId,
    toggleSeverity,
    toggleStatus,
    applyPreset,
    clearFilters,
  } = useIncidentFilters();

  const severityKey = filters.severity.join(",");
  const statusKey = filters.status.join(",");

  const summary = useAsync(
    (signal) =>
      getIncidentSummary(
        { projectId: filters.projectId, recentHours: RECENT_WINDOW_HOURS },
        signal,
      ),
    [filters.projectId],
    { keepPreviousData: true },
  );

  const list = useAsync(
    (signal) =>
      listIncidents(
        {
          projectId: filters.projectId,
          page: filters.page,
          pageSize: filters.pageSize,
          severity: filters.severity,
          status: filters.status,
        },
        signal,
      ),
    [filters.projectId, filters.page, filters.pageSize, severityKey, statusKey],
    { keepPreviousData: true },
  );

  // If filters shrink the result set below the current page, snap back.
  useEffect(() => {
    if (list.status !== "success") {
      return;
    }
    const totalPages = Math.max(1, Math.ceil(list.data.total / filters.pageSize));
    if (filters.page > totalPages) {
      setPage(totalPages);
    }
  }, [list, filters.page, filters.pageSize, setPage]);

  const summaryData = summary.data;
  const listData = list.data;
  const listLoading = list.status === "loading";

  return (
    <section className="page dashboard">
      <div className="page__intro dashboard__intro">
        <div>
          <p className="eyebrow">Incidents</p>
          <h1>Incident dashboard</h1>
          <p className="lede">
            Live view of project <span className="mono">#{filters.projectId}</span>
            . Click a stat or breakdown row to filter the table.
          </p>
        </div>
        <div className="button-row dashboard__actions">
          <button
            type="button"
            className="button button--ghost"
            onClick={() => {
              summary.reload();
              list.reload();
            }}
          >
            Refresh
          </button>
        </div>
      </div>

      {summary.status === "error" && !summaryData ? (
        <ErrorState
          title="Could not load summary"
          message={summary.error}
          onRetry={summary.reload}
        />
      ) : null}

      <div className="stat-grid">
        <StatCard
          label="Active"
          value={summaryData?.active ?? null}
          hint="Open, investigating, or identified"
          tone="accent"
          active={preset === "active"}
          loading={summary.status === "loading" && !summaryData}
          onClick={() => applyPreset("active")}
        />
        <StatCard
          label="Critical"
          value={summaryData?.critical_active ?? null}
          hint="Critical severity, still active"
          tone="danger"
          active={preset === "critical"}
          loading={summary.status === "loading" && !summaryData}
          onClick={() => applyPreset("critical")}
        />
        <StatCard
          label="Recent"
          value={summaryData?.recent ?? null}
          hint={`Started in the last ${RECENT_WINDOW_HOURS}h`}
          loading={summary.status === "loading" && !summaryData}
        />
        <StatCard
          label="Total"
          value={summaryData?.total ?? null}
          hint="All incidents in this project"
          active={preset === "all"}
          loading={summary.status === "loading" && !summaryData}
          onClick={() => applyPreset("all")}
        />
      </div>

      <div className="dashboard__grid">
        <div className="dashboard__main">
          <section className="panel panel--flush">
            <IncidentFilters
              projectId={filters.projectId}
              severity={filters.severity}
              status={filters.status}
              pageSize={filters.pageSize}
              hasActiveFilters={hasActiveFilters}
              onProjectChange={setProjectId}
              onToggleSeverity={toggleSeverity}
              onToggleStatus={toggleStatus}
              onPageSizeChange={setPageSize}
              onClear={clearFilters}
            />

            {list.status === "error" && !listData ? (
              <div className="panel__body">
                <ErrorState
                  title="Could not load incidents"
                  message={list.error}
                  onRetry={list.reload}
                />
              </div>
            ) : null}

            {listLoading && !listData ? (
              <div className="panel__body">
                <LoadingState label="Loading incidents…" />
              </div>
            ) : null}

            {listData ? (
              <>
                {list.status === "error" ? (
                  <p className="inline-error" role="alert">
                    Refresh failed: {list.error}. Showing last known results.
                  </p>
                ) : null}

                {listData.items.length === 0 ? (
                  <div className="panel__body empty-state">
                    <h2>No incidents match</h2>
                    <p>
                      {hasActiveFilters
                        ? "Try widening the status or severity filters."
                        : "This project has no incidents yet."}
                    </p>
                    {hasActiveFilters ? (
                      <button
                        type="button"
                        className="button button--ghost"
                        onClick={clearFilters}
                      >
                        Clear filters
                      </button>
                    ) : null}
                  </div>
                ) : (
                  <IncidentsTable
                    incidents={listData.items}
                    loading={listLoading}
                  />
                )}

                <Pagination
                  page={listData.page}
                  pageSize={listData.page_size}
                  total={listData.total}
                  onPageChange={setPage}
                />
              </>
            ) : null}
          </section>
        </div>

        <aside className="dashboard__side">
          <Breakdown
            title="By status"
            variant="status"
            total={summaryData?.total ?? 0}
            selected={filters.status}
            onToggle={toggleStatus}
            rows={STATUSES.map((status) => ({
              key: status,
              label: STATUS_LABELS[status],
              count: summaryData?.by_status[status] ?? 0,
            }))}
          />
          <Breakdown
            title="By severity"
            variant="severity"
            total={summaryData?.total ?? 0}
            selected={filters.severity}
            onToggle={toggleSeverity}
            rows={SEVERITIES.map((severity) => ({
              key: severity,
              label: SEVERITY_LABELS[severity],
              count: summaryData?.by_severity[severity] ?? 0,
            }))}
          />
          {summaryData ? (
            <p className="side-note">
              {formatNumber(summaryData.total)} incidents indexed for project{" "}
              <span className="mono">#{summaryData.project_id}</span>.
            </p>
          ) : null}
        </aside>
      </div>
    </section>
  );
}
