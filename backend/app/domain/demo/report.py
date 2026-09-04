"""Human-readable formatting for the IncidentIQ demo result."""

from __future__ import annotations

from app.domain.demo.types import DemoResult


def format_demo_report(result: DemoResult) -> str:
    """Render the final demo RCA fields for terminal display."""

    lines: list[str] = [
        "=" * 72,
        "IncidentIQ end-to-end demo",
        "=" * 72,
        f"Scenario:          {result.scenario}",
        f"Reproducible:      {result.reproducible} (deterministic fake AI)",
        f"Incident:          #{result.incident_id} - {result.incident_title}",
        f"Service:           {result.service}",
        f"Job:               {result.pipeline.job_id} ({result.pipeline.status})",
        f"Stages completed:  {len(result.pipeline.stages_completed)}",
        "",
        "--- Pipeline signals ---",
        f"Timeline entries:  {result.timeline.entry_count}",
        f"Anomalies:         {result.timeline.anomaly_count}",
        f"Correlations:      {result.timeline.correlation_count}",
        f"Deployment link:   {result.timeline.deployment_correlation or 'n/a'}",
        f"Evidence items:    {result.evidence.item_count}",
        f"Evidence quality:  {result.evidence_quality}/100",
        "",
        "--- Ranked RCA ---",
        f"Status:            {result.rca_status.value}",
        f"Confidence:        {result.confidence:.0%}",
        f"Root cause:        {result.root_cause or '(none)'}",
    ]
    if result.root_cause_description:
        lines.append(f"Description:       {result.root_cause_description}")
    if result.root_cause_rationale:
        lines.append(f"Rationale:         {result.root_cause_rationale}")

    lines.extend(["", "Supporting evidence:"])
    if not result.supporting_evidence:
        lines.append("  (none)")
    for item in result.supporting_evidence:
        lines.append(
            f"  - [{item.get('key')}] {item.get('description')} "
            f"(confidence={item.get('confidence')}, source={item.get('source')})"
        )

    lines.extend(["", "Contradicting evidence:"])
    if not result.contradicting_evidence:
        lines.append("  (none)")
    for item in result.contradicting_evidence:
        lines.append(
            f"  - [{item.get('key')}] {item.get('description')} "
            f"(confidence={item.get('confidence')}, source={item.get('source')})"
        )

    lines.extend(["", "Alternative hypotheses:"])
    if not result.alternative_hypotheses:
        lines.append("  (none)")
    for item in result.alternative_hypotheses:
        lines.append(f"  - {item.get('title')} (confidence={item.get('confidence')})")
        if item.get("description"):
            lines.append(f"      {item.get('description')}")

    lines.extend(["", "Verification steps:"])
    if not result.verification_steps:
        lines.append("  (none)")
    for index, item in enumerate(result.verification_steps, start=1):
        lines.append(f"  {index}. [P{item.get('priority')}] {item.get('title')}")
        if item.get("description"):
            lines.append(f"      {item.get('description')}")

    lines.extend(
        [
            "",
            f"AI provider/model: {result.ai_provider} / {result.ai_model}",
            f"Engine/prompt:     {result.engine_version} / {result.prompt_version}",
            "=" * 72,
        ]
    )
    return "\n".join(lines)
