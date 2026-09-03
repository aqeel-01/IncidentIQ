import { useMemo, useState } from "react";

import type {
  EvidenceGraph,
  EvidenceGroup,
  EvidenceGraphNode,
} from "@/api/types";
import { formatDateTime } from "@/utils/format";

const LANE_ORDER = [
  "deployment",
  "metric_anomaly",
  "error_increase",
  "service_failure",
  "incident",
] as const;

const LANE_LABELS: Record<(typeof LANE_ORDER)[number], string> = {
  deployment: "Deployment",
  metric_anomaly: "Anomaly",
  error_increase: "Error",
  service_failure: "Service",
  incident: "Incident",
};

const LANE_COLORS: Record<(typeof LANE_ORDER)[number], string> = {
  deployment: "deployment",
  metric_anomaly: "metric",
  error_increase: "error",
  service_failure: "service",
  incident: "incident",
};

type EvidenceGraphVisualizationProps = {
  graph: EvidenceGraph;
  evidence: EvidenceGroup["evidence"];
};

export function EvidenceGraphVisualization({
  graph,
  evidence,
}: EvidenceGraphVisualizationProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(
    graph.chain[0] ?? graph.nodes[0]?.id ?? null,
  );
  const [selectedEdgeKey, setSelectedEdgeKey] = useState<string | null>(null);

  const nodesByLane = useMemo(() => {
    const grouped = new Map<string, EvidenceGraph["nodes"]>();
    for (const lane of LANE_ORDER) {
      grouped.set(lane, []);
    }
    for (const node of graph.nodes) {
      const nodes = grouped.get(node.kind) ?? [];
      nodes.push(node);
      grouped.set(node.kind, nodes);
    }
    return grouped;
  }, [graph.nodes]);

  const selectedNode =
    graph.nodes.find((node) => node.id === selectedNodeId) ?? null;
  const selectedEdge =
    graph.edges.find((edge) => edge.key === selectedEdgeKey) ?? null;
  const selectedEvidence = selectedNode
    ? evidence.find((item) => isSameReference(item.event_reference, selectedNode.event_reference))
    : null;

  return (
    <div className="evidence-graph">
      <div className="evidence-graph__toolbar">
        <div>
          <h3>Evidence relationships</h3>
          <p>
            Follow the strongest available path from a deployment or anomaly
            through errors and services to this incident.
          </p>
        </div>
        <div className="evidence-graph__legend" aria-label="Graph legend">
          {LANE_ORDER.map((lane) => (
            <span key={lane}>
              <i className={`legend-dot legend-dot--${LANE_COLORS[lane]}`} />
              {LANE_LABELS[lane]}
            </span>
          ))}
        </div>
      </div>

      {graph.nodes.length === 0 ? (
        <p className="muted">The evidence graph contains no nodes.</p>
      ) : (
        <div className="evidence-graph__canvas" role="group" aria-label="Evidence graph">
          <div className="evidence-graph__lanes">
            {LANE_ORDER.map((lane) => {
              const nodes = nodesByLane.get(lane) ?? [];
              return (
                <div className="evidence-graph__lane" key={lane}>
                  <div className="evidence-graph__lane-label">
                    <i className={`legend-dot legend-dot--${LANE_COLORS[lane]}`} />
                    {LANE_LABELS[lane]}
                  </div>
                  <div className="evidence-graph__nodes">
                    {nodes.length > 0 ? (
                      nodes.map((node) => (
                        <GraphNode
                          key={node.id}
                          node={node}
                          selected={node.id === selectedNodeId}
                          onSelect={() => {
                            setSelectedNodeId(node.id);
                            setSelectedEdgeKey(null);
                          }}
                        />
                      ))
                    ) : (
                      <span className="evidence-graph__missing">No signal</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          {graph.chain.length > 1 ? (
            <div className="evidence-graph__chain" aria-label="Primary evidence chain">
              {graph.chain.map((nodeId, index) => {
                const node = graph.nodes.find((candidate) => candidate.id === nodeId);
                return (
                  <span key={`${nodeId}-${index}`}>
                    {node?.label ?? nodeId}
                    {index < graph.chain.length - 1 ? <b> → </b> : null}
                  </span>
                );
              })}
            </div>
          ) : null}
        </div>
      )}

      <div className="evidence-graph__details">
        <div className="evidence-graph__detail-panel">
          <div className="evidence-graph__detail-heading">
            <h3>{selectedNode ? selectedNode.label : "Select a node"}</h3>
            {selectedNode ? (
              <span className="confidence mono">
                {formatPercent(selectedNode.confidence)}
              </span>
            ) : null}
          </div>
          {selectedNode ? (
            <>
              <p>{selectedNode.description ?? "No node description available."}</p>
              <dl className="evidence-detail-list">
                <div>
                  <dt>Type</dt>
                  <dd>{humanize(selectedNode.kind)}</dd>
                </div>
                <div>
                  <dt>Observed</dt>
                  <dd>
                    <time dateTime={selectedNode.timestamp}>
                      {formatDateTime(selectedNode.timestamp)}
                    </time>
                  </dd>
                </div>
                <div>
                  <dt>Reference</dt>
                  <dd className="mono">
                    {formatReference(selectedNode.event_reference)}
                  </dd>
                </div>
              </dl>
              {selectedEvidence ? (
                <div className="evidence-detail-source">
                  <span className="evidence-source">Source information</span>
                  <strong>{humanize(selectedEvidence.source)}</strong>
                  <p>{selectedEvidence.description}</p>
                  <span className="mono">
                    {humanize(selectedEvidence.supporting_or_contradicting)} ·{" "}
                    {formatPercent(selectedEvidence.confidence)}
                  </span>
                </div>
              ) : (
                <p className="muted evidence-detail-source">
                  No direct evidence item is linked to this graph node.
                </p>
              )}
            </>
          ) : (
            <p className="muted">Choose a graph node to inspect its details.</p>
          )}
        </div>

        <div className="evidence-graph__detail-panel">
          <div className="evidence-graph__detail-heading">
            <h3>{selectedEdge ? selectedEdge.kind.replaceAll("_", " ") : "Relationships"}</h3>
            <span className="section-count mono">{graph.edges.length}</span>
          </div>
          {graph.edges.length > 0 ? (
            <ul className="relationship-list">
              {graph.edges.map((edge) => {
                const source = graph.nodes.find((node) => node.id === edge.source_id);
                const target = graph.nodes.find((node) => node.id === edge.target_id);
                const selected = edge.key === selectedEdgeKey;
                return (
                  <li key={edge.key}>
                    <button
                      type="button"
                      className={`relationship-row ${selected ? "relationship-row--selected" : ""}`}
                      onClick={() => {
                        setSelectedEdgeKey(edge.key);
                        setSelectedNodeId(edge.target_id);
                      }}
                      aria-pressed={selected}
                    >
                      <span>{source?.label ?? edge.source_id}</span>
                      <b>→</b>
                      <span>{target?.label ?? edge.target_id}</span>
                      <small className="mono">{formatPercent(edge.confidence)}</small>
                    </button>
                    {selected ? <p className="relationship-reason">{edge.reason}</p> : null}
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="muted">No graph relationships were produced.</p>
          )}
        </div>
      </div>
    </div>
  );
}

function GraphNode({
  node,
  selected,
  onSelect,
}: {
  node: EvidenceGraphNode;
  selected: boolean;
  onSelect: () => void;
}) {
  const color = LANE_COLORS[node.kind as (typeof LANE_ORDER)[number]] ?? "default";
  return (
    <button
      type="button"
      className={`graph-node graph-node--${color} ${selected ? "graph-node--selected" : ""}`}
      onClick={onSelect}
      aria-pressed={selected}
      title={node.description ?? node.label}
    >
      <strong>{node.label}</strong>
      <small className="mono">{formatPercent(node.confidence)}</small>
    </button>
  );
}

function isSameReference(
  left: EvidenceGroup["evidence"][number]["event_reference"],
  right: EvidenceGraphNode["event_reference"],
): boolean {
  return (
    (left.timeline_entry_id !== null &&
      left.timeline_entry_id === right.timeline_entry_id) ||
    (left.event_id !== null && left.event_id === right.event_id) ||
    (left.error_group_id !== null && left.error_group_id === right.error_group_id)
  );
}

function formatReference(reference: EvidenceGraphNode["event_reference"]): string {
  if (reference.timeline_entry_id) return reference.timeline_entry_id;
  if (reference.event_id !== null) return `event:${reference.event_id}`;
  if (reference.error_group_id !== null) return `error_group:${reference.error_group_id}`;
  return "none";
}

function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function humanize(value: string): string {
  return value.replaceAll("_", " ");
}
