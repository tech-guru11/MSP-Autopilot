import { useCallback, useEffect, useState } from "react";
import {
  api,
  getToken,
  login,
  setOrganization,
  setToken,
} from "./api";

const STATUSES = [
  "new",
  "triaging",
  "investigating",
  "awaiting_approval",
  "remediating",
  "verifying",
  "resolved",
  "escalated",
  "closed",
];

const NEXT_STATUSES = {
  new: ["triaging", "escalated"],
  triaging: ["investigating", "escalated"],
  investigating: ["awaiting_approval", "verifying", "escalated"],
  awaiting_approval: ["remediating", "investigating", "escalated"],
  remediating: ["verifying", "investigating", "escalated"],
  verifying: ["resolved", "investigating", "escalated"],
  resolved: ["closed"],
  escalated: ["triaging", "investigating", "closed"],
  closed: [],
};

const ACTION_TYPES = [
  "inspect_connection_pool",
  "clear_cache",
  "restart_service",
  "scale_out",
  "rollback_deployment",
  "failover_database",
  "delete_database",
  "change_iam_policy",
];

const DEMO_EVIDENCE = {
  observations: {
    http_status: 500,
    db_connection_usage: 96,
    cpu_usage: 88,
    recent_deployment: true,
    log_errors: [
      "FATAL: remaining connection slots are reserved",
      "Timeout acquiring database connection",
    ],
    service_unavailable: false,
    dns_failure: false,
  },
};

function formatDate(value) {
  return value ? new Date(value).toLocaleString() : "-";
}

function roleFor(user, organizationId) {
  const membership = (user?.memberships || []).find(
    (item) => item.organization === organizationId,
  );
  return membership?.role || "";
}

function Login({ onLogin }) {
  const [username, setUsername] = useState("engineer");
  const [password, setPassword] = useState("demo-password");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await onLogin(username, password);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login">
      <form className="card login-card" onSubmit={submit}>
        <h1>MSP Autopilot</h1>
        <p className="muted">Sign in with a demo or organization account.</p>
        <label>
          Username
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete="current-password"
          />
        </label>
        {error ? <p className="error">{error}</p> : null}
        <button type="submit" disabled={busy}>
          {busy ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </main>
  );
}

function InvestigationCard({ investigation }) {
  const result = investigation.result || {};
  const hypotheses = result.hypotheses || [];
  const evidence = result.evidence || [];
  const recommendation = result.recommendation || {};

  return (
    <article className="investigation">
      <div className="row spread">
        <strong>Investigation</strong>
        <span className="badge">{investigation.severity_assessment}</span>
      </div>
      <p>{investigation.summary}</p>
      <h4>Hypotheses</h4>
      <ul>
        {hypotheses.map((item) => (
          <li key={item.title}>
            <strong>{item.title}</strong> ({item.confidence}) -{" "}
            {item.explanation}
          </li>
        ))}
      </ul>
      <h4>Evidence</h4>
      <ul>
        {evidence.map((item) => (
          <li key={`${item.source}-${item.observation}`}>
            <strong>{item.source}</strong>: {item.observation}
          </li>
        ))}
      </ul>
      {recommendation.action ? (
        <p className="recommendation">
          <strong>Recommended:</strong> {recommendation.action} (
          {recommendation.risk} risk)
        </p>
      ) : null}
    </article>
  );
}

