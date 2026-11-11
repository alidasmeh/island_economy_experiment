// React hook: one authenticated socket per participant, latest server snapshot, and actions.
import { useCallback, useEffect, useRef, useState } from "react";
import { connectGameSocket } from "./api";

export function useGame(token) {
  const socketRef = useRef(null);
  const [snapshot, setSnapshot] = useState(null);
  const [connection, setConnection] = useState("connecting"); // connecting | connected | reconnecting | refused
  const [clockOffset, setClockOffset] = useState(0); // server time - local time (ms)

  useEffect(() => {
    if (!token) return undefined;
    const socket = connectGameSocket(token);
    socketRef.current = socket;
    socket.on("connect", () => setConnection("connected"));
    socket.on("disconnect", () => setConnection("reconnecting"));
    socket.on("connect_error", (err) => {
      // The server refuses unknown tokens; anything else is a network problem worth retrying.
      if (err && /token/i.test(err.message || "")) setConnection("refused");
      else setConnection("reconnecting");
    });
    socket.on("state", (s) => {
      if (s && s.server_now_ms) setClockOffset(s.server_now_ms - Date.now());
      setSnapshot(s);
    });
    return () => {
      socket.removeAllListeners();
      socket.disconnect();
      socketRef.current = null;
    };
  }, [token]);

  // Emit with acknowledgement; resolves to {ok, error?}.
  const call = useCallback(
    (event, data) =>
      new Promise((resolve) => {
        const socket = socketRef.current;
        if (!socket || !socket.connected) {
          resolve({ ok: false, error: "Not connected. Trying to reconnect…" });
          return;
        }
        socket.timeout(8000).emit(event, data || {}, (err, ack) => {
          if (err) resolve({ ok: false, error: "The server did not respond. Please try again." });
          else resolve(ack || { ok: false, error: "No response" });
        });
      }),
    []
  );

  return { snapshot, connection, clockOffset, call };
}

// Seconds left until a server deadline, ticking every 250 ms.
export function useCountdown(deadlineMs, clockOffset) {
  const compute = useCallback(
    () => (deadlineMs ? Math.max(0, Math.ceil((deadlineMs - (Date.now() + clockOffset)) / 1000)) : 0),
    [deadlineMs, clockOffset]
  );
  const [left, setLeft] = useState(compute);
  useEffect(() => {
    setLeft(compute());
    const id = setInterval(() => setLeft(compute()), 250);
    return () => clearInterval(id);
  }, [compute]);
  return left;
}
