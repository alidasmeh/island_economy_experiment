// Calls to the game server's researcher (admin) API.
// The login is kept for this browser tab only (sessionStorage) and sent as HTTP Basic auth.

export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
export const PARTICIPANT_URL = process.env.REACT_APP_PARTICIPANT_URL || "http://localhost:3000";

const AUTH_KEY = "island_admin_auth";
const USER_KEY = "island_admin_user";

export function storedLogin() {
  try {
    const auth = sessionStorage.getItem(AUTH_KEY);
    return auth ? { auth, username: sessionStorage.getItem(USER_KEY) || "" } : null;
  } catch {
    return null;
  }
}

export function forgetLogin() {
  try {
    sessionStorage.removeItem(AUTH_KEY);
    sessionStorage.removeItem(USER_KEY);
  } catch {
    /* ignore */
  }
}

export class UnauthorizedError extends Error {}

async function request(path, { auth, method = "GET", body } = {}) {
  const headers = { Authorization: `Basic ${auth || storedLogin()?.auth || ""}` };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch(`${BACKEND_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new Error(`Cannot reach the game server at ${BACKEND_URL}. Is it running?`);
  }
  if (res.status === 401) throw new UnauthorizedError("Wrong username or password.");
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = typeof data.detail === "string" ? data.detail : "Request failed";
    throw new Error(detail);
  }
  return data;
}

// Checks the credentials against the admin API and keeps them for this tab.
export async function login(username, password) {
  const auth = btoa(unescape(encodeURIComponent(`${username}:${password}`)));
  await request("/api/admin/sessions", { auth });
  sessionStorage.setItem(AUTH_KEY, auth);
  sessionStorage.setItem(USER_KEY, username);
  return { auth, username };
}

export const listSessions = () => request("/api/admin/sessions");
export const getSession = (code) => request(`/api/admin/sessions/${encodeURIComponent(code)}`);
export const createSession = (body) => request("/api/admin/sessions", { method: "POST", body });

export const getRules = () => request("/api/rules");

export const participantLink = (code) => `${PARTICIPANT_URL}/play?session=${code}`;
export const prolificLink = (code) =>
  `${participantLink(code)}&PROLIFIC_PID={{%PROLIFIC_PID%}}&STUDY_ID={{%STUDY_ID%}}&SESSION_ID={{%SESSION_ID%}}`;
