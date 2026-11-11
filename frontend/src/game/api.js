// REST + Socket.IO connection to the Island Economy backend.
import { io } from "socket.io-client";

export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
const SOCKET_URL = process.env.REACT_APP_BACKEND_SOCKET_URL || BACKEND_URL;

const tokenKey = (code) => `island_token_${code}`;

export function storedToken(sessionCode) {
  try {
    return sessionStorage.getItem(tokenKey(sessionCode));
  } catch {
    return null;
  }
}

function storeToken(sessionCode, token) {
  try {
    sessionStorage.setItem(tokenKey(sessionCode), token);
  } catch {
    /* private mode: the token then only lives for this page load */
  }
}

export function forgetToken(sessionCode) {
  try {
    sessionStorage.removeItem(tokenKey(sessionCode));
  } catch {
    /* ignore */
  }
}

// Join a session. Returns {participant_id, token, session_code, status}.
// Concurrent calls for the same session share one request (React StrictMode runs effects twice in dev).
const inflight = new Map();
export function joinSession(args) {
  const key = args.sessionCode;
  if (!inflight.has(key)) {
    inflight.set(key, doJoin(args).finally(() => inflight.delete(key)));
  }
  return inflight.get(key);
}

async function doJoin({ sessionCode, prolificPid, studyId, prolificSessionId }) {
  const res = await fetch(`${BACKEND_URL}/api/join`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_code: sessionCode,
      prolific_pid: prolificPid || null,
      study_id: studyId || null,
      prolific_session_id: prolificSessionId || null,
    }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Could not join (HTTP ${res.status})`);
  }
  const data = await res.json();
  storeToken(data.session_code, data.token);
  return data;
}

export function connectGameSocket(token) {
  return io(SOCKET_URL, {
    path: "/ws",
    transports: ["websocket"],
    auth: { token },
    reconnection: true,
    reconnectionDelay: 500,
    reconnectionDelayMax: 3000,
  });
}

// Public game parameters for the instructions (never includes the number of rounds).
export async function fetchRules() {
  const res = await fetch(`${BACKEND_URL}/api/rules`);
  if (!res.ok) throw new Error(`Could not load the instructions (HTTP ${res.status})`);
  return res.json();
}
