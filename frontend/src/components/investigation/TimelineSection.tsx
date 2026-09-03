import type { TimelineEntry, TimelineResponse } from "@/api/types";
import {
  InvestigationSection,
  SectionEmpty,
} from "@/components/investigation/InvestigationSection";
import { formatDateTime, formatRelativeTime } from "@/utils/format";

const CATEGORY_LABELS: Record<TimelineEntry["category"], string> = {
  alert: "Alert",
  log: "Log",
  error: "Error",
  metric: "Metric",
  deployment: "Deployment",
  trace: "Trace",
};

export function TimelineSection({ timeline }: { timeline: TimelineResponse }) {
  return (
    <InvestigationSection
      id="timeline"
      title="Timeline"
      description={`Correlated events from ${formatDateTime(timeline.window_start)} to ${formatDateTime(timeline.window_end)}.`}
      count={timeline.entries.length}
    >
      {timeline.entries.length === 0 ? (
        <SectionEmpty>No events were found in the incident window.</SectionEmpty>
      ) : (
        <ol className="incident-timeline">
          {timeline.entries.map((entry) => (
            <li
              key={entry.id}
              className={`incident-timeline__item incident-timeline__item--${entry.category}`}
            >
              <span className="incident-timeline__marker" aria-hidden="true" />
              <div className="incident-timeline__time">
                <time
                  dateTime={entry.timestamp}
                  title={formatDateTime(entry.timestamp)}
                >
                  {formatRelativeTime(entry.timestamp)}
                </time>
                <span className="mono">{formatClock(entry.timestamp)}</span>
              </div>
              <div className="incident-timeline__body">
                <div className="incident-timeline__heading">
                  <span
                    className={`signal-kind signal-kind--${entry.category}`}
                  >
                    {CATEGORY_LABELS[entry.category]}
                  </span>
                  <strong>{entry.title}</strong>
                </div>
                {entry.summary && entry.summary !== entry.title ? (
                  <p>{entry.summary}</p>
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      )}
    </InvestigationSection>
  );
}

function formatClock(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(date);
}
