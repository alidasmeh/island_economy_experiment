import React, { useState } from "react";
import {
  Alert,
  Box,
  Button,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from "@mui/material";
import { coins, describeEvent, signed } from "../format";

function ReadyButton({ snap, call, label = "Continue" }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (snap.done) {
    return (
      <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
        Waiting for the others ({snap.n_done} of {snap.n_players} ready). The next step starts when everyone is
        ready or the time is up.
      </Typography>
    );
  }
  return (
    <>
      {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
      <Button
        fullWidth
        variant="contained"
        size="large"
        sx={{ mt: 2 }}
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          const ack = await call("ready", { phase: snap.phase });
          setBusy(false);
          if (!ack.ok) setError(ack.error || "Something went wrong");
        }}
      >
        {label}
      </Button>
    </>
  );
}

export function EventPanel({ snap, call }) {
  const ev = describeEvent(snap.observation.event);
  return (
    <Paper elevation={0} sx={{ p: 2, border: 1, borderColor: "divider" }}>
      <Typography variant="overline" color="text.secondary">This round's event</Typography>
      <Typography variant="h5" gutterBottom>{ev.title}</Typography>
      {ev.effects.map((e) => (
        <Typography key={e} variant="body1">{e}</Typography>
      ))}
      <ReadyButton snap={snap} call={call} />
    </Paper>
  );
}

export function CommunicationPanel({ snap, call }) {
  return (
    <Paper elevation={0} sx={{ p: 2, border: 1, borderColor: "divider" }}>
      <Typography variant="h6" gutterBottom>Talk to your group</Typography>
      <Alert severity="info">Chat is not available in this version of the game yet.</Alert>
      <ReadyButton snap={snap} call={call} label="Continue to the decision" />
    </Paper>
  );
}

function Line({ label, value, strong }) {
  return (
    <>
      <Typography component="dt" variant="body2" fontWeight={strong ? 700 : 400}>{label}</Typography>
      <Typography component="dd" variant="body2" fontWeight={strong ? 700 : 400} sx={{ m: 0, textAlign: "right" }}>
        {value}
      </Typography>
    </>
  );
}

function FairnessRating({ snap, call }) {
  const [error, setError] = useState("");
  return (
    <Box sx={{ mt: 2 }}>
      <Typography variant="body2" fontWeight={600}>
        How fair are the current rules? (optional)
      </Typography>
      <ToggleButtonGroup
        exclusive
        size="small"
        fullWidth
        value={snap.my_rating}
        onChange={async (_e, v) => {
          if (v === null) return;
          const ack = await call("submit_rating", { round: snap.round, rating: v });
          if (!ack.ok) setError(ack.error || "Could not save the rating");
        }}
        sx={{ mt: 0.5 }}
        aria-label="Fairness rating from 1 (very unfair) to 7 (very fair)"
      >
        {[1, 2, 3, 4, 5, 6, 7].map((v) => (
          <ToggleButton key={v} value={v}>{v}</ToggleButton>
        ))}
      </ToggleButtonGroup>
      <Stack direction="row" justifyContent="space-between">
        <Typography variant="caption" color="text.secondary">1 = very unfair</Typography>
        <Typography variant="caption" color="text.secondary">7 = very fair</Typography>
      </Stack>
      {error && <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert>}
    </Box>
  );
}

