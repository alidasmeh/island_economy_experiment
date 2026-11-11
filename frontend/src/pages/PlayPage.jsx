// Entry point for participants: /play?session=CODE&PROLIFIC_PID=...&STUDY_ID=...&SESSION_ID=...
import React, { useEffect, useMemo, useState } from "react";
import { Alert, Box, CircularProgress, Container, Typography } from "@mui/material";
import { fetchRules, forgetToken, joinSession, storedToken } from "../game/api";
import Instructions from "../game/components/Instructions";
import { useGame } from "../game/useGame";
import { GameHeader, PolicyBanner, SharedState } from "../game/components/StatusBar";
import DecisionPanel from "../game/components/DecisionPanel";
import {
  CommunicationPanel,
  EventPanel,
  FinalPanel,
  ResultsPanel,
  WaitingRoom,
} from "../game/components/PhasePanels";

function useQuery() {
  return useMemo(() => new URLSearchParams(window.location.search), []);
}

export default function PlayPage() {
  const q = useQuery();
  const sessionCode = (q.get("session") || "").trim().toUpperCase();
  const [token, setToken] = useState(() => (sessionCode ? storedToken(sessionCode) : null));
  const [joinError, setJoinError] = useState("");

  useEffect(() => {
    if (!sessionCode || token) return;
    joinSession({
      sessionCode,
      prolificPid: q.get("PROLIFIC_PID"),
      studyId: q.get("STUDY_ID"),
      prolificSessionId: q.get("SESSION_ID"),
    })
      .then((d) => setToken(d.token))
      .catch((e) => setJoinError(e.message));
  }, [sessionCode, token, q]);

  const { snapshot, connection, clockOffset, call } = useGame(token);
  const [enterError, setEnterError] = useState("");

  // A stale token (e.g. the same Prolific ID joined from another tab) -> join again.
  useEffect(() => {
    if (connection === "refused" && sessionCode) {
      forgetToken(sessionCode);
      setToken(null);
    }
  }, [connection, sessionCode]);

  // Instructions first (once per session in this tab), then the waiting room.
  // Consent and the comprehension quiz are added before this in Milestone 7.
  const doneKey = `island_instructions_done_${sessionCode}`;
  const [instructionsDone, setInstructionsDone] = useState(() => {
    try {
      return sessionStorage.getItem(doneKey) === "1";
    } catch {
      return false;
    }
  });
  const [rules, setRules] = useState(null);
  const [rulesError, setRulesError] = useState("");
  const shownAt = useMemo(() => Date.now(), []);
  const inLobby = snapshot && snapshot.view === "lobby";

  useEffect(() => {
    if (inLobby && !instructionsDone && !rules) fetchRules().then(setRules).catch((e) => setRulesError(e.message));
  }, [inLobby, instructionsDone, rules]);

  useEffect(() => {
    if (inLobby && instructionsDone) {
      call("enter_waiting_room", { instructions_seconds: Math.round((Date.now() - shownAt) / 1000) }).then((ack) => {
        if (!ack.ok) setEnterError(ack.error || "Could not enter the waiting room");
      });
    }
  }, [inLobby, instructionsDone, call, shownAt]);

  const finishInstructions = () => {
    try {
      sessionStorage.setItem(doneKey, "1");
    } catch {
      /* ignore */
    }
    setInstructionsDone(true);
  };

  let body;
  if (!sessionCode) {
    body = <Alert severity="error">This link is missing the session code.</Alert>;
  } else if (joinError) {
    body = <Alert severity="error">{joinError}</Alert>;
  } else if (enterError) {
    body = <Alert severity="info">{enterError}. Thank you for your interest.</Alert>;
  } else if (!snapshot) {
    body = (
      <Box textAlign="center" sx={{ mt: 6 }}>
        <CircularProgress />
        <Typography sx={{ mt: 2 }}>Connecting…</Typography>
      </Box>
    );
  } else if (inLobby && !instructionsDone) {
    body = rulesError ? (
      <Alert severity="error">{rulesError}</Alert>
    ) : rules ? (
      <Instructions rules={rules} condition="none" onDone={finishInstructions} />
    ) : (
      <CircularProgress sx={{ mt: 4 }} />
    );
  } else if (snapshot.view === "waiting" || snapshot.view === "lobby") {
    body = <WaitingRoom snap={snapshot.view === "waiting" ? snapshot : { n_waiting: 1, n_needed: "?" }} />;
  } else if (snapshot.view === "unavailable") {
    body = (
      <Alert severity="warning">
        Your game is no longer available because of a technical problem. Please contact the researchers via
        Prolific.
      </Alert>
    );
  } else {
    body = <GameScreen snap={snapshot} call={call} clockOffset={clockOffset} />;
  }

  return (
    <Container maxWidth="sm" sx={{ py: 2, px: 2 }}>
      {connection === "reconnecting" && snapshot && (
        <Alert severity="warning" sx={{ mb: 1.5 }}>
          Connection lost — reconnecting…
        </Alert>
      )}
      {body}
    </Container>
  );
}

function GameScreen({ snap, call, clockOffset }) {
  if (snap.status === "aborted") {
    return <Alert severity="error">The game stopped because of a technical problem. Please contact the researchers.</Alert>;
  }
  const key = `${snap.phase}-${snap.round}`;
  let panel = null;
  if (snap.phase === "finished") panel = <FinalPanel snap={snap} />;
  else if (snap.phase === "event") panel = <EventPanel key={key} snap={snap} call={call} />;
  else if (snap.phase === "communication") panel = <CommunicationPanel key={key} snap={snap} call={call} />;
  else if (snap.phase === "decision") panel = <DecisionPanel key={key} snap={snap} call={call} />;
  else if (snap.phase === "resolution") panel = <ResultsPanel key={key} snap={snap} call={call} />;
  else panel = <Typography>Starting…</Typography>;
  return (
    <>
      <GameHeader snap={snap} clockOffset={clockOffset} />
      {snap.phase !== "finished" && <SharedState snap={snap} />}
      {snap.phase !== "finished" && <PolicyBanner snap={snap} />}
      {panel}
    </>
  );
}
