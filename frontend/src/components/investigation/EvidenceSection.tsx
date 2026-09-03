import type { EvidenceGroup } from "@/api/types";
import { EvidenceGraphVisualization } from "@/components/investigation/EvidenceGraphVisualization";
import {
  InvestigationSection,
  SectionEmpty,
} from "@/components/investigation/InvestigationSection";
import { formatDateTime } from "@/utils/format";

export function EvidenceSection({ evidence }: { evidence: EvidenceGroup }) {
  return (
    <InvestigationSection
      id="evidence"
      title="Evidence"
      description={
        evidence.summary ??
        `Structured evidence package built by engine ${evidence.engine_version}.`
      }
      count={evidence.evidence.length}
      aside={
        evidence.quality ? (
          <div
            className="quality-score"
            title={evidence.quality.summary}
            aria-label={`Evidence quality ${evidence.quality.score} out of 100`}
          >
            <span className="mono">{evidence.quality.score}</span>
            <small>quality</small>
          </div>
        ) : null
      }
    >
      {evidence.evidence.length === 0 ? (
        <SectionEmpty>No structured evidence was produced.</SectionEmpty>
      ) : (
        <ul className="evidence-list">
          {evidence.evidence.map((item) => (
            <li
              key={item.key}
              className={`evidence-card evidence-card--${item.supporting_or_contradicting}`}
            >
              <div className="evidence-card__top">
                <span className="evidence-source">{humanize(item.source)}</span>
                <span className="confidence mono">
                  {formatPercent(item.confidence)}
                </span>
              </div>
              <p>{item.description}</p>
              <div className="evidence-card__footer">
                <span
                  className={`stance stance--${item.supporting_or_contradicting}`}
                >
                  {humanize(item.supporting_or_contradicting)}
                </span>
                <time
                  className="mono"
                  dateTime={item.timestamp}
                  title={formatDateTime(item.timestamp)}
                >
                  {formatDateTime(item.timestamp)}
                </time>
              </div>
            </li>
          ))}
        </ul>
      )}

      {evidence.evidence_graph ? (
        <EvidenceGraphVisualization
          graph={evidence.evidence_graph}
          evidence={evidence.evidence}
        />
      ) : null}
    </InvestigationSection>
  );
}

function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function humanize(value: string): string {
  return value.replaceAll("_", " ");
}
