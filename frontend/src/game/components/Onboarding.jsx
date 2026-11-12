// Onboarding and exit screens (Milestone 7): consent, quiz, practice, questionnaire, payment page.
// Every step is checked and recorded by the server; these screens only show it and send answers.
import React, { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Checkbox,
  CircularProgress,
  Divider,
  FormControl,
  FormControlLabel,
  FormLabel,
  MenuItem,
  Paper,
  Radio,
  RadioGroup,
  Select,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import studyInfo from "../studyInfo";

function Card({ children }) {
  return (
    <Paper elevation={0} sx={{ p: { xs: 2, sm: 3 }, border: 1, borderColor: "divider" }}>
      {children}
    </Paper>
  );
}

function P({ children, ...rest }) {
  return (
    <Typography variant="body1" sx={{ mb: 1.5 }} {...rest}>
      {children}
    </Typography>
  );
}

const money = (x, currency) => `${Number(x || 0).toFixed(2)} ${currency}`;

// ---------------------------------------------------------------------- consent

export function Consent({ rules, call }) {
  const [checked, setChecked] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const answer = async (consent) => {
    setBusy(true);
    const ack = await call("give_consent", { consent });
    if (!ack.ok) {
      setError(ack.error || "Could not save your answer");
      setBusy(false);
    }
  };
  const s = studyInfo;
  return (
    <Card>
      <Typography variant="overline" color="text.secondary">
        Information and consent
      </Typography>
      <Typography variant="h5" gutterBottom>
        {s.title}
      </Typography>
      <P>
        This study is run by {s.researchers} at the {s.institution}. It takes about {s.expectedMinutes} minutes.
      </P>
      <Typography variant="subtitle1" fontWeight={700}>
        What you will do
      </Typography>
      <P>
        You read short instructions, answer a few questions about them, play {rules.n_practice} practice rounds
        with computer players, and then play a game in real time with other participants. At the end you answer a short
        questionnaire. The other participants in your game are real people taking part right now.
      </P>
      <Typography variant="subtitle1" fontWeight={700}>
        Payment
      </Typography>
      <P>
        You receive the participation payment of {money(rules.show_up_fee, rules.currency)} for taking part. In the
        game you can earn a bonus on top: {rules.coins_per_currency_unit} coins = 1 {rules.currency}. If you do not
        pass the questions about the instructions, the study ends there and you receive the participation payment only.
      </P>
      <Typography variant="subtitle1" fontWeight={700}>
        Your data
      </Typography>
      <P>
        We record your answers and everything you do in the game, including the timing of your actions and the messages
        you write. Your data are stored under a random code, separately from your Prolific ID, which we keep only to pay
        you. Nobody in the game learns who you are. The data are used for research only and may be shared with other
        researchers in anonymous form.
      </P>
      <Typography variant="subtitle1" fontWeight={700}>
        Your rights
      </Typography>
      <P>
        Taking part is voluntary. You can stop at any time by closing this page, without giving a reason. The other
        participants in your game depend on you, so please only start if you can stay until the end.
      </P>
      <P>
        Questions: {s.contactEmail}. This study was approved by {s.ethicsApproval}.
      </P>
      <Divider sx={{ my: 2 }} />
      <FormControlLabel
        control={<Checkbox checked={checked} onChange={(e) => setChecked(e.target.checked)} />}
        label="I have read this information, I am at least 18 years old, and I agree to take part."
      />
      {error && <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert>}
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mt: 2 }}>
        <Button variant="outlined" disabled={busy} onClick={() => answer(false)} sx={{ flex: 1 }}>
          I do not agree
        </Button>
        <Button variant="contained" disabled={!checked || busy} onClick={() => answer(true)} sx={{ flex: 2 }}>
          I agree, continue
        </Button>
      </Stack>
    </Card>
  );
}

// ---------------------------------------------------------------------- quiz