export function ResultsPanel({ snap, call }) {
  const own = snap.observation.last_round_own;
  const group = snap.observation.last_round_group;
  const others = snap.observation.last_round_individual;
  const hist = snap.history[snap.history.length - 1];
  if (!own || !group || !hist) return null;
  const capitalGain = own.capital_after - own.capital_before;
  const wealthChange = own.wealth_after - own.wealth_before;
  return (
    <Paper elevation={0} sx={{ p: 2, border: 1, borderColor: "divider" }}>
      <Typography variant="h6">Results of round {snap.round}</Typography>
      {own.timeout && (
        <Alert severity="warning" sx={{ mt: 1 }}>
          You did not decide in time, so your previous split was used.
        </Alert>
      )}
      <Typography variant="body2" sx={{ mt: 1 }}>
        You used: fish {own.harvest_effort} · infrastructure {own.contribute_effort} · save {own.save_effort}
      </Typography>
      <Box component="dl" sx={{ display: "grid", gridTemplateColumns: "1fr auto", columnGap: 2, rowGap: 0.25, mt: 1.5, mb: 0 }}>
        <Line label={`Fish caught (${coins(own.harvest)})`} value={`+${coins(own.harvest_income)}`} />
        {own.tax > 0 && <Line label="Tax" value={signed(-own.tax)} />}
        {own.redistribution > 0 && <Line label="Share of the tax pot" value={signed(own.redistribution)} />}
        {own.fines_paid > 0 && <Line label="Fines" value={signed(-own.fines_paid)} />}
        {own.premium > 0 && <Line label="Insurance premium" value={signed(-own.premium)} />}
        {own.insurance_payout > 0 && <Line label="Insurance payout" value={signed(own.insurance_payout)} />}
        {own.transfer_out > 0 && <Line label="Coins you sent" value={signed(-own.transfer_out)} />}
        {own.transfer_in > 0 && <Line label="Coins you received" value={signed(own.transfer_in)} />}
        <Line label="Change in coins" value={signed(wealthChange)} strong />
        <Line label="Added to savings (incl. interest)" value={signed(capitalGain)} strong />
      </Box>

      <Typography variant="subtitle2" sx={{ mt: 2 }}>Your group</Typography>
      <Typography variant="body2">
        The group caught {coins(group.total_harvest)} fish. Fish in the sea now: {coins(group.stock_after)}.
        Infrastructure is now {coins(group.infra_after, 2)}.
      </Typography>
      {others ? (
        <Box sx={{ overflowX: "auto", mt: 1 }}>
          <Table
            size="small"
            aria-label="What each islander did"
            sx={{ "& td, & th": { px: 0.75 }, "& td:first-of-type, & th:first-of-type": { pl: 0 } }}
          >
            <TableHead>
              <TableRow>
                <TableCell>Islander</TableCell>
                <TableCell align="right">Fish</TableCell>
                <TableCell align="right">Infra.</TableCell>
                <TableCell align="right">Save</TableCell>
                <TableCell align="right">Caught</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {others.map((r) => (
                <TableRow key={r.seat} selected={r.seat === snap.seat}>
                  <TableCell>
                    {snap.labels[r.seat].replace("Islander ", "")}
                    {r.seat === snap.seat ? " (you)" : ""}
                  </TableCell>
                  <TableCell align="right">{r.harvest_effort}</TableCell>
                  <TableCell align="right">{r.contribute_effort}</TableCell>
                  <TableCell align="right">{r.save_effort}</TableCell>
                  <TableCell align="right">{coins(r.harvest)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      ) : (
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          On average, islanders put {coins(group.avg_harvest_effort)} points into fishing,{" "}
          {coins(group.avg_contribute_effort)} into infrastructure and {coins(group.avg_save_effort)} into saving.
        </Typography>
      )}
      <FairnessRating snap={snap} call={call} />
      <ReadyButton snap={snap} call={call} label="Next round" />
    </Paper>
  );
}

export function FinalPanel({ snap }) {
  const f = snap.final;
  if (!f) return null;
  return (
    <Paper elevation={0} sx={{ p: 2, border: 1, borderColor: "divider" }}>
      <Typography variant="h5" gutterBottom>The game is over</Typography>
      <Box component="dl" sx={{ display: "grid", gridTemplateColumns: "1fr auto", columnGap: 2, rowGap: 0.25 }}>
        <Line label="Coins" value={coins(f.wealth)} />
        <Line label="Savings" value={coins(f.capital)} />
        {f.pool_refund > 0 && <Line label="Insurance pool refund" value={coins(f.pool_refund)} />}
        <Line label="Total" value={`${coins(f.payoff_coins)} coins`} strong />
        <Line label="Your bonus" value={`${f.payoff_money.toFixed(2)} ${snap.currency}`} strong />
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
        {f.coins_per_currency_unit} coins = 1 {snap.currency}.
      </Typography>
    </Paper>
  );
}

export function WaitingRoom({ snap }) {
  return (
    <Paper elevation={0} sx={{ p: 3, border: 1, borderColor: "divider", textAlign: "center" }}>
      <Typography variant="h5" gutterBottom>Waiting for other participants</Typography>
      <Typography variant="body1">
        {snap.n_waiting} of {snap.n_needed} participants are here.
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
        The game starts automatically when your group is complete. Please keep this tab open.
      </Typography>
    </Paper>
  );
}
