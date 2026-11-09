const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
const TOKEN_KEY = "msp_token";
const ORG_KEY = "msp_org";

let token = localStorage.getItem(TOKEN_KEY) || "";
let organizationId = localStorage.getItem(ORG_KEY) || "";

export function getToken() {
  return token;
}

export function setToken(value) {
  token = value || "";
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

export function setOrganization(value) {
  organizationId = value || "";
  if (organizationId) {
    localStorage.setItem(ORG_KEY, organizationId);
  } else {
    localStorage.removeItem(ORG_KEY);
  }
}

function errorMessage(data, status) {
  if (!data) {
    return `Request failed (${status})`;
  }
  if (typeof data === "string") {
    return data;
  }
  if (data.detail) {
    return data.detail;
  }
  return Object.entries(data)
    .map(([key, value]) => {
      const text = Array.isArray(value) ? value.join(", ") : String(value);
      return `${key}: ${text}`;
    })
    .join("\n");
}

async function request(path, options = {}) {
  const headers = {
    ...(options.body ? { "Content-Type": "application/json" } : {}),
    ...(options.headers || {}),
  };

  if (token) {
    headers.Authorization = `Token ${token}`;
  }
  if (organizationId) {
    headers["X-Organization-ID"] = organizationId;
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers,
  });
  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!response.ok) {
    throw new Error(errorMessage(data, response.status));
  }

  return data;
}

export async function login(username, password) {
  const response = await fetch(`${API_URL}/api-token-auth/`, {
    method: "POST",
    headers: {
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: new URLSearchParams({ username, password }),
  });
  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!response.ok) {
    throw new Error(errorMessage(data, response.status));
  }

  setToken(data.token);
  return data;
}

export const api = {
  me: () => request("/api/me/"),
  organizations: () => request("/api/organizations/"),
  incidents: () =>
    request("/api/incidents/?ordering=-started_at"),
  incident: (id) => request(`/api/incidents/${id}/`),
  events: (id) => request(`/api/incidents/${id}/events/`),
  transition: (id, status) =>
    request(`/api/incidents/${id}/transition/`, {
      method: "POST",
      body: JSON.stringify({ status }),
    }),
  investigate: (id, evidence) =>
    request(`/api/incidents/${id}/investigate/`, {
      method: "POST",
      body: JSON.stringify({ evidence }),
    }),
  remediationActions: () => request("/api/remediation-actions/"),
  propose: (payload) =>
    request("/api/remediation-actions/", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
  approve: (id) =>
    request(`/api/remediation-actions/${id}/approve/`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  reject: (id, reason) =>
    request(`/api/remediation-actions/${id}/reject/`, {
      method: "POST",
      body: JSON.stringify({ reason }),
    }),
  execute: (id) =>
    request(`/api/remediation-actions/${id}/execute/`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  rollback: (id) =>
    request(`/api/remediation-actions/${id}/rollback/`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  ingestAlert: (payload) =>
    request("/api/alerts/", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
};