export function Quiz({ quiz, call, onReread }) {
  const [answers, setAnswers] = useState({});
  const [result, setResult] = useState(null); // last failed attempt: {wrong, attempts_left}
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const shownAt = useMemo(() => Date.now(), []);
  const complete = quiz.questions.every((q) => answers[q.id] !== undefined);
  const wrong = new Set(result ? result.wrong : []);

  const submit = async () => {
    setBusy(true);
    setError("");
    const ack = await call("submit_quiz", { answers, seconds: Math.round((Date.now() - shownAt) / 1000) });
    setBusy(false);
    if (!ack.ok) setError(ack.error || "Could not submit your answers");
    else if (!ack.passed) {
      setResult(ack);
      setAnswers({});
      window.scrollTo(0, 0);
    }
    // On a pass (or a final fail) the server sends the next screen.
  };

  return (
    <Card>
      <Typography variant="overline" color="text.secondary">
        Questions about the instructions
      </Typography>
      <Typography variant="h5" gutterBottom>
        Check your understanding
      </Typography>
      {result ? (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {result.wrong.length === 1 ? "One answer was" : `${result.wrong.length} answers were`} not right (marked
          below). You have {result.attempts_left} more {result.attempts_left === 1 ? "try" : "tries"}. If it is not right
          then, the study ends and you receive the participation payment only.
          <Box sx={{ mt: 1 }}>
            <Button size="small" variant="outlined" onClick={onReread}>
              Read the instructions again
            </Button>
          </Box>
        </Alert>
      ) : (
        <P>
          Please answer every question. You need all answers right to continue; you have {quiz.max_attempts - quiz.attempts_used}{" "}
          {quiz.max_attempts - quiz.attempts_used === 1 ? "try" : "tries"}.
        </P>
      )}
      {quiz.questions.map((q, n) => (
        <FormControl key={q.id} component="fieldset" sx={{ display: "block", mb: 2 }}
          error={wrong.has(q.id) && answers[q.id] === undefined}>
          <FormLabel component="legend" sx={{ color: "text.primary", fontWeight: 600, mb: 0.5 }}>
            {n + 1}. {q.text}
            {wrong.has(q.id) && (
              <Typography component="span" color="error" variant="body2">
                {" "}
                (not right last time)
              </Typography>
            )}
          </FormLabel>
          <RadioGroup
            value={answers[q.id] === undefined ? "" : String(answers[q.id])}
            onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: Number(e.target.value) }))}
          >
            {q.options.map((o, k) => (
              <FormControlLabel key={k} value={String(k)} control={<Radio size="small" />} label={o}
                sx={{ alignItems: "flex-start", my: 0.25, "& .MuiRadio-root": { pt: 0.5 } }} />
            ))}
          </RadioGroup>
        </FormControl>
      ))}
      {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
      <Button variant="contained" fullWidth disabled={!complete || busy} onClick={submit}>
        Submit answers
      </Button>
    </Card>
  );
}

// ---------------------------------------------------------------------- practice