function IncidentDetail({ incident, role, onRefresh, onError }) {
  const [events, setEvents] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [nextStatus, setNextStatus] = useState("");
  const [actionType, setActionType] = useState("restart_service");
  const [parameters, setParameters] = useState(
    '{"service_name": "university-website"}',
  );

  const loadEvents = useCallback(async () => {
    try {
      const data = await api.events(incident.id);
      setEvents(data.results || data);
    } catch (err) {
      setError(err.message);
    }
  }, [incident.id]);

  useEffect(() => {
    setNextStatus(NEXT_STATUSES[incident.status]?.[0] || "");
    loadEvents();
  }, [incident.status, loadEvents]);

  async function run(task) {
    setBusy(true);
    setError("");
    try {
      await task();
      await onRefresh();
      await loadEvents();
    } catch (err) {
      setError(err.message);
      onError(err.message);
    } finally {
      setBusy(false);
    }
  }

  async function investigate() {
    if (incident.status === "new") {
      await api.transition(incident.id, "triaging");
    }
    if (
      incident.status === "new" ||
      incident.status === "triaging"
    ) {
      await api.transition(incident.id, "investigating");
    }
    await api.investigate(incident.id, DEMO_EVIDENCE);
  }

  function propose() {
    let parsed;
    try {
      parsed = JSON.parse(parameters);
    } catch {
      setError("Parameters must be valid JSON.");
      return;
    }

    run(() =>
      api.propose({
        incident: incident.id,
        action_type: actionType,
        parameters: parsed,
      }),
    );
  }

  function reject(actionId) {
    const reason = window.prompt("Rejection reason", "Not appropriate");
    if (reason === null) {
      return;
    }
    run(() => api.reject(actionId, reason));
  }

  const canApprove = role === "admin";
  const canAct = role === "admin" || role === "engineer";
  const investigations = incident.investigations || [];
  const actions = incident.remediation_actions || [];

  return (
    <section className="detail">
      <div className="row spread">
        <div>
          <h2>{incident.title}</h2>
          <p className="muted">
            {incident.customer_name} · {incident.asset_name || "No asset"}
          </p>
        </div>
        <div className="row">
          <span className={`badge severity-${incident.severity}`}>
            {incident.severity}
          </span>
          <span className="badge">{incident.status}</span>
        </div>
      </div>

      <p>{incident.description || "No description."}</p>

      {error ? <p className="error">{error}</p> : null}

      <div className="actions">
        <label>
          Transition to
          <select
            value={nextStatus}
            onChange={(event) => setNextStatus(event.target.value)}
          >
            {(NEXT_STATUSES[incident.status] || []).map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>
        </label>
        <button
          disabled={busy || !nextStatus}
          onClick={() => run(() => api.transition(incident.id, nextStatus))}
        >
          Apply transition
        </button>
        <button
          disabled={busy || !["new", "triaging", "investigating"].includes(incident.status)}
          onClick={() => run(investigate)}
        >
          Investigate
        </button>
      </div>

      <h3>Investigations</h3>
      {investigations.length === 0 ? (
        <p className="muted">No investigations yet.</p>
      ) : (
        investigations.map((item) => (
          <InvestigationCard key={item.id} investigation={item} />
        ))
      )}

      <h3>Remediation</h3>
      {canAct ? (
        <div className="proposal">
          <label>
            Action
            <select
              value={actionType}
              onChange={(event) => setActionType(event.target.value)}
            >
              {ACTION_TYPES.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label>
            Parameters (JSON)
            <textarea
              rows="3"
              value={parameters}
              onChange={(event) => setParameters(event.target.value)}
            />
          </label>
          <button disabled={busy} onClick={propose}>
            Propose action
          </button>
        </div>
      ) : (
        <p className="muted">Viewers cannot propose remediation.</p>
      )}

      {actions.length === 0 ? (
        <p className="muted">No remediation actions yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Action</th>
              <th>Risk</th>
              <th>Status</th>
              <th>Controls</th>
            </tr>
          </thead>
          <tbody>
            {actions.map((action) => (
              <tr key={action.id}>
                <td>{action.action_type}</td>
                <td>{action.risk}</td>
                <td>{action.status}</td>
                <td className="row">
                  {canApprove &&
                  action.status === "pending_approval" ? (
                    <>
                      <button
                        disabled={busy}
                        onClick={() =>
                          run(() => api.approve(action.id))
                        }
                      >
                        Approve
                      </button>
                      <button
                        className="secondary"
                        disabled={busy}
                        onClick={() => reject(action.id)}
                      >
                        Reject
                      </button>
                    </>
                  ) : null}
                  {canAct && action.status === "approved" ? (
                    <button
                      disabled={busy}
                      onClick={() =>
                        run(() => api.execute(action.id))
                      }
                    >
                      Execute
                    </button>
                  ) : null}
                  {canAct && action.status === "succeeded" ? (
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() =>
                        run(() => api.rollback(action.id))
                      }
                    >
                      Rollback
                    </button>
                  ) : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3>Timeline</h3>
      <ol className="timeline">
        {events.map((event) => (
          <li key={event.id}>
            <span className="muted">{formatDate(event.created_at)}</span>{" "}
            <strong>{event.event_type}</strong> {event.description}
          </li>
        ))}
      </ol>
    </section>
  );
}

export default function App() {
  const [tokenState, setTokenState] = useState(getToken());
  const [user, setUser] = useState(null);
  const [organizations, setOrganizations] = useState([]);
  const [organizationId, setOrganizationId] = useState("");
  const [incidents, setIncidents] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [incident, setIncident] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const loadIncidents = useCallback(async () => {
    setBusy(true);
    setError("");
    try {
      const data = await api.incidents();
      setIncidents(data.results || data);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }, []);

  const openIncident = useCallback(async (id) => {
    setSelectedId(id);
    setBusy(true);
    setError("");
    try {
      const data = await api.incident(id);
      setIncident(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }, []);

  const refreshIncident = useCallback(async () => {
    if (!selectedId) {
      return;
    }
    const data = await api.incident(selectedId);
    setIncident(data);
  }, [selectedId]);

  useEffect(() => {
    if (!tokenState) {
      return;
    }

    let active = true;

    async function bootstrap() {
      setBusy(true);
      setError("");
      try {
        const me = await api.me();
        if (!active) {
          return;
        }
        setUser(me);
        const data = await api.organizations();
        if (!active) {
          return;
        }
        const results = data.results || data;
        setOrganizations(results);
        const stored = localStorage.getItem("msp_org");
        const selected =
          results.find((item) => item.id === stored) || results[0];
        if (selected) {
          setOrganization(selected.id);
          setOrganizationId(selected.id);
          await loadIncidents();
        }
      } catch (err) {
        if (active) {
          setError(err.message);
        }
      } finally {
        if (active) {
          setBusy(false);
        }
      }
    }

    bootstrap();

    return () => {
      active = false;
    };
  }, [tokenState, loadIncidents]);

  async function handleLogin(username, password) {
    const data = await login(username, password);
    setTokenState(data.token);
  }

  async function chooseOrganization(id) {
    setOrganization(id);
    setOrganizationId(id);
    setSelectedId("");
    setIncident(null);
    await loadIncidents();
  }

  function logout() {
    setToken("");
    setOrganization("");
    setTokenState("");
    setUser(null);
    setOrganizations([]);
    setOrganizationId("");
    setIncidents([]);
    setIncident(null);
  }

  if (!tokenState) {
    return <Login onLogin={handleLogin} />;
  }

  const role = roleFor(user, organizationId);

  return (
    <div className="app">
      <header>
        <div>
          <h1>MSP Autopilot</h1>
          <p className="muted">
            {user?.username || "Loading"} · role: {role || "none"}
          </p>
        </div>
        <div className="row">
          <select
            value={organizationId}
            onChange={(event) => chooseOrganization(event.target.value)}
          >
            {organizations.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
          <button className="secondary" onClick={logout}>
            Sign out
          </button>
        </div>
      </header>

      {error ? <p className="error banner">{error}</p> : null}

      <main className="layout">
        <aside className="card list">
          <div className="row spread">
            <h2>Incidents</h2>
            <button
              className="secondary"
              disabled={busy}
              onClick={loadIncidents}
            >
              Refresh
            </button>
          </div>
          {incidents.length === 0 ? (
            <p className="muted">No incidents in this organization.</p>
          ) : (
            <ul>
              {incidents.map((item) => (
                <li key={item.id}>
                  <button
                    className={
                      item.id === selectedId
                        ? "incident selected"
                        : "incident"
                    }
                    onClick={() => openIncident(item.id)}
                  >
                    <span className={`badge severity-${item.severity}`}>
                      {item.severity}
                    </span>
                    <span>
                      <strong>{item.title}</strong>
                      <small>
                        {item.customer_name} · {item.status}
                      </small>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <section className="card">
          {incident ? (
            <IncidentDetail
              key={incident.id}
              incident={incident}
              role={role}
              onRefresh={refreshIncident}
              onError={setError}
            />
          ) : (
            <p className="muted">
              Select an incident to view diagnostics and remediation.
            </p>
          )}
        </section>
      </main>
    </div>
  );
}
