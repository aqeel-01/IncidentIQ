import { Link } from "react-router-dom";

import type { Incident } from "@/api/types";
import { SeverityBadge, StatusBadge } from "@/components/incidents/Badges";
import { paths } from "@/routes/paths";
import {
  formatDateTime,
  formatNumber,
  formatRelativeTime,
} from "@/utils/format";

type IncidentsTableProps = {
  incidents: Incident[];
  loading?: boolean;
};

export function IncidentsTable({ incidents, loading = false }: IncidentsTableProps) {
  return (
    <div
      className={`table-wrap ${loading ? "table-wrap--loading" : ""}`}
      aria-busy={loading}
    >
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col">Incident</th>
            <th scope="col">Severity</th>
            <th scope="col">Status</th>
            <th scope="col" className="num">
              Occurrences
            </th>
            <th scope="col">Started</th>
            <th scope="col">Environment</th>
          </tr>
        </thead>
        <tbody>
          {incidents.map((incident) => (
            <tr key={incident.id}>
              <td>
                <Link
                  className="table-title"
                  to={paths.incidentDetail(incident.id)}
                >
                  {incident.title}
                </Link>
                <div className="table-sub mono">
                  #{incident.id}
                  {incident.service_id !== null
                    ? ` · service ${incident.service_id}`
                    : ""}
                </div>
              </td>
              <td>
                <SeverityBadge severity={incident.severity} />
              </td>
              <td>
                <StatusBadge status={incident.status} />
              </td>
              <td className="num">
                <span
                  className={`count ${
                    incident.occurrence_count > 1 ? "count--repeat" : ""
                  }`}
                  title={`${incident.occurrence_count} occurrence(s)`}
                >
                  {formatNumber(incident.occurrence_count)}
                </span>
              </td>
              <td>
                <time
                  dateTime={incident.started_at}
                  title={formatDateTime(incident.started_at)}
                >
                  {formatRelativeTime(incident.started_at)}
                </time>
                {incident.ended_at ? (
                  <div className="table-sub">
                    ended {formatRelativeTime(incident.ended_at)}
                  </div>
                ) : null}
              </td>
              <td className="mono">{incident.environment}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
