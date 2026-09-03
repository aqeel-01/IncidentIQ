import { useEffect, useMemo, useState, type FormEvent } from "react";

import { getErrorMessage } from "@/api/errors";
import {
  createConnector,
  deleteConnector,
  disableConnector,
  enableConnector,
  listConnectorTypes,
  listConnectors,
  testConnector,
  updateConnector,
} from "@/api/connectors";
import type {
  ConfiguredConnector,
  ConnectorType,
  ConnectorTypeInfo,
} from "@/api/types";
import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { useAsync } from "@/hooks/useAsync";
import { formatDateTime, formatRelativeTime } from "@/utils/format";

const PROJECT_STORAGE_KEY = "incidentiq.project_id";
const DEFAULT_PROJECT_ID = 1;

const BOOLEAN_FIELDS = new Set(["verify_tls"]);
const NUMBER_FIELDS = new Set(["timeout_seconds", "query_timeout_seconds"]);

function readStoredProjectId(): number {
  try {
    const raw = window.localStorage.getItem(PROJECT_STORAGE_KEY);
    const parsed = raw ? Number.parseInt(raw, 10) : NaN;
    return Number.isInteger(parsed) && parsed > 0 ? parsed : DEFAULT_PROJECT_ID;
  } catch {
    return DEFAULT_PROJECT_ID;
  }
}

function humanize(value: string): string {
  return value.replaceAll("_", " ");
}

type FormState = {
  name: string;
  connectorType: ConnectorType;
  settings: Record<string, string>;
  credentials: Record<string, string>;
  enabled: boolean;
};

function emptyForm(typeInfo: ConnectorTypeInfo | undefined): FormState {
  const settings: Record<string, string> = {};
  const credentials: Record<string, string> = {};
  for (const field of typeInfo?.setting_fields ?? []) {
    settings[field] = field === "verify_tls" ? "true" : "";
  }
  for (const field of typeInfo?.secret_fields ?? []) {
    credentials[field] = "";
  }
  return {
    name: "",
    connectorType: typeInfo?.connector_type ?? "prometheus",
    settings,
    credentials,
    enabled: true,
  };
}

function formFromConnector(
  connector: ConfiguredConnector,
  typeInfo: ConnectorTypeInfo | undefined,
): FormState {
  const base = emptyForm(typeInfo);
  for (const [key, value] of Object.entries(connector.settings)) {
    base.settings[key] = value == null ? "" : String(value);
  }
  return {
    name: connector.name,
    connectorType: connector.connector_type,
    settings: base.settings,
    credentials: base.credentials,
    enabled: connector.enabled,
  };
}

function parseSettings(
  raw: Record<string, string>,
  fields: string[],
): Record<string, unknown> {
  const settings: Record<string, unknown> = {};
  for (const field of fields) {
    const value = raw[field]?.trim() ?? "";
    if (value === "") {
      continue;
    }
    if (BOOLEAN_FIELDS.has(field)) {
      settings[field] = value === "true";
    } else if (NUMBER_FIELDS.has(field)) {
      settings[field] = Number(value);
    } else {
      settings[field] = value;
    }
  }
  return settings;
}