export function PracticeIntro({ snap, call }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const coord = snap.role === "coordinator";
  const start = async () => {
    setBusy(true);
    const ack = await call("start_practice", {});
    if (!ack.ok) {
      setError(ack.error || "Could not start the practice rounds");
      setBusy(false);
    }
  };
  return (
    <Card>
      <Typography variant="overline" color="text.secondary">
        Practice
      </Typography>
      <Typography variant="h5" gutterBottom>
        All answers right. Now try it out
      </Typography>
      <P>
        You now play {snap.practice_rounds} practice {snap.practice_rounds === 1 ? "round" : "rounds"}{" "}
        {coord
          ? "as the coordinator. The islanders in practice are computer players that follow simple fixed strategies."
          : `with ${snap.n_computer} computer players that follow simple fixed strategies. In practice there are no rules and no chat.`}
      </P>
      <P>
        <b>Practice rounds do not count:</b> the coins you earn in practice are not paid. The timers are the same as in
        the real game.
      </P>
      <P>After practice you wait until your group of real participants is complete.</P>
      {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
      <Button variant="contained" fullWidth disabled={busy} onClick={start}>
        Start practice
      </Button>
    </Card>
  );
}

export function PracticeBanner() {
  return (
    <Alert severity="info" icon={false} sx={{ mb: 1.5, fontWeight: 600 }}>
      Practice with computer players — nothing here counts for your payment.
    </Alert>
  );
}

export function PracticeDone({ snap, call }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const f = snap.final;
  const go = async () => {
    setBusy(true);
    const ack = await call("finish_practice", {});
    if (!ack.ok) {
      setError(ack.error || "Could not continue");
      setBusy(false);
    }
  };
  return (
    <Card>
      <Typography variant="h5" gutterBottom>
        Practice is over
      </Typography>
      {snap.role !== "coordinator" && f && (
        <P>
          You ended practice with {Number(f.payoff_coins).toFixed(1)} coins. These coins are not paid; in the real game
          everyone starts again from the beginning.
        </P>
      )}
      <P>When you continue, you wait for the other participants. The real game starts as soon as your group is complete.</P>
      {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
      <Button variant="contained" fullWidth disabled={busy} onClick={go}>
        Continue to the waiting room
      </Button>
    </Card>
  );
}

// ---------------------------------------------------------------------- questionnaire

function Likert({ item, value, onChange }) {
  return (
    <Box>
      <ToggleButtonGroup exclusive fullWidth size="small" value={value ?? null}
        onChange={(_e, v) => v !== null && onChange(v)} aria-label={item.text}>
        {[1, 2, 3, 4, 5, 6, 7].map((n) => (
          <ToggleButton key={n} value={n} aria-label={String(n)}>
            {n}
          </ToggleButton>
        ))}
      </ToggleButtonGroup>
      <Stack direction="row" justifyContent="space-between">
        <Typography variant="caption" color="text.secondary">1 = {item.anchors[0]}</Typography>
        <Typography variant="caption" color="text.secondary">7 = {item.anchors[1]}</Typography>
      </Stack>
    </Box>
  );
}

export function Questionnaire({ items: given, call }) {
  const [items, setItems] = useState(given || null);
  const [answers, setAnswers] = useState({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const shownAt = useMemo(() => Date.now(), []);

  useEffect(() => {
    if (items) return;
    call("get_questionnaire", {}).then((ack) => {
      if (ack.ok) setItems(ack.items);
      else setError(ack.error || "Could not load the questionnaire");
    });
  }, [items, call]);

  if (!items) {
    return error ? <Alert severity="error">{error}</Alert> : <CircularProgress sx={{ mt: 4 }} />;
  }
  const set = (id, v) => setAnswers((a) => ({ ...a, [id]: v }));
  const missing = items.some((it) => it.required && (answers[it.id] === undefined || answers[it.id] === ""));
  const submit = async () => {
    setBusy(true);
    setError("");
    const ack = await call("submit_questionnaire", {
      answers,
      seconds: Math.round((Date.now() - shownAt) / 1000),
    });
    if (!ack.ok) {
      setError(ack.error || "Could not submit");
      setBusy(false);
    }
  };
  let section = null;
  return (
    <Card>
      <Typography variant="overline" color="text.secondary">
        Last step
      </Typography>
      <Typography variant="h5" gutterBottom>
        A few questions
      </Typography>
      <P>Please tell us about the game. There are no right or wrong answers.</P>
      {items.map((it) => {
        const header = it.section !== section;
        section = it.section;
        return (
          <Box key={it.id} sx={{ mb: 2.5 }}>
            {header && (
              <Typography variant="subtitle1" fontWeight={700} sx={{ mt: 1, mb: 1 }}>
                {it.section}
              </Typography>
            )}
            {/* Optional items say so in their text (defined in the backend). */}
            <Typography sx={{ mb: 0.75 }}>{it.text}</Typography>
            {it.kind === "likert7" && <Likert item={it} value={answers[it.id]} onChange={(v) => set(it.id, v)} />}
            {it.kind === "choice" && (
              <Select fullWidth size="small" displayEmpty value={answers[it.id] ?? ""}
                onChange={(e) => set(it.id, e.target.value)} inputProps={{ "aria-label": it.text }}>
                <MenuItem value="" disabled>
                  Choose…
                </MenuItem>
                {it.options.map((o) => (
                  <MenuItem key={o} value={o}>{o}</MenuItem>
                ))}
              </Select>
            )}
            {it.kind === "number" && (
              <TextField size="small" type="number" value={answers[it.id] ?? ""}
                inputProps={{ min: it.min, max: it.max, "aria-label": it.text }}
                onChange={(e) => set(it.id, e.target.value === "" ? undefined : e.target.value)} sx={{ width: 140 }} />
            )}
            {it.kind === "text" && (
              <TextField fullWidth multiline minRows={2} size="small" value={answers[it.id] ?? ""}
                inputProps={{ maxLength: it.max_chars, "aria-label": it.text }}
                onChange={(e) => set(it.id, e.target.value)} />
            )}
          </Box>
        );
      })}
      {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
      <Button variant="contained" fullWidth disabled={missing || busy} onClick={submit}>
        Submit and see my payment
      </Button>
    </Card>
  );
}

// ---------------------------------------------------------------------- exit and payment

const EXIT_TEXT = {
  completed: ["Thank you!", "You have finished the study."],
  quiz_failed: [
    "Thank you for your interest",
    "Unfortunately, not all answers about the instructions were right, so the study ends here. You receive the participation payment.",
  ],
  no_group: [
    "Thank you for waiting",
    "Not enough participants arrived to complete your group, so the study ends here. You receive the participation payment.",
  ],
  aborted: [
    "The game stopped",
    "The game stopped because of a technical problem. We are sorry. You receive the participation payment. If you have questions, please contact the researchers through Prolific.",
  ],
  no_consent: [
    "Thank you",
    "You did not agree to take part, so no data about you will be used. Please return the study on Prolific.",
  ],
};

export function ExitPage({ snap }) {
  const [title, text] = EXIT_TEXT[snap.outcome] || ["Thank you", ""];
  const cur = snap.currency;
  return (
    <Card>
      <Typography variant="h5" gutterBottom>
        {title}
      </Typography>
      <P>{text}</P>
      {snap.show_up_fee !== null && snap.show_up_fee !== undefined && (
        <Box component="dl" sx={{ display: "grid", gridTemplateColumns: "1fr auto", columnGap: 2, rowGap: 0.25, my: 2 }}>
          <Typography component="dt">Participation payment</Typography>
          <Typography component="dd" sx={{ m: 0, textAlign: "right" }}>{money(snap.show_up_fee, cur)}</Typography>
          {snap.bonus !== null && snap.bonus !== undefined && (
            <>
              <Typography component="dt">
                Bonus from the game{snap.role === "coordinator" ? " (as coordinator)" : ""}
              </Typography>
              <Typography component="dd" sx={{ m: 0, textAlign: "right" }}>{money(snap.bonus, cur)}</Typography>
              <Typography component="dt" fontWeight={700}>Total</Typography>
              <Typography component="dd" fontWeight={700} sx={{ m: 0, textAlign: "right" }}>
                {money(snap.show_up_fee + snap.bonus, cur)}
              </Typography>
            </>
          )}
        </Box>
      )}
      {snap.bonus !== null && snap.bonus !== undefined && (
        <P variant="body2" color="text.secondary">
          The participation payment is paid by Prolific when your submission is approved; the bonus is paid separately
          through Prolific after the study.
        </P>
      )}
      {snap.code ? (
        <>
          <P>
            Your completion code: <b style={{ fontFamily: "monospace", fontSize: "1.1em" }}>{snap.code}</b>
          </P>
          {snap.url && (
            <Button variant="contained" fullWidth href={snap.url}>
              Return to Prolific
            </Button>
          )}
        </>
      ) : (
        snap.outcome !== "no_consent" && (
          <Alert severity="info">
            Please return to Prolific. If you are asked for a completion code, contact the researchers at{" "}
            {studyInfo.contactEmail}.
          </Alert>
        )
      )}
      <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
        You can close this page now.
      </Typography>
    </Card>
  );
}
