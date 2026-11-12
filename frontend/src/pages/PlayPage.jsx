// Entry point for participants: /play?session=CODE&PROLIFIC_PID=...&STUDY_ID=...&SESSION_ID=...
import React, { useEffect, useMemo, useState } from "react";
import { Alert, Box, Button, CircularProgress, Container, Typography } from "@mui/material";
import { fetchRules, forgetToken, joinSession, storedToken } from "../game/api";
import Instructions from "../game/components/Instructions";
import { useGame } from "../game/useGame";
import { GameHeader, PolicyBanner, SharedState } from "../game/components/StatusBar";
import DecisionPanel from "../game/components/DecisionPanel";
import CoordinatorScreen from "../game/components/CoordinatorScreen";
import {
  CommunicationPanel,
  EventPanel,
  FinalPanel,
  PolicyWaitPanel,
  ResultsPanel,
  WaitingRoom,
} from "../game/components/PhasePanels";
import {
  Consent,
  ExitPage,
  PracticeBanner,
  PracticeDone,
  PracticeIntro,
  Questionnaire,
  Quiz,
} from "../game/components/Onboarding";

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

  // A stale token (e.g. the same Prolific ID joined from another tab) -> join again.
  useEffect(() => {
    if (connection === "refused" && sessionCode) {
      forgetToken(sessionCode);
      setToken(null);
    }
  }, [connection, sessionCode]);

  // The server decides the step (consent -> instructions + quiz -> practice -> waiting room -> game ->
  // questionnaire -> payment). Only "instructions read" is kept in this tab, so a reload skips re-reading.
  const doneKey = `island_instructions_done_${sessionCode}`;
  const [instructionsDone, setInstructionsDone] = useState(() => {
    try {
      return sessionStorage.getItem(doneKey) === "1";
    } catch {
      return false;
    }
  });
  const markInstructions = (done) => {
    try {
      if (done) sessionStorage.setItem(doneKey, "1");
      else sessionStorage.removeItem(doneKey);
    } catch {
      /* ignore */
    }
    setInstructionsDone(done);
    window.scrollTo(0, 0);
  };
  const [rules, setRules] = useState(null);
  const [rulesError, setRulesError] = useState("");
  const shownAt = useMemo(() => Date.now(), []);
  const step = snapshot && snapshot.view === "lobby" ? snapshot.step : null;
  const [enterError, setEnterError] = useState("");

  useEffect(() => {
    if (step && !rules) fetchRules().then(setRules).catch((e) => setRulesError(e.message));
  }, [step, rules]);

  useEffect(() => {
    if (step === "ready") {
      call("enter_waiting_room", { instructions_seconds: Math.round((Date.now() - shownAt) / 1000) }).then((ack) => {
        if (!ack.ok) setEnterError(ack.error || "Could not enter the waiting room");
      });
    }
  }, [step, call, shownAt]);

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
  } else if (step) {
    if (rulesError) body = <Alert severity="error">{rulesError}</Alert>;
    else if (!rules) body = <CircularProgress sx={{ mt: 4 }} />;
    else if (step === "consent") body = <Consent rules={rules} call={call} />;
    else if (step === "instructions" && !instructionsDone)
      body = (
        <Instructions
          rules={rules}
          condition={snapshot.condition || "none"}
          role={snapshot.role || "player"}
          onDone={() => markInstructions(true)}
          doneLabel="Continue to the questions"
        />
      );
    else if (step === "instructions")
      body = <Quiz quiz={snapshot.quiz} call={call} onReread={() => markInstructions(false)} />;
    else if (step === "practice") body = <PracticeIntro snap={snapshot} call={call} />;
    else body = <WaitingRoom snap={{ n_waiting: 1, n_needed: "?" }} />;
  } else if (snapshot.view === "waiting") {
    body = <WaitingRoom snap={snapshot} call={call} clockOffset={clockOffset} />;
  } else if (snapshot.view === "questionnaire") {
    body = <Questionnaire items={snapshot.items} call={call} />;
  } else if (snapshot.view === "exit") {
    body = <ExitPage snap={snapshot} />;
  } else if (snapshot.view === "full") {
    body = (
      <Alert severity="info">
        This session is already full, so there is no place for you in a group. Thank you for your interest. Please
        return the study on Prolific.
      </Alert>
    );
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

  const wide = snapshot && snapshot.view === "game" && snapshot.role === "coordinator";
  return (
    <Container maxWidth={wide ? "md" : "sm"} sx={{ py: 2, px: 2 }}>
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
  const [toQuestionnaire, setToQuestionnaire] = useState(false);
  if (snap.status === "aborted") {
    return (
      <Alert severity="error">
        The game stopped because of a technical problem. Please reload this page to see how to finish the study.
      </Alert>
    );
  }
  if (snap.phase === "finished") {
    if (snap.practice) return <PracticeDone snap={snap} call={call} />;
    if (toQuestionnaire) return <Questionnaire call={call} />;
  }
  const next = snap.phase === "finished" && (
    <Button variant="contained" fullWidth sx={{ mt: 2 }} onClick={() => setToQuestionnaire(true)}>
      Continue
    </Button>
  );
  const banner = snap.practice && <PracticeBanner />;
  if (snap.role === "coordinator") {
    return (
      <>
        {banner}
        <GameHeader snap={snap} clockOffset={clockOffset} />
        {snap.phase !== "finished" && <SharedState snap={snap} />}
        <CoordinatorScreen snap={snap} call={call} />
        {next}
      </>
    );
  }
  const key = `${snap.phase}-${snap.round}`;
  let panel = null;
  if (snap.phase === "finished") panel = <FinalPanel snap={snap} />;
  else if (snap.phase === "event") panel = <EventPanel key={key} snap={snap} call={call} />;
  else if (snap.phase === "policy") panel = <PolicyWaitPanel snap={snap} />;
  else if (snap.phase === "communication") panel = <CommunicationPanel key={key} snap={snap} call={call} />;
  else if (snap.phase === "decision") panel = <DecisionPanel key={key} snap={snap} call={call} />;
  else if (snap.phase === "resolution") panel = <ResultsPanel key={key} snap={snap} call={call} />;
  else panel = <Typography>Starting…</Typography>;
  return (
    <>
      {banner}
      <GameHeader snap={snap} clockOffset={clockOffset} />
      {snap.phase !== "finished" && <SharedState snap={snap} />}
      {snap.phase !== "finished" && <PolicyBanner snap={snap} />}
      {panel}
      {next}
    </>
  );
}
