import type { Investigation } from "@/api/types";

const STAGE_LABELS: Record<string, string> = {
  queued: "Queued",
  collect_sources: "Collecting sources",
  parse: "Parsing records",
  normalize: "Normalizing events",
  dedupe: "Deduplicating",
  group_errors: "Grouping errors",
  anomalies: "Detecting anomalies",
  timeline: "Building timeline",
  correlate: "Correlating signals",
  evidence: "Building evidence",
  quality: "Scoring evidence",
  rca_package: "Preparing RCA",
  run_rca: "Running RCA",
  persist_rca: "Saving RCA",
  completed: "Completed",
  failed: "Failed",
};

export function InvestigationProgress({
  investigation,
}: {
  investigation: Investigation;
}) {
  const percent = investigation.progress.percent_complete;
  const stateLabel =
    investigation.status === "queued"
      ? "Queued"
      : investigation.status === "running"
        ? "In progress"
        : investigation.status === "completed"
          ? "Completed"
          : "Failed";

  return (
    <div
      className={`investigation-progress investigation-progress--${investigation.status}`}
      role="status"
    >
      <div className="investigation-progress__top">
        <div>
          <span className="investigation-progress__state">{stateLabel}</span>
          <strong>{STAGE_LABELS[investigation.stage] ?? investigation.stage}</strong>
        </div>
        <span className="mono">{percent}%</span>
      </div>
      <div
        className="progress-track"
        role="progressbar"
        aria-label="Investigation progress"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
      >
        <span style={{ width: `${percent}%` }} />
      </div>
      {investigation.error_message ? (
        <p className="investigation-progress__error">
          {investigation.error_message}
        </p>
      ) : null}
    </div>
  );
}