export function ConnectorsPage() {
  const [projectId, setProjectId] = useState(readStoredProjectId);
  const [projectDraft, setProjectDraft] = useState(String(projectId));
  const [editing, setEditing] = useState<ConfiguredConnector | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [testMessage, setTestMessage] = useState<string | null>(null);

  const types = useAsync((signal) => listConnectorTypes(signal), []);
  const connectors = useAsync(
    (signal) => listConnectors(projectId, signal),
    [projectId],
    { keepPreviousData: true },
  );

  const typeMap = useMemo(() => {
    const map = new Map<ConnectorType, ConnectorTypeInfo>();
    if (types.status === "success") {
      for (const item of types.data.items) {
        map.set(item.connector_type, item);
      }
    }
    return map;
  }, [types]);

  const [form, setForm] = useState<FormState>(() => emptyForm(undefined));

  useEffect(() => {
    setProjectDraft(String(projectId));
    try {
      window.localStorage.setItem(PROJECT_STORAGE_KEY, String(projectId));
    } catch {
      // ignore storage failures
    }
  }, [projectId]);

  useEffect(() => {
    if (!showForm && !editing && types.status === "success") {
      setForm(emptyForm(types.data.items[0]));
    }
  }, [types, showForm, editing]);

  function openCreate() {
    const typeInfo = types.status === "success" ? types.data.items[0] : undefined;
    setEditing(null);
    setForm(emptyForm(typeInfo));
    setFormError(null);
    setShowForm(true);
  }

  function openEdit(connector: ConfiguredConnector) {
    setEditing(connector);
    setForm(formFromConnector(connector, typeMap.get(connector.connector_type)));
    setFormError(null);
    setShowForm(true);
  }

  function onTypeChange(nextType: ConnectorType) {
    const typeInfo = typeMap.get(nextType);
    setForm((current) => ({
      ...emptyForm(typeInfo),
      name: current.name,
      enabled: current.enabled,
      connectorType: nextType,
    }));
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    const typeInfo = typeMap.get(form.connectorType);
    if (!typeInfo) {
      setFormError("Select a connector type.");
      return;
    }
    if (!form.name.trim()) {
      setFormError("Name is required.");
      return;
    }

    const settings = parseSettings(form.settings, typeInfo.setting_fields);
    const credentials: Record<string, string> = {};
    for (const field of typeInfo.secret_fields) {
      const value = form.credentials[field]?.trim() ?? "";
      if (value) {
        credentials[field] = value;
      }
    }

    try {
      if (editing) {
        await updateConnector(editing.id, {
          name: form.name.trim(),
          settings,
          credentials: Object.keys(credentials).length > 0 ? credentials : undefined,
          enabled: form.enabled,
        });
      } else {
        await createConnector({
          projectId,
          name: form.name.trim(),
          connectorType: form.connectorType,
          settings,
          credentials,
          enabled: form.enabled,
        });
      }
      setShowForm(false);
      setEditing(null);
      connectors.reload();
    } catch (error) {
      setFormError(getErrorMessage(error, "Could not save connector"));
    }
  }

  async function runAction(
    connectorId: number,
    action: () => Promise<unknown>,
    successMessage?: string,
  ) {
    setBusyId(connectorId);
    setActionError(null);
    setTestMessage(null);
    try {
      await action();
      if (successMessage) {
        setTestMessage(successMessage);
      }
      connectors.reload();
    } catch (error) {
      setActionError(getErrorMessage(error, "Action failed"));
    } finally {
      setBusyId(null);
    }
  }

  const typeInfo = typeMap.get(form.connectorType);

  return (
    <section className="page connectors-page">
      <div className="page__intro dashboard__intro">
        <div>
          <p className="eyebrow">Connectors</p>
          <h1>Connector management</h1>
          <p className="lede">
            Configure data-source connectors for project{" "}
            <span className="mono">#{projectId}</span>. Stored credentials are
            never shown after save.
          </p>
        </div>
        <div className="button-row dashboard__actions">
          <button type="button" className="button" onClick={openCreate}>
            Add connector
          </button>
          <button
            type="button"
            className="button button--ghost"
            onClick={connectors.reload}
          >
            Refresh
          </button>
        </div>
      </div>

      <div className="panel filter-bar connectors-toolbar">
        <label className="control">
          <span>Project</span>
          <input
            className="control__input mono"
            type="number"
            min={1}
            value={projectDraft}
            onChange={(event) => setProjectDraft(event.target.value)}
            onBlur={() => {
              const parsed = Number.parseInt(projectDraft, 10);
              if (Number.isInteger(parsed) && parsed > 0) {
                setProjectId(parsed);
              } else {
                setProjectDraft(String(projectId));
              }
            }}
          />
        </label>
      </div>

      {actionError ? (
        <p className="inline-error" role="alert">
          {actionError}
        </p>
      ) : null}
      {testMessage ? (
        <p className="inline-ok" role="status">
          {testMessage}
        </p>
      ) : null}

      {showForm ? (
        <form className="panel connector-form" onSubmit={onSubmit}>
          <div className="investigation-section__title-row">
            <h2>{editing ? "Edit connector" : "New connector"}</h2>
            <button
              type="button"
              className="button button--ghost"
              onClick={() => {
                setShowForm(false);
                setEditing(null);
              }}
            >
              Cancel
            </button>
          </div>

          <div className="connector-form__grid">
            <label className="field">
              <span>Name</span>
              <input
                value={form.name}
                onChange={(event) =>
                  setForm((current) => ({ ...current, name: event.target.value }))
                }
                required
              />
            </label>

            <label className="field">
              <span>Type</span>
              <select
                value={form.connectorType}
                disabled={Boolean(editing)}
                onChange={(event) =>
                  onTypeChange(event.target.value as ConnectorType)
                }
              >
                {(types.status === "success" ? types.data.items : []).map((item) => (
                  <option key={item.connector_type} value={item.connector_type}>
                    {item.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="field field--checkbox">
              <span>Enabled</span>
              <input
                type="checkbox"
                checked={form.enabled}
                onChange={(event) =>
                  setForm((current) => ({
                    ...current,
                    enabled: event.target.checked,
                  }))
                }
              />
            </label>
          </div>

          <h3>Settings</h3>
          <div className="connector-form__grid">
            {(typeInfo?.setting_fields ?? []).map((field) => (
              <label key={field} className="field">
                <span>{humanize(field)}</span>
                {BOOLEAN_FIELDS.has(field) ? (
                  <select
                    value={form.settings[field] ?? "true"}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        settings: {
                          ...current.settings,
                          [field]: event.target.value,
                        },
                      }))
                    }
                  >
                    <option value="true">true</option>
                    <option value="false">false</option>
                  </select>
                ) : (
                  <input
                    value={form.settings[field] ?? ""}
                    onChange={(event) =>
                      setForm((current) => ({
                        ...current,
                        settings: {
                          ...current.settings,
                          [field]: event.target.value,
                        },
                      }))
                    }
                  />
                )}
              </label>
            ))}
          </div>

          <h3>Credentials</h3>
          <p className="muted connector-form__hint">
            {editing
              ? "Leave blank to keep the currently stored secret. Values are write-only."
              : "Secrets are encrypted at rest and never returned by the API."}
          </p>
          <div className="connector-form__grid">
            {(typeInfo?.secret_fields ?? []).map((field) => (
              <label key={field} className="field">
                <span>
                  {humanize(field)}
                  {editing &&
                  editing.configured_credentials.includes(field) ? (
                    <em className="configured-secret"> configured</em>
                  ) : null}
                </span>
                <input
                  type="password"
                  autoComplete="new-password"
                  placeholder={
                    editing && editing.configured_credentials.includes(field)
                      ? "••••••••"
                      : undefined
                  }
                  value={form.credentials[field] ?? ""}
                  onChange={(event) =>
                    setForm((current) => ({
                      ...current,
                      credentials: {
                        ...current.credentials,
                        [field]: event.target.value,
                      },
                    }))
                  }
                />
              </label>
            ))}
          </div>

          {formError ? (
            <p className="form-error" role="alert">
              {formError}
            </p>
          ) : null}

          <div className="button-row">
            <button type="submit" className="button">
              {editing ? "Save changes" : "Create connector"}
            </button>
          </div>
        </form>
      ) : null}

      <section className="panel panel--flush">
        {connectors.status === "loading" && !connectors.data ? (
          <div className="panel__body">
            <LoadingState label="Loading connectors…" />
          </div>
        ) : null}
        {connectors.status === "error" && !connectors.data ? (
          <div className="panel__body">
            <ErrorState
              title="Could not load connectors"
              message={connectors.error}
              onRetry={connectors.reload}
            />
          </div>
        ) : null}
        {connectors.data ? (
          connectors.data.items.length === 0 ? (
            <div className="panel__body empty-state">
              <h2>No connectors yet</h2>
              <p>Add a Prometheus, GitHub, database, or search connector.</p>
              <button type="button" className="button" onClick={openCreate}>
                Add connector
              </button>
            </div>
          ) : (
            <ul className="connector-list">
              {connectors.data.items.map((connector) => (
                <li key={connector.id} className="connector-row">
                  <div className="connector-row__main">
                    <div className="connector-row__title">
                      <strong>{connector.name}</strong>
                      <span className="signal-kind">
                        {typeMap.get(connector.connector_type)?.label ??
                          humanize(connector.connector_type)}
                      </span>
                      <span
                        className={`status-pill ${
                          connector.enabled
                            ? "status-pill--on"
                            : "status-pill--off"
                        }`}
                      >
                        {connector.enabled ? "Enabled" : "Disabled"}
                      </span>
                    </div>
                    <div className="connector-row__meta">
                      <span>
                        Credentials:{" "}
                        {connector.configured_credentials.length > 0
                          ? connector.configured_credentials
                              .map(humanize)
                              .join(", ")
                          : "none"}
                      </span>
                      {connector.last_tested_at ? (
                        <span
                          title={formatDateTime(connector.last_tested_at)}
                        >
                          Last test{" "}
                          {connector.last_test_success ? "passed" : "failed"}{" "}
                          {formatRelativeTime(connector.last_tested_at)}
                          {connector.last_test_detail
                            ? ` — ${connector.last_test_detail}`
                            : ""}
                        </span>
                      ) : (
                        <span>Not tested yet</span>
                      )}
                    </div>
                  </div>
                  <div className="connector-row__actions">
                    <button
                      type="button"
                      className="button button--ghost"
                      disabled={busyId === connector.id}
                      onClick={() => openEdit(connector)}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="button button--ghost"
                      disabled={busyId === connector.id}
                      onClick={() =>
                        runAction(
                          connector.id,
                          () =>
                            connector.enabled
                              ? disableConnector(connector.id)
                              : enableConnector(connector.id),
                        )
                      }
                    >
                      {connector.enabled ? "Disable" : "Enable"}
                    </button>
                    <button
                      type="button"
                      className="button button--ghost"
                      disabled={busyId === connector.id}
                      onClick={() =>
                        runAction(connector.id, async () => {
                          const result = await testConnector(connector.id);
                          setTestMessage(
                            result.success
                              ? `${connector.name}: connection ok — ${result.detail}`
                              : `${connector.name}: connection failed — ${result.detail}`,
                          );
                        })
                      }
                    >
                      Test
                    </button>
                    <button
                      type="button"
                      className="button button--ghost"
                      disabled={busyId === connector.id}
                      onClick={() => {
                        if (
                          window.confirm(
                            `Delete connector “${connector.name}”? This cannot be undone.`,
                          )
                        ) {
                          void runAction(connector.id, () =>
                            deleteConnector(connector.id),
                          );
                        }
                      }}
                    >
                      Delete
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )
        ) : null}
      </section>
    </section>
  );
}
