export type HealthResponse = {
  status: string;
  service: string;
  version: string;
  environment: string;
};

export type ReadinessResponse = {
  status: string;
  checks: Record<string, Record<string, unknown>>;
};

export type IncidentSeverity =
  | "INFO"
  | "LOW"
  | "MEDIUM"
  | "HIGH"
  | "CRITICAL";

export type IncidentStatus =
  | "OPEN"
  | "INVESTIGATING"
  | "IDENTIFIED"
  | "RESOLVED"
  | "CLOSED";

export type Incident = {
  id: number;
  project_id: number;
  service_id: number | null;
  title: string;
  environment: string;
  severity: IncidentSeverity;
  status: IncidentStatus;
  started_at: string;
  ended_at: string | null;
  occurrence_count: number;
  fingerprint: string;
  created_at: string;
  updated_at: string;
  deduplicated?: boolean;
};

export type IncidentListResponse = {
  items: Incident[];
  total: number;
  page: number;
  page_size: number;
};

export type IncidentSummary = {
  project_id: number;
  total: number;
  active: number;
  critical_active: number;
  recent: number;
  recent_window_hours: number;
  by_status: Record<IncidentStatus, number>;
  by_severity: Record<IncidentSeverity, number>;
};

export type InvestigationStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed";

export type InvestigationProgress = {
  completed_stages: string[];
  total_stages: number;
  percent_complete: number;
};

