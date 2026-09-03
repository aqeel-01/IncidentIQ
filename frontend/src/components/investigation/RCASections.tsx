import type { CSSProperties } from "react";

import type { HistoricalRCARecord, RCAHypothesis } from "@/api/types";
import {
  InvestigationSection,
  SectionEmpty,
} from "@/components/investigation/InvestigationSection";
import { formatDateTime } from "@/utils/format";

export function RCASection({ record }: { record: HistoricalRCARecord }) {
  const result = record.result;
  const primary = result.primary_hypothesis;

  return (
    <InvestigationSection
      id="rca"
      title="RCA"
      description={`Generated ${formatDateTime(record.created_at)} using ${record.ai_provider} / ${record.ai_model}.`}
      aside={
        <span className={`rca-status rca-status--${result.status}`}>
          {humanize(result.status)}
        </span>
      }
    >
      {primary ? (
        <div className="root-cause">
          <div className="root-cause__confidence">
            <span className="mono">{formatPercent(result.confidence)}</span>
            <small>confidence</small>
          </div>
          <div>
            <p className="root-cause__label">Primary root cause</p>
            <h3>{primary.title}</h3>
            <p>{primary.description}</p>
            {primary.rationale ? (
              <p className="root-cause__rationale">{primary.rationale}</p>
            ) : null}
          </div>
        </div>
      ) : (
        <SectionEmpty>
          The analysis did not identify a sufficiently confident root cause.
        </SectionEmpty>
      )}

      {(result.supporting_evidence.length > 0 ||
        result.contradicting_evidence.length > 0) && (
        <div className="rca-evidence-grid">
          <EvidenceSummary
            title="Supporting"
            tone="supporting"
            items={result.supporting_evidence}
          />
          <EvidenceSummary
            title="Contradicting"
            tone="contradicting"
            items={result.contradicting_evidence}
          />
        </div>
      )}
    </InvestigationSection>
  );
}

export function HypothesesSection({
  record,
}: {
  record: HistoricalRCARecord;
}) {
  const hypotheses = [
    ...(record.result.primary_hypothesis
      ? [record.result.primary_hypothesis]
      : []),
    ...record.result.alternative_hypotheses,
  ];

  return (
    <InvestigationSection
      id="hypotheses"
      title="Hypotheses"
      description="Ranked explanations produced by the RCA engine."
      count={hypotheses.length}
    >
      {hypotheses.length === 0 ? (
        <SectionEmpty>No hypotheses were generated.</SectionEmpty>
      ) : (
        <ol className="hypothesis-list">
          {hypotheses.map((hypothesis, index) => (
            <HypothesisCard
              key={`${hypothesis.title}-${index}`}
              hypothesis={hypothesis}
              rank={index + 1}
              primary={index === 0 && record.result.primary_hypothesis !== null}
            />
          ))}
        </ol>
      )}
    </InvestigationSection>
  );
}

export function VerificationSection({
  record,
}: {
  record: HistoricalRCARecord;
}) {
  const steps = record.result.verification_steps;
  return (
    <InvestigationSection
      id="verification"
      title="Verification"
      description="Recommended checks to validate or disprove the leading hypothesis."
      count={steps.length}
    >
      {steps.length === 0 ? (
        <SectionEmpty>No verification steps were generated.</SectionEmpty>
      ) : (
        <ol className="verification-list">
          {steps.map((step, index) => (
            <li key={`${step.title}-${index}`}>
              <span className="verification-list__number mono">{index + 1}</span>
              <div>
                <div className="verification-list__heading">
                  <strong>{step.title}</strong>
                  <span>Priority {step.priority}</span>
                </div>
                <p>{step.description}</p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </InvestigationSection>
  );
}

function HypothesisCard({
  hypothesis,
  rank,
  primary,
}: {
  hypothesis: RCAHypothesis;
  rank: number;
  primary: boolean;
}) {
  return (
    <li className={`hypothesis-card ${primary ? "hypothesis-card--primary" : ""}`}>
      <div className="hypothesis-card__rank mono">{rank}</div>
      <div>
        <div className="hypothesis-card__heading">
          <h3>{hypothesis.title}</h3>
          {primary ? <span>Primary</span> : null}
        </div>
        <p>{hypothesis.description}</p>
        {hypothesis.rationale ? (
          <p className="hypothesis-card__rationale">{hypothesis.rationale}</p>
        ) : null}
      </div>
      <div
        className="confidence-ring mono"
        style={
          {
            "--confidence": `${hypothesis.confidence * 360}deg`,
          } as CSSProperties
        }
        aria-label={`${formatPercent(hypothesis.confidence)} confidence`}
      >
        {formatPercent(hypothesis.confidence)}
      </div>
    </li>
  );
}

function EvidenceSummary({
  title,
  tone,
  items,
}: {
  title: string;
  tone: "supporting" | "contradicting";
  items: HistoricalRCARecord["result"]["supporting_evidence"];
}) {
  return (
    <div className={`rca-evidence-summary rca-evidence-summary--${tone}`}>
      <h3>{title}</h3>
      {items.length === 0 ? (
        <p className="muted">No {title.toLowerCase()} evidence.</p>
      ) : (
        <ul>
          {items.map((item) => (
            <li key={item.key}>
              <span>{item.description}</span>
              <small className="mono">{formatPercent(item.confidence)}</small>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function humanize(value: string): string {
  return value.replaceAll("_", " ");
}
