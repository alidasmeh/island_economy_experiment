// Create sessions and list existing ones.
import React, { useCallback, useContext, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Container,
  FormControlLabel,
  FormGroup,
  Paper,
  Radio,
  RadioGroup,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { AuthContext } from "../contexts/AuthContext";
import { createSession, getRules, listSessions, UnauthorizedError } from "../api";
import { LinkBox } from "../components/LinkBox";

// The two conditions of Study 1.
// Ways a participant can leave the study, each with its own Prolific completion code.
const CODE_FIELDS = [
  ["completed", "Completed"],
  ["quiz_failed", "Failed the quiz"],
  ["no_group", "No group (waited too long)"],
  ["aborted", "Game stopped (technical)"],
];

const CONDITIONS = [
  { value: "none", label: "No coordinator", available: true },
  { value: "human", label: "Human coordinator (groups of 4 islanders + 1 coordinator)", available: true },
];

function parseSeeds(text) {
  const parts = text.split(/[\s,;]+/).filter(Boolean);
  const seeds = parts.map((p) => Number(p));
  if (!parts.length || seeds.some((n) => !Number.isInteger(n) || n < 0)) return null;
  return seeds;
}

export function useAdminCall() {
  const { logout } = useContext(AuthContext);
  return useCallback(
    async (fn, setError) => {
      try {
        return await fn();
      } catch (e) {
        if (e instanceof UnauthorizedError) logout();
        else setError(e.message);
        return null;
      }
    },
    [logout]
  );
}

function CreateSessionForm({ onCreated }) {
  const run = useAdminCall();
  const [label, setLabel] = useState("");
  const [conditions, setConditions] = useState(["none"]);
  const [seedMode, setSeedMode] = useState("random");
  const [nGroups, setNGroups] = useState("3");
  const [seedText, setSeedText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState(null);
  const [codes, setCodes] = useState({});
  const [groupSize, setGroupSize] = useState(null);

  useEffect(() => {
    getRules()
      .then((r) => setGroupSize(r.n_players))
      .catch(() => {});
  }, []);

  const seeds = seedMode === "own" ? parseSeeds(seedText) : null;
  const n = seedMode === "random" ? Number(nGroups) : seeds ? seeds.length : 0;
  const nOk = Number.isInteger(n) && n >= 1 && n <= 10000;
  const totalGroups = nOk ? n * conditions.length : 0;
  const valid = conditions.length > 0 && nOk && (seedMode === "random" || seeds);

  const toggle = (c) =>
    setConditions((cur) => (cur.includes(c) ? cur.filter((x) => x !== c) : [...cur, c]));

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setCreated(null);
    setBusy(true);
    const body = { label: label.trim(), conditions, completion_codes: codes };
    if (seedMode === "random") body.n_seeds = n;
    else body.seeds = seeds;
    const res = await run(() => createSession(body), setError);
    setBusy(false);
    if (res) {
      setCreated(res);
      onCreated();
    }
  };

  return (
    <Paper variant="outlined" sx={{ p: 2.5, mb: 3 }}>
      <Typography variant="h6" gutterBottom>
        Create a new session
      </Typography>
      <Box component="form" onSubmit={submit}>
        <TextField
          label="Name (for you only)"
          placeholder="e.g. pilot 12 Nov"
          fullWidth
          size="small"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          inputProps={{ maxLength: 200 }}
          sx={{ mb: 2 }}
        />

        <Typography variant="subtitle2">Conditions</Typography>
        <FormGroup sx={{ mb: 2 }}>
          {CONDITIONS.map((c) => (
            <FormControlLabel
              key={c.value}
              disabled={!c.available}
              control={<Checkbox checked={conditions.includes(c.value)} onChange={() => toggle(c.value)} />}
              label={c.label}
            />
          ))}
        </FormGroup>

        <Typography variant="subtitle2">Groups and seeds</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          A seed fixes a group's luck (starting coins, skills, events, number of rounds). Each seed is played once
          in every chosen condition, so the conditions get exactly the same luck.
        </Typography>
        <RadioGroup value={seedMode} onChange={(e) => setSeedMode(e.target.value)}>
          <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap">
            <FormControlLabel value="random" control={<Radio />} label="Random seeds — number of seeds:" />
            <TextField
              size="small"
              type="number"
              value={nGroups}
              onChange={(e) => setNGroups(e.target.value)}
              disabled={seedMode !== "random"}
              inputProps={{ min: 1, max: 10000 }}
              sx={{ width: 100 }}
            />
          </Stack>
          <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap">
            <FormControlLabel value="own" control={<Radio />} label="My own seeds:" />
            <TextField
              size="small"
              placeholder="e.g. 1, 2, 3"
              value={seedText}
              onChange={(e) => setSeedText(e.target.value)}
              disabled={seedMode !== "own"}
              error={seedMode === "own" && seedText !== "" && !seeds}
              helperText={seedMode === "own" && seedText !== "" && !seeds ? "Whole numbers separated by commas" : " "}
              sx={{ width: 220 }}
            />
          </Stack>
        </RadioGroup>

        <Typography variant="subtitle2" sx={{ mt: 1 }}>Prolific completion codes</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
          Create these codes in your Prolific study and copy them here. Participants see the code for how they left
          the study, with a button back to Prolific. Empty fields use the defaults from the server config.
        </Typography>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 1 }}>
          {CODE_FIELDS.map(([key, text]) => (
            <TextField key={key} size="small" label={text} value={codes[key] || ""}
              onChange={(e) => setCodes((c) => ({ ...c, [key]: e.target.value.trim() }))}
              inputProps={{ maxLength: 64, style: { fontFamily: "monospace" } }} sx={{ width: { sm: 200 } }} />
          ))}
        </Stack>

        <Typography variant="body2" sx={{ my: 1.5 }}>
          {valid ? (
            <>
              This plans <b>{totalGroups}</b> group{totalGroups === 1 ? "" : "s"}
              {groupSize && (
                <>
                  {" "}
                  — <b>{n * conditions.reduce((t, c) => t + groupSize + (c === "human" ? 1 : 0), 0)}</b> participants in
                  total
                </>
              )}
              . Later arrivals are told the session is full.
            </>
          ) : (
            "Choose at least one condition and at least one seed."
          )}
        </Typography>

        {error && (
          <Alert severity="error" sx={{ mb: 1.5 }}>
            {error}
          </Alert>
        )}
        <Button type="submit" variant="contained" disabled={!valid || busy}>
          {busy ? "Creating…" : "Create session"}
        </Button>
      </Box>

      {created && (
        <Alert severity="success" sx={{ mt: 2 }}>
          <Typography variant="body2" gutterBottom>
            Session <b>{created.session_code}</b> created with {created.assignments.length} group
            {created.assignments.length === 1 ? "" : "s"}.
          </Typography>
          <LinkBox code={created.session_code} />
        </Alert>
      )}
    </Paper>
  );
}