export type Investigation = {
  id: string;
  incident_id: number;
  project_id: number;
  status: InvestigationStatus;
  stage: string;
  progress: InvestigationProgress;
  attempt_count: number;
  error_message: string | null;
  celery_task_id: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type TimelineCategory =
  | "alert"
  | "log"
  | "error"
  | "metric"
  | "deployment"
  | "trace";

export type TimelineEntry = {
  id: string;
  category: TimelineCategory;
  timestamp: string;
  title: string;
  summary: string | null;
  severity: IncidentSeverity | null;
  event_id: number | null;
  error_group_id: number | null;
  metadata: Record<string, unknown>;
};

export type TimelineMarkers = {
  first_anomaly: TimelineEntry | null;
  first_relevant_error: TimelineEntry | null;
  first_alert: TimelineEntry | null;
  recent_deployment: TimelineEntry | null;
  recovery: TimelineEntry | null;
};

export type TemporalCorrelation = {
  kind: string;
  source: TimelineEntry;
  target: TimelineEntry;
  time_difference: string;
  correlation_score: number;
  reason: string;
};

export type DeploymentEvidence = {
  kind: string;
  detail: string;
  weight: number;
};

export type DeploymentCorrelation = {
  is_related: boolean;
  relationship_score: number;
  deployment: TimelineEntry | null;
  supporting_evidence: DeploymentEvidence[];
  contradicting_evidence: DeploymentEvidence[];
  summary: string;
};

export type ServiceRelationship = {
  kind: string;
  source_id: string;
  source_label: string;
  target_id: string;
  target_label: string;
  correlation_score: number;
  evidence: Array<{ signal: string; detail: string; weight: number }>;
  reason: string;
  source_entry_id: string | null;
  target_entry_id: string | null;
};

export type ServiceCorrelation = {
  relationships: ServiceRelationship[];
  dependencies: Array<{
    source_service: string;
    target_service: string;
    inferred_from: string;
  }>;
  services: string[];
};

export type TimelineResponse = {
  incident_id: number;
  project_id: number;
  started_at: string;
  ended_at: string | null;
  window_start: string;
  window_end: string;
  entries: TimelineEntry[];
  markers: TimelineMarkers;
  counts: Record<string, number>;
  correlations: TemporalCorrelation[];
  deployment_correlation: DeploymentCorrelation | null;
  service_correlation: ServiceCorrelation | null;
};

export type EvidenceStance = "supporting" | "contradicting" | "neutral";

export type EvidenceItem = {
  key: string;
  source: string;
  timestamp: string;
  event_reference: {
    event_id: number | null;
    error_group_id: number | null;
    timeline_entry_id: string | null;
  };
  description: string;
  value: string | number | boolean | null;
  confidence: number;
  supporting_or_contradicting: EvidenceStance;
};

export type EvidenceRelation = {
  key: string;
  source_evidence_key: string;
  target_evidence_key: string;
  kind: string;
  confidence: number;
  description: string | null;
};

export type EvidenceGraphNode = {
  id: string;
  kind: string;
  label: string;
  timestamp: string;
  event_reference: {
    event_id: number | null;
    error_group_id: number | null;
    timeline_entry_id: string | null;
  };
  confidence: number;
  description: string | null;
};

export type EvidenceGraphEdge = {
  key: string;
  source_id: string;
  target_id: string;
  kind: string;
  confidence: number;
  reason: string;
};

export type EvidenceGraph = {
  incident_id: number;
  project_id: number;
  nodes: EvidenceGraphNode[];
  edges: EvidenceGraphEdge[];
  chain: string[];
  summary: string;
};

export type EvidenceQuality = {
  score: number;
  breakdown: {
    source_diversity: number;
    temporal_consistency: number;
    correlation_strength: number;
    completeness: number;
    consistency: number;
  };
  summary: string;
};

export type EvidenceGroup = {
  id: number | null;
  incident_id: number;
  project_id: number;
  built_at: string;
  engine_version: string;
  summary: string | null;
  evidence: EvidenceItem[];
  relations: EvidenceRelation[];
  evidence_graph: EvidenceGraph | null;
  quality: EvidenceQuality | null;
  metadata: Record<string, unknown>;
};

export type RCAStatus =
  | "confident"
  | "low_confidence"
  | "no_confident_root_cause";

export type RCAHypothesis = {
  title: string;
  description: string;
  confidence: number;
  rationale: string | null;
};

export type RCAEvidence = {
  key: string;
  description: string;
  confidence: number;
  source: string | null;
};

export type VerificationStep = {
  title: string;
  description: string;
  priority: number;
};

export type RCAResult = {
  status: RCAStatus;
  primary_hypothesis: RCAHypothesis | null;
  confidence: number;
  supporting_evidence: RCAEvidence[];
  contradicting_evidence: RCAEvidence[];
  alternative_hypotheses: RCAHypothesis[];
  verification_steps: VerificationStep[];
  evidence_quality: number;
};

export type HistoricalRCARecord = {
  id: number;
  project_id: number;
  incident_id: number;
  investigation_job_id: string | null;
  evidence_group_id: number | null;
  status: RCAStatus;
  confidence: number;
  evidence_quality: number;
  ai_provider: string;
  ai_model: string;
  engine_version: string;
  prompt_version: string;
  result: RCAResult;
  created_at: string;
  updated_at: string;
};

export type ConnectorType =
  | "opensearch"
  | "elasticsearch"
  | "database"
  | "prometheus"
  | "github"
  | "azure_devops";

export type ConfiguredConnector = {
  id: number;
  project_id: number;
  name: string;
  connector_type: ConnectorType;
  enabled: boolean;
  settings: Record<string, unknown>;
  configured_credentials: string[];
  last_tested_at: string | null;
  last_test_success: boolean | null;
  last_test_detail: string | null;
  created_at: string;
  updated_at: string;
};

export type ConnectorListResponse = {
  items: ConfiguredConnector[];
  total: number;
};

export type ConnectorTypeInfo = {
  connector_type: ConnectorType;
  label: string;
  secret_fields: string[];
  setting_fields: string[];
};

export type ConnectorTypesResponse = {
  items: ConnectorTypeInfo[];
};

export type ConnectorConnectionTest = {
  connector_id: number;
  connector_type: ConnectorType;
  name: string;
  success: boolean;
  detail: string;
  tested_at: string;
  connector: ConfiguredConnector;
};
