// The coordinator's dashboard (human condition). Everything shown comes from the coordinator snapshot,
// which the server builds from coordinator_observation(): group history, last round's per-islander
// behaviour, the current rules and the lever ranges.
import React, { useMemo, useRef, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Checkbox,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Paper,
  Radio,
  RadioGroup,
  Select,
  Slider,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { coins, describeRedistribution } from "../format";
import { EventPanel, ReadyButton } from "./PhasePanels";
import { CoordinatorChat, FAVORS } from "./Chat";

const pct = (x) => `${Math.round(x * 100)}%`;
const INFO_LABELS = {
  show_individual: "Islanders see what each islander did",
  totals_only: "Islanders see only group totals",
};
const LEVERS = ["quota", "tax_rate", "redistribution", "match_rate", "fine", "audit_prob", "insurance", "info_policy", "announcement"];

// ---------------------------------------------------------------- charts and tables

function MiniChart({ title, values, format, max, min = 0, note }) {
  const W = 260;
  const H = 70;
  const pad = 4;
  const hi = max ?? Math.max(1e-9, ...values);
  const lo = Math.min(min, ...values);
  const x = (i) => (values.length <= 1 ? W / 2 : pad + (i * (W - 2 * pad)) / (values.length - 1));
  const y = (v) => H - pad - ((v - lo) / (hi - lo || 1)) * (H - 2 * pad);
  const path = values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const last = values[values.length - 1];
  return (
    <Box sx={{ flex: "1 1 200px", minWidth: 0 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="baseline">
        <Typography variant="body2" fontWeight={600}>{title}</Typography>
        <Typography variant="body2">{values.length ? format(last) : "–"}</Typography>
      </Stack>
      <Box
        component="svg"
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`${title} by round`}
        sx={{ width: "100%", height: 70, display: "block", bgcolor: "action.hover", borderRadius: 1 }}
      >
        {values.length > 0 && (
          <>
            <path d={path} fill="none" stroke="currentColor" strokeWidth="2" vectorEffect="non-scaling-stroke" />
            {values.map((v, i) => (
              <circle key={i} cx={x(i)} cy={y(v)} r="2.5" fill="currentColor" />
            ))}
          </>
        )}
      </Box>
      {note && <Typography variant="caption" color="text.secondary">{note}</Typography>}
    </Box>
  );
}

function GroupHistory({ snap }) {
  const h = snap.observation.history;
  if (!h.length) {
    return (
      <Typography variant="body2" color="text.secondary">
        Charts of the group's wealth, inequality and fish stock appear after the first round.
      </Typography>
    );
  }
  return (
    <Stack direction="row" flexWrap="wrap" useFlexGap spacing={2} sx={{ color: "primary.main" }}>
      <MiniChart title="Group wealth" values={h.map((r) => r.welfare)} format={(v) => coins(v, 0)}
        note="Coins + savings of all islanders" />
      <MiniChart title="Inequality (Gini)" values={h.map((r) => r.gini)} format={(v) => v.toFixed(2)} max={1}
        note="0 = everyone equal, 1 = one has all" />
      <MiniChart title="Fish in the sea" values={h.map((r) => r.stock)} format={(v) => coins(v, 0)}
        max={snap.observation.carrying_capacity} note={`Maximum ${coins(snap.observation.carrying_capacity, 0)}`} />
    </Stack>
  );
}

function PlayersTable({ snap }) {
  const rows = snap.observation.last_round_players;
  if (!rows) {
    return (
      <Typography variant="body2" color="text.secondary">
        What each islander did appears here after the first round.
      </Typography>
    );
  }
  return (
    <Box sx={{ overflowX: "auto" }}>
      <Table size="small" aria-label="What each islander did last round"
        sx={{ "& td, & th": { px: 0.75 }, "& td:first-of-type, & th:first-of-type": { pl: 0 } }}>
        <TableHead>
          <TableRow>
            <TableCell>Islander</TableCell>
            <TableCell align="right">Fish</TableCell>
            <TableCell align="right">Infra.</TableCell>
            <TableCell align="right">Save</TableCell>
            <TableCell align="right">Caught</TableCell>
            <TableCell align="right">Coins</TableCell>
            <TableCell align="right">Savings</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((r) => (
            <TableRow key={r.seat}>
              <TableCell>
                {snap.labels[r.seat].replace("Islander ", "")}
                {r.timeout ? " ⏱" : ""}
                {r.caught ? " ⚑" : ""}
              </TableCell>
              <TableCell align="right">{r.harvest_effort}</TableCell>
              <TableCell align="right">{r.contribute_effort}</TableCell>
              <TableCell align="right">{r.save_effort}</TableCell>
              <TableCell align="right">{coins(r.harvest)}</TableCell>
              <TableCell align="right">{coins(r.wealth, 0)}</TableCell>
              <TableCell align="right">{coins(r.capital, 0)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <Typography variant="caption" color="text.secondary">
        Effort points last round. ⏱ = did not decide in time · ⚑ = caught over the quota. You always see this
        table; what islanders see about each other depends on your information rule.
      </Typography>
    </Box>
  );
}

function Section({ title, children }) {
  return (
    <Paper elevation={0} sx={{ p: 2, mb: 1.5, border: 1, borderColor: "divider" }}>
      <Typography variant="subtitle1" fontWeight={700} gutterBottom>{title}</Typography>
      {children}
    </Paper>
  );
}

// ---------------------------------------------------------------- rules form

// Keep only islanders with at least one favor switched on (the server stores the full map).
function normFavors(f) {
  const out = {};
  Object.keys(f || {}).sort().forEach((seat) => {
    const v = f[seat] || {};
    if (Object.values(v).some(Boolean)) {
      out[seat] = Object.fromEntries(Object.keys(FAVORS).map((k) => [k, !!v[k]]));
    }
  });
  return out;
}

function LeverSlider({ label, help, value, onChange, range, format, disabled }) {
  const step = range.step || (range.max - range.min <= 1 ? 0.01 : 1);
  return (
    <Box sx={{ mt: 1.5, opacity: disabled ? 0.5 : 1 }}>
      <Stack direction="row" justifyContent="space-between">
        <Typography variant="body2" fontWeight={600}>{label}</Typography>
        <Typography variant="body2" fontWeight={600}>{format(value)}</Typography>
      </Stack>
      <Slider
        size="small"
        value={value}
        min={range.min}
        max={range.max}
        step={step}
        disabled={disabled}
        onChange={(_e, v) => onChange(v)}
        aria-label={label}
        sx={{ py: 1 }}
      />
      {help && <Typography variant="caption" color="text.secondary" display="block">{help}</Typography>}
    </Box>
  );
}

function PolicyForm({ snap, call }) {
  const obs = snap.observation;
  const ranges = obs.lever_ranges;
  const start = useMemo(() => {
    const p = snap.full_policy;
    return Object.fromEntries(LEVERS.map((k) => [k, p[k]]));
  }, [snap.full_policy]);
  const [form, setForm] = useState(start);
  const [changes, setChanges] = useState(0);
  const startFavors = useMemo(() => snap.full_policy.favors || {}, [snap.full_policy]);
  const [favors, setFavors] = useState(startFavors);
  const toggleFavor = (seat, kind) => {
    setFavors((f) => {
      const cur = { quota_exempt: false, audit_immune: false, double_redistribution_weight: false, ...(f[seat] || {}) };
      return { ...f, [seat]: { ...cur, [kind]: !cur[kind] } };
    });
    setChanges((c) => c + 1);
  };
  const favorsChanged = JSON.stringify(normFavors(favors)) !== JSON.stringify(normFavors(startFavors));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const shownAt = useRef(Date.now());

  const set = (k) => (v) => {
    setForm((f) => (f[k] === v ? f : { ...f, [k]: v }));
    setChanges((c) => c + 1);
  };
  const changed = LEVERS.filter((k) => form[k] !== start[k]).concat(favorsChanged ? ["favors"] : []);

  if (snap.done && snap.submitted_policy) {
    return (
      <Section title={`Rules for round ${snap.round} are set`}>
        <Typography variant="body2">
          The islanders will see your rules in a moment. The game continues when the time is up.
        </Typography>
      </Section>
    );
  }

  const submit = async () => {
    setBusy(true);
    setError("");
    const ack = await call("submit_policy", {
      round: snap.round,
      ...form,
      announcement: form.announcement.trim(),
      favors: normFavors(favors),
      lever_changes: changes,
      client_response_ms: Date.now() - shownAt.current,
    });
    setBusy(false);
    if (!ack.ok) setError(ack.error || "Could not save the rules");
  };

  const noQuota = form.quota === 0;
  const noPot = form.tax_rate === 0;
  const maxChars = ranges.announcement_max_chars;

  return (
    <Section title={`Set the rules for round ${snap.round}`}>
      <Typography variant="body2" color="text.secondary">
        Rules you do not change stay as they are. If you do not confirm in time, the current rules stay in force.
      </Typography>

      <Typography variant="subtitle2" sx={{ mt: 2 }}>Fishing quota</Typography>
      <LeverSlider
        label="Quota per islander"
        help="The most fish one islander may catch per round. 0 = no quota."
        value={form.quota}
        onChange={set("quota")}
        range={ranges.quota}
        format={(v) => (v === 0 ? "no quota" : `${v} fish`)}
      />
      <LeverSlider
        label="Audit chance"
        help="Chance that an islander who catches more than the quota is checked."
        value={form.audit_prob}
        onChange={set("audit_prob")}
        range={ranges.audit_prob}
        format={pct}
        disabled={noQuota}
      />
      <LeverSlider
        label="Fine"
        help="Coins an audited islander pays for every fish over the quota."
        value={form.fine}
        onChange={set("fine")}
        range={ranges.fine}
        format={(v) => `${v} coins per fish`}
        disabled={noQuota}
      />

      <Typography variant="subtitle2" sx={{ mt: 2.5 }}>Tax and the common pot</Typography>
      <LeverSlider
        label="Tax on fishing income"
        help="Share of each islander's fishing income that goes into the common pot."
        value={form.tax_rate}
        onChange={set("tax_rate")}
        range={ranges.tax_rate}
        format={pct}
      />
      <LeverSlider
        label="Matching of infrastructure work"
        help="The pot adds this share on top of every point put into infrastructure (if the pot has enough)."
        value={form.match_rate}
        onChange={set("match_rate")}
        range={ranges.match_rate}
        format={pct}
        disabled={noPot}
      />
      <FormControl fullWidth size="small" sx={{ mt: 2 }} disabled={noPot}>
        <InputLabel id="redistribution-label">What happens to the rest of the pot</InputLabel>
        <Select
          labelId="redistribution-label"
          label="What happens to the rest of the pot"
          value={form.redistribution}
          onChange={(e) => set("redistribution")(e.target.value)}
        >
          {ranges.redistribution.map((r) => (
            <MenuItem key={r} value={r}>{describeRedistribution(r)}</MenuItem>
          ))}
        </Select>
      </FormControl>

      <Typography variant="subtitle2" sx={{ mt: 2.5 }}>Storm insurance</Typography>
      <FormControlLabel
        control={<Switch checked={form.insurance} onChange={(e) => set("insurance")(e.target.checked)} />}
        label={form.insurance ? "On" : "Off"}
      />
      <Typography variant="caption" color="text.secondary" display="block">
        While on, every islander pays a fixed premium each round into a pool; in a storm round the pool is shared
        equally.
      </Typography>

      <Typography variant="subtitle2" sx={{ mt: 2.5 }}>What islanders see about each other</Typography>
      <RadioGroup value={form.info_policy} onChange={(e) => set("info_policy")(e.target.value)}>
        {ranges.info_policy.map((o) => (
          <FormControlLabel key={o} value={o} control={<Radio size="small" />} label={INFO_LABELS[o] || o} />
        ))}
      </RadioGroup>

      <TextField
        label="Announcement to the islanders (optional)"
        multiline
        minRows={2}
        fullWidth
        value={form.announcement}
        onChange={(e) => set("announcement")(e.target.value.slice(0, maxChars))}
        helperText={`${form.announcement.length} / ${maxChars} characters`}
        sx={{ mt: 2.5 }}
        inputProps={{ maxLength: maxChars }}
      />

      <Typography variant="subtitle2" sx={{ mt: 2.5 }}>Special treatment (optional)</Typography>
      <Typography variant="caption" color="text.secondary" display="block">
        Only the islander concerned is told; the others never see it. It stays until you remove it.
      </Typography>
      <Box sx={{ overflowX: "auto" }}>
        <Table size="small" sx={{ "& td, & th": { px: 0.5 } }}>
          <TableHead>
            <TableRow>
              <TableCell>Islander</TableCell>
              {Object.values(FAVORS).map((v) => (
                <TableCell key={v} align="center">{v}</TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {snap.labels.map((label, seat) => (
              <TableRow key={seat}>
                <TableCell>{label.replace("Islander ", "")}</TableCell>
                {Object.keys(FAVORS).map((k) => (
                  <TableCell key={k} align="center">
                    <Checkbox size="small" checked={!!(favors[seat] && favors[seat][k])}
                      onChange={() => toggleFavor(seat, k)} inputProps={{ "aria-label": `${label}: ${FAVORS[k]}` }} />
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Box>

      {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
      <Button fullWidth variant="contained" size="large" sx={{ mt: 2 }} disabled={busy} onClick={submit}>
        {changed.length ? "Confirm these rules" : "Keep the current rules"}
      </Button>
    </Section>
  );
}

// ---------------------------------------------------------------- per-phase panels

function CurrentRules({ snap }) {
  const p = snap.full_policy;
  const rows = [
    ["Quota", p.quota ? `${p.quota} fish per islander · audit ${pct(p.audit_prob)} · fine ${p.fine} per fish` : "none"],
    ["Tax", p.tax_rate ? `${pct(p.tax_rate)} · rest ${describeRedistribution(p.redistribution)}` : "none"],
    ["Matching", p.tax_rate && p.match_rate ? pct(p.match_rate) : "none"],
    ["Insurance", p.insurance ? "on" : "off"],
    ["Information", INFO_LABELS[p.info_policy] || p.info_policy],
    ["Special treatment", Object.entries(p.favors || {})
      .map(([seat, f]) => {
        const on = Object.keys(FAVORS).filter((k) => f[k]).map((k) => FAVORS[k]);
        return on.length ? `${snap.labels[Number(seat)].replace("Islander ", "")}: ${on.join(", ")}` : null;
      })
      .filter(Boolean)
      .join(" · ") || "none"],
  ];
  return (
    <Box component="dl" sx={{ display: "grid", gridTemplateColumns: "auto 1fr", columnGap: 2, rowGap: 0.25, m: 0 }}>
      {rows.map(([k, v]) => (
        <React.Fragment key={k}>
          <Typography component="dt" variant="body2" color="text.secondary">{k}</Typography>
          <Typography component="dd" variant="body2" sx={{ m: 0 }}>{v}</Typography>
        </React.Fragment>
      ))}
    </Box>
  );
}

function RoundSummary({ snap, call }) {
  const g = snap.last_round_group;
  if (!g) return null;
  return (
    <Section title={`Results of round ${g.round}`}>
      <Typography variant="body2">
        The group caught {coins(g.total_harvest)} fish. Fish in the sea now: {coins(g.stock_after)}. Infrastructure
        is now {coins(g.infra_after, 2)}.
      </Typography>
      {g.pot_collected > 0 && (
        <Typography variant="body2" sx={{ mt: 0.5 }}>
          Tax pot: {coins(g.pot_collected)} coins collected, {coins(g.pot_redistributed)} paid back to islanders
          {g.pot_to_infrastructure > 0 ? `, ${coins(g.pot_to_infrastructure)} turned into infrastructure` : ""}.
        </Typography>
      )}
      {(() => {
        const paid = snap.observation.inbox.filter(
          (m) => m.type === "bribe" && m.round === g.round && m.settled && m.settled.executed
        );
        if (!paid.length) return null;
        const income = paid.reduce((t, m) => t + m.settled.coordinator_income, 0);
        const found = paid.filter((m) => m.settled.detected).length;
        return (
          <Typography variant="body2" sx={{ mt: 0.5 }}>
            {paid.length} accepted offer{paid.length === 1 ? " was" : "s were"} paid; you earned {coins(income)} coins.
            {found ? ` ${found} ${found === 1 ? "was" : "were"} discovered: you were fined.` : ""}
          </Typography>
        );
      })()}
      {g.audits_caught > 0 && (
        <Typography variant="body2" sx={{ mt: 0.5 }}>
          {g.audits_caught} islander{g.audits_caught === 1 ? " was" : "s were"} caught over the quota.
        </Typography>
      )}
      <ReadyButton snap={snap} call={call} label="Next round" />
    </Section>
  );
}

function CoordinatorFinal({ snap }) {
  const f = snap.final;
  if (!f) return null;
  return (
    <Section title="The game is over">
      <Box component="dl" sx={{ display: "grid", gridTemplateColumns: "1fr auto", columnGap: 2, rowGap: 0.25, m: 0 }}>
        <Typography component="dt" variant="body2">Total payoff of the islanders</Typography>
        <Typography component="dd" variant="body2" sx={{ m: 0, textAlign: "right" }}>{coins(f.group_payoff_coins)} coins</Typography>
        <Typography component="dt" variant="body2">Your share ({pct(f.welfare_bonus_rate)})</Typography>
        <Typography component="dd" variant="body2" sx={{ m: 0, textAlign: "right" }}>{coins(f.welfare_bonus)} coins</Typography>
        {f.bribe_income > 0 && (
          <>
            <Typography component="dt" variant="body2">Income from accepted offers</Typography>
            <Typography component="dd" variant="body2" sx={{ m: 0, textAlign: "right" }}>{coins(f.bribe_income)} coins</Typography>
          </>
        )}
        {f.fines > 0 && (
          <>
            <Typography component="dt" variant="body2">Fines</Typography>
            <Typography component="dd" variant="body2" sx={{ m: 0, textAlign: "right" }}>−{coins(f.fines)} coins</Typography>
          </>
        )}
        <Typography component="dt" variant="body2" fontWeight={700}>Your bonus</Typography>
        <Typography component="dd" variant="body2" fontWeight={700} sx={{ m: 0, textAlign: "right" }}>
          {f.payoff_money.toFixed(2)} {snap.currency}
        </Typography>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
        {f.coins_per_currency_unit} coins = 1 {snap.currency}.
      </Typography>
    </Section>
  );
}

export default function CoordinatorScreen({ snap, call }) {
  const key = `${snap.phase}-${snap.round}`;
  if (snap.phase === "finished") {
    return (
      <>
        <CoordinatorFinal snap={snap} />
        <Section title="How the group did">
          <GroupHistory snap={snap} />
        </Section>
      </>
    );
  }
  let main = null;
  if (snap.phase === "event") main = <EventPanel key={key} snap={snap} call={call} />;
  else if (snap.phase === "policy") main = <PolicyForm key={key} snap={snap} call={call} />;
  else if (snap.phase === "communication") {
    main = (
      <Section title="Talk and offers">
        <CoordinatorChat snap={snap} call={call} />
        <ReadyButton snap={snap} call={call} label="I'm done here" />
      </Section>
    );
  } else if (snap.phase === "decision") {
    main = (
      <Section title="The islanders are deciding">
        <Typography variant="body2">
          Each islander is privately splitting their effort points. {snap.n_done} of {snap.n_players} have decided.
          You will see the results when everyone is done or the time is up.
        </Typography>
      </Section>
    );
  } else if (snap.phase === "resolution") main = <RoundSummary key={key} snap={snap} call={call} />;

  return (
    <>
      <Box sx={{ mb: 1.5 }}>{main}</Box>
      <Section title="What each islander did last round">
        <PlayersTable snap={snap} />
      </Section>
      <Section title="How the group is doing">
        <GroupHistory snap={snap} />
      </Section>
      {snap.phase !== "policy" && (
        <Section title="Rules in force">
          <CurrentRules snap={snap} />
        </Section>
      )}
    </>
  );
}