export default function SessionsPage() {
  const navigate = useNavigate();
  const run = useAdminCall();
  const [sessions, setSessions] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    const res = await run(listSessions, setError);
    if (res) {
      setError("");
      setSessions([...res].sort((a, b) => b.created_at.localeCompare(a.created_at)));
    }
  }, [run]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <Container maxWidth="md" sx={{ py: 3 }}>
      <CreateSessionForm onCreated={load} />

      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
        <Typography variant="h6">Sessions</Typography>
        <Button size="small" onClick={load}>
          Refresh
        </Button>
      </Stack>
      {error && (
        <Alert severity="error" sx={{ mb: 1.5 }}>
          {error}
        </Alert>
      )}
      {sessions && sessions.length === 0 && (
        <Typography color="text.secondary">No sessions yet.</Typography>
      )}
      {sessions && sessions.length > 0 && (
        <Paper variant="outlined" sx={{ overflowX: "auto" }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Code</TableCell>
                <TableCell>Name</TableCell>
                <TableCell>Created</TableCell>
                <TableCell align="right">Groups</TableCell>
                <TableCell>Status</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {sessions.map((s) => (
                <TableRow
                  key={s.session_code}
                  hover
                  sx={{ cursor: "pointer" }}
                  onClick={() => navigate(`/sessions/${s.session_code}`)}
                >
                  <TableCell sx={{ fontFamily: "monospace" }}>{s.session_code}</TableCell>
                  <TableCell>{s.label || "—"}</TableCell>
                  <TableCell>{new Date(s.created_at).toLocaleString()}</TableCell>
                  <TableCell align="right">{s.n_groups_planned}</TableCell>
                  <TableCell>{s.status}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}
    </Container>
  );
}
