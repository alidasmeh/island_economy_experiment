import React, { useMemo, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Collapse,
  Divider,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Slider,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { coins } from "../format";

const ROWS = [
  { key: "harvest", label: "Fish", help: "Catch fish and sell them now." },
  { key: "contribute", label: "Build infrastructure", help: "Improves everyone's fishing in later rounds." },
  { key: "save", label: "Save", help: "Adds to your private savings, which earn interest." },
];

// Rough income estimate from public parameters and own information. Labeled as an estimate:
// the real result also depends on what others do (the catch is cut if the group over-fishes), audits and events.
function estimate(snap, alloc) {
  const o = snap.observation;
  const pv = snap.preview;
  const fish = pv.catchability * alloc.harvest * o.stock * o.skill * o.infra * pv.harvest_mult;
  const gross = fish * pv.price * pv.price_mult;
  const tax = gross * pv.tax_rate;
  const saving = pv.saving_return_per_point * alloc.save;
  const interest = pv.interest_rate * o.capital;
  return { fish, gross, tax, saving, interest, overQuota: pv.quota > 0 && fish > pv.quota };
}

export default function DecisionPanel({ snap, call }) {
  const E = snap.preview.effort_points;
  const [alloc, setAlloc] = useState({ harvest: 0, contribute: 0, save: 0 });
  const [sliderChanges, setSliderChanges] = useState(0);
  const [showTransfer, setShowTransfer] = useState(false);
  const [transferTo, setTransferTo] = useState("");
  const [transferAmount, setTransferAmount] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const shownAt = useRef(Date.now());

  const used = alloc.harvest + alloc.contribute + alloc.save;
  const left = E - used;
  const est = useMemo(() => estimate(snap, alloc), [snap, alloc]);
  const wealth = snap.observation.wealth;
  const amount = Number(transferAmount || 0);
  const transferValid = !showTransfer || amount === 0 || (transferTo !== "" && amount > 0 && amount <= wealth);

  if (snap.done) {
    const d = snap.my_decision;
    return (
      <Paper elevation={0} sx={{ p: 2, border: 1, borderColor: "divider" }}>
        <Typography variant="h6">Decision submitted</Typography>
        {d && (
          <Typography variant="body2" sx={{ mt: 1 }}>
            Fish {d.harvest} · Infrastructure {d.contribute} · Save {d.save}
            {d.transfer_amount > 0 && ` · Send ${coins(d.transfer_amount)} coins to ${snap.labels[d.transfer_to]}`}
          </Typography>
        )}
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          Waiting for the others ({snap.n_done} of {snap.n_players} have decided).
        </Typography>
      </Paper>
    );
  }

  const setRow = (key, v) => {
    const others = used - alloc[key];
    setAlloc({ ...alloc, [key]: Math.max(0, Math.min(v, E - others)) });
  };

  const submit = async () => {
    setBusy(true);
    setError("");
    const ack = await call("submit_decision", {
      round: snap.round,
      ...alloc,
      transfer_to: showTransfer && amount > 0 ? Number(transferTo) : null,
      transfer_amount: showTransfer && amount > 0 ? amount : 0,
      slider_changes: sliderChanges,
      client_response_ms: Date.now() - shownAt.current,
    });
    setBusy(false);
    if (!ack.ok) setError(ack.error || "Could not submit");
  };

  return (
    <Paper elevation={0} sx={{ p: 2, border: 1, borderColor: "divider" }}>
      <Typography variant="h6">How do you use your {E} effort points?</Typography>
      <Typography variant="body2" color="text.secondary">
        {snap.has_coordinator
          ? "Other islanders do not see your choice while you decide; the coordinator sees it after the round."
          : "Other islanders do not see your choice while you decide."}{" "}
        Points left: <b>{left}</b>
      </Typography>
      <Stack spacing={1.5} sx={{ mt: 2 }}>
        {ROWS.map((r) => (
          <Box key={r.key}>
            <Stack direction="row" justifyContent="space-between">
              <Typography fontWeight={600}>{r.label}</Typography>
              <Typography fontWeight={600}>{alloc[r.key]}</Typography>
            </Stack>
            <Slider
              value={alloc[r.key]}
              min={0}
              max={E}
              step={1}
              marks
              onChange={(_e, v) => setRow(r.key, v)}
              onChangeCommitted={() => setSliderChanges((n) => n + 1)}
              aria-label={r.label}
            />
            <Typography variant="caption" color="text.secondary">
              {r.help}
            </Typography>
          </Box>
        ))}
      </Stack>

      <Divider sx={{ my: 2 }} />
      <Typography variant="body2" fontWeight={600}>
        Estimated income this round (an estimate, not a promise)
      </Typography>
      <Box component="dl" sx={{ display: "grid", gridTemplateColumns: "1fr auto", columnGap: 2, rowGap: 0.25, m: 0, mt: 0.5 }}>
        <Typography component="dt" variant="body2">Fishing: about {coins(est.fish)} fish</Typography>
        <Typography component="dd" variant="body2" sx={{ m: 0, textAlign: "right" }}>{coins(est.gross - est.tax)} coins</Typography>
        {est.tax > 0 && (
          <>
            <Typography component="dt" variant="body2" color="text.secondary">(after {coins(est.tax)} tax)</Typography>
            <Typography component="dd" variant="body2" sx={{ m: 0 }} />
          </>
        )}
        <Typography component="dt" variant="body2">Savings</Typography>
        <Typography component="dd" variant="body2" sx={{ m: 0, textAlign: "right" }}>+{coins(est.saving)} coins</Typography>
        <Typography component="dt" variant="body2" color="text.secondary">Interest on your savings</Typography>
        <Typography component="dd" variant="body2" sx={{ m: 0, textAlign: "right" }}>+{coins(est.interest)} coins</Typography>
      </Box>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
        Your actual catch can be lower if the group together tries to catch more fish than there are.
      </Typography>
      {est.overQuota && (
        <Alert severity="warning" sx={{ mt: 1 }}>
          This catch is above the quota of {snap.preview.quota} fish.
        </Alert>
      )}

      <Button size="small" sx={{ mt: 1.5, px: 0 }} onClick={() => setShowTransfer((v) => !v)}>
        {showTransfer ? "Don't send coins" : "Send coins to another islander (optional)"}
      </Button>
      <Collapse in={showTransfer}>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} sx={{ mt: 1 }}>
          <FormControl size="small" sx={{ minWidth: 160 }}>
            <InputLabel id="transfer-to">Recipient</InputLabel>
            <Select labelId="transfer-to" label="Recipient" value={transferTo} onChange={(e) => setTransferTo(e.target.value)}>
              {snap.labels.map((l, i) =>
                i === snap.seat ? null : (
                  <MenuItem key={i} value={i}>
                    {l}
                  </MenuItem>
                )
              )}
            </Select>
          </FormControl>
          <TextField
            size="small"
            type="number"
            label="Coins"
            value={transferAmount}
            onChange={(e) => setTransferAmount(e.target.value)}
            inputProps={{ min: 0, max: wealth, step: 1 }}
            helperText={`You have ${coins(wealth)} coins`}
            error={showTransfer && amount > wealth}
          />
        </Stack>
      </Collapse>

      {error && (
        <Alert severity="error" sx={{ mt: 1.5 }}>
          {error}
        </Alert>
      )}
      <Button
        fullWidth
        variant="contained"
        size="large"
        sx={{ mt: 2 }}
        disabled={left !== 0 || !transferValid || busy}
        onClick={submit}
      >
        {left !== 0 ? `Use all ${E} points (${left} left)` : "Submit decision"}
      </Button>
      <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 1 }}>
        If you don't submit in time, last round's split is used again.
      </Typography>
    </Paper>
  );
}
