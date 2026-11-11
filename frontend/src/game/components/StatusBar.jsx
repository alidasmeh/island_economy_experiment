import React from "react";
import { Box, Chip, LinearProgress, Paper, Stack, Typography } from "@mui/material";
import { coins, describeEvent, describeRedistribution, PHASE_TITLES } from "../format";
import { useCountdown } from "../useGame";

// Round, phase steps, timer and own wealth.
export function GameHeader({ snap, clockOffset }) {
  const left = useCountdown(snap.phase === "finished" ? 0 : snap.deadline_ms, clockOffset);
  const obs = snap.observation;
  const urgent = left <= 10 && snap.phase !== "finished";
  return (
    <Paper elevation={0} sx={{ p: 1.5, mb: 1.5, border: 1, borderColor: "divider" }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" spacing={1}>
        <Box>
          <Typography variant="overline" color="text.secondary" lineHeight={1.2}>
            {snap.label}
          </Typography>
          <Typography variant="h6" lineHeight={1.2}>
            {snap.phase === "finished" ? "Game over" : `Round ${snap.round}`}
          </Typography>
        </Box>
        {snap.phase !== "finished" && (
          <Box textAlign="center" aria-live="polite">
            <Typography variant="overline" color="text.secondary" lineHeight={1.2}>
              Time left
            </Typography>
            <Typography variant="h6" lineHeight={1.2} color={urgent ? "error.main" : "text.primary"}>
              {Math.floor(left / 60)}:{String(left % 60).padStart(2, "0")}
            </Typography>
          </Box>
        )}
        {snap.role === "coordinator" ? (
          <Box textAlign="right">
            <Typography variant="overline" color="text.secondary" lineHeight={1.2}>
              Your role
            </Typography>
            <Typography variant="h6" lineHeight={1.2}>
              Coordinator
            </Typography>
          </Box>
        ) : (
          <Box textAlign="right">
            <Typography variant="overline" color="text.secondary" lineHeight={1.2}>
              Coins · Savings
            </Typography>
            <Typography variant="h6" lineHeight={1.2}>
              {coins(obs.wealth)} · {coins(obs.capital)}
            </Typography>
          </Box>
        )}
      </Stack>
      {snap.phase !== "finished" && (
        <Stack direction="row" spacing={0.5} sx={{ mt: 1, flexWrap: "wrap", rowGap: 0.5 }}>
          {snap.phases.map((p) => (
            <Chip
              key={p}
              size="small"
              label={PHASE_TITLES[p] || p}
              color={p === snap.phase ? "primary" : "default"}
              variant={p === snap.phase ? "filled" : "outlined"}
            />
          ))}
        </Stack>
      )}
    </Paper>
  );
}

// Fish stock, infrastructure and this round's event (public information).
export function SharedState({ snap }) {
  const obs = snap.observation;
  const pct = Math.max(0, Math.min(100, (obs.stock / obs.carrying_capacity) * 100));
  const ev = describeEvent(obs.event, snap.policy.insurance);
  return (
    <Paper elevation={0} sx={{ p: 1.5, mb: 1.5, border: 1, borderColor: "divider" }}>
      <Stack direction="row" justifyContent="space-between">
        <Typography variant="body2" fontWeight={600}>
          Fish in the sea
        </Typography>
        <Typography variant="body2">
          {coins(obs.stock)} / {coins(obs.carrying_capacity, 0)}
        </Typography>
      </Stack>
      <LinearProgress
        variant="determinate"
        value={pct}
        aria-label="Fish stock"
        sx={{ height: 10, borderRadius: 5, my: 0.75 }}
        color={pct < 20 ? "error" : pct < 40 ? "warning" : "primary"}
      />
      <Stack direction="row" justifyContent="space-between" sx={{ mt: 0.5 }}>
        <Typography variant="body2" color="text.secondary">
          Infrastructure level: <b>{coins(obs.infra, 2)}</b>
        </Typography>
        {obs.event && (
          <Typography variant="body2" color="text.secondary">
            Event: <b>{ev.title}</b>
          </Typography>
        )}
      </Stack>
    </Paper>
  );
}

const FAVOR_TEXT = {
  quota_exempt: "the quota does not apply to you",
  audit_immune: "you are never audited",
  double_redistribution_weight: "you get a double share of the pot",
};

// Special treatment the coordinator granted this islander (only they are told).
function OwnFavors({ favors }) {
  const on = Object.entries(favors || {}).filter(([, v]) => v).map(([k]) => FAVOR_TEXT[k] || k);
  if (!on.length) return null;
  return (
    <Typography variant="body2" sx={{ mt: 0.5 }}>
      <b>Special treatment for you</b> (the other islanders are not told): {on.join("; ")}.
    </Typography>
  );
}

// The rules in force. In the no-coordinator condition there is no one setting policy.
export function PolicyBanner({ snap }) {
  const p = snap.policy;
  const rules = [];
  if (p.quota > 0) rules.push(`Quota ${p.quota} fish per islander (fine ${p.fine} per fish over, audit chance ${Math.round(p.audit_prob * 100)}%)`);
  if (p.tax_rate > 0) rules.push(`Tax ${Math.round(p.tax_rate * 100)}% on fishing income, ${describeRedistribution(p.redistribution)}`);
  if (p.match_rate > 0) rules.push(`Contributions matched at ${Math.round(p.match_rate * 100)}% from the tax pot`);
  if (p.insurance) rules.push(`Storm insurance on (premium ${coins(snap.preview.insurance_premium)} coins per round)`);
  if (snap.has_coordinator && p.info_policy === "totals_only") rules.push("Only group totals are shown after each round");
  return (
    <Paper elevation={0} sx={{ p: 1.5, mb: 1.5, bgcolor: "action.hover" }}>
      <Typography variant="body2" fontWeight={600}>
        {snap.has_coordinator ? "The coordinator's rules" : "No coordinator — your group governs itself"}
      </Typography>
      {p.announcement && (
        <Typography variant="body2" sx={{ mt: 0.5, fontStyle: "italic", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
          “{p.announcement}”
        </Typography>
      )}
      {snap.role === "player" && snap.coordinator_left && (
        <Typography variant="body2" sx={{ mt: 0.5 }}>
          <b>The coordinator has left the game.</b> These rules stay in force for the rest of the game.
        </Typography>
      )}
      {snap.role === "player" && <OwnFavors favors={snap.observation.own_favors} />}
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
        {rules.length
          ? rules.join(" · ")
          : snap.has_coordinator && snap.round <= 1 && snap.phase === "policy"
            ? "No rules yet."
            : "No quota, no tax, no fines, no insurance."}
      </Typography>
    </Paper>
  );
}
