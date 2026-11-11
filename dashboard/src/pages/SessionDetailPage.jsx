// One session: links, waiting room and each group's progress (refreshes every few seconds).
import React, { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Alert,
  Button,
  Chip,
  Container,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { getSession } from "../api";
import { LinkBox } from "../components/LinkBox";
import { useAdminCall } from "./SessionsPage";

const REFRESH_MS = 3000;

const CONDITION_LABELS = { none: "No coordinator", human: "Human coordinator" };
const PHASE_LABELS = {
  event: "Event",
  policy: "Policy",
  communication: "Talk",
  decision: "Decide",
  resolution: "Results",
  finished: "Finished",
};

const FLAG_LABELS = { coordinator_dropout: "coordinator left" };

function flagLabel(f) {
  return `${FLAG_LABELS[f.type] || f.type}${f.round ? ` (round ${f.round})` : ""}`;
}

function statusChip(status) {
  const color = { running: "primary", finished: "success", aborted: "error" }[status] || "default";
  return <Chip size="small" label={status} color={color} variant={status === "running" ? "filled" : "outlined"} />;
}

export default function SessionDetailPage() {
  const { code } = useParams();
  const navigate = useNavigate();
  const run = useAdminCall();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [updated, setUpdated] = useState(null);

  const load = useCallback(async () => {
    const res = await run(() => getSession(code), setError);
    if (res) {
      setError("");
      setData(res);
      setUpdated(new Date());
    }
  }, [code, run]);

  useEffect(() => {
    load();
    const t = setInterval(load, REFRESH_MS);
    return () => clearInterval(t);
  }, [load]);

  const planned = data ? data.assignments.length : 0;
  const started = data ? data.groups.length : 0;

  return (
    <Container maxWidth="md" sx={{ py: 3 }}>
      <Button size="small" onClick={() => navigate("/")} sx={{ mb: 1 }}>
        ← All sessions
      </Button>
      {error && (
        <Alert severity="error" sx={{ mb: 1.5 }}>
          {error}
        </Alert>
      )}
      {data && (
        <>
          <Typography variant="h5">
            Session <span style={{ fontFamily: "monospace" }}>{data.session_code}</span>
          </Typography>
          <Typography color="text.secondary" gutterBottom>
            {data.label || "No name"} · {data.status}
          </Typography>

          <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
            <LinkBox code={data.session_code} />
          </Paper>

          <Stack direction="row" spacing={2} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
            <Paper variant="outlined" sx={{ p: 2, minWidth: 150 }}>
              <Typography variant="overline" color="text.secondary">
                In the waiting room
              </Typography>
              <Typography variant="h5">{data.n_waiting}</Typography>
            </Paper>
            <Paper variant="outlined" sx={{ p: 2, minWidth: 150 }}>
              <Typography variant="overline" color="text.secondary">
                Groups started
              </Typography>
              <Typography variant="h5">
                {started} / {planned}
              </Typography>
            </Paper>
          </Stack>

          <Typography variant="h6" gutterBottom>
            Groups
          </Typography>
          {started === 0 ? (
            <Typography color="text.secondary">
              No group has started yet. A group starts as soon as the waiting room has enough participants for one group.
            </Typography>
          ) : (
            <Paper variant="outlined" sx={{ overflowX: "auto" }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>#</TableCell>
                    <TableCell>Condition</TableCell>
                    <TableCell align="right">Seed</TableCell>
                    <TableCell align="right">Round</TableCell>
                    <TableCell>Step</TableCell>
                    <TableCell>Status</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {data.groups.map((g, i) => (
                    <TableRow key={g.group_id}>
                      <TableCell>{i + 1}</TableCell>
                      <TableCell>{CONDITION_LABELS[g.condition] || g.condition}</TableCell>
                      <TableCell align="right">{g.seed}</TableCell>
                      <TableCell align="right">
                        {g.round ?? "–"}
                        {g.n_rounds ? ` of ${g.n_rounds}` : ""}
                      </TableCell>
                      <TableCell>{g.phase ? PHASE_LABELS[g.phase] || g.phase : "–"}</TableCell>
                      <TableCell>
                        {statusChip(g.status)}{" "}
                        {g.flagged && (g.flags && g.flags.length
                          ? g.flags.map((f, k) => <Chip key={k} size="small" color="warning" label={flagLabel(f)} sx={{ mr: 0.5 }} />)
                          : <Chip size="small" color="warning" label="flagged" />)}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Paper>
          )}

          {planned > started && (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
              Still to start:{" "}
              {data.assignments
                .slice(started)
                .map((a) => `${CONDITION_LABELS[a.condition] || a.condition} (seed ${a.seed})`)
                .join(", ")}
            </Typography>
          )}
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 2 }}>
            Flagged groups (for example, the coordinator left) should be analysed separately. Updates automatically every {REFRESH_MS / 1000} seconds
            {updated ? ` · last update ${updated.toLocaleTimeString()}` : ""}. The number of rounds is shown here
            only; participants never see it.
          </Typography>
        </>
      )}
    </Container>
  );
}
