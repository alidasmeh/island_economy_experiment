// Participant instructions. Every number comes from the server's config (GET /api/rules).
import React, { useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  LinearProgress,
  Paper,
  Slider,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableRow,
  Typography,
} from "@mui/material";
import { coins, describeEvent, PHASE_TITLES } from "../format";

const pct = (x, digits = 0) => `${(x * 100).toFixed(digits)}%`;

const letters = (n) => {
  const l = Array.from({ length: n }, (_, i) => `Islander ${String.fromCharCode(65 + i)}`);
  return l.length > 1 ? `${l.slice(0, -1).join(", ")} or ${l[l.length - 1]}` : l[0];
};

function P({ children }) {
  return (
    <Typography variant="body1" sx={{ mb: 1.5 }}>
      {children}
    </Typography>
  );
}

function Welcome({ r }) {
  return (
    <>
      <P>
        In this study you play a game with <b>{r.n_players - 1} other participants</b>. Together you are{" "}
        {r.n_players} islanders who live from the same sea.
      </P>
      <P>
        The game lasts several rounds. You will not know in advance exactly how many, so every round could be followed
        by another one.
      </P>
      <P>
        Everyone else in your group is a real person taking part in this study right now. You will not learn who they
        are, and they will not learn who you are. In the game everyone is called by a letter:{" "}
        <b>{letters(r.n_players)}</b>.
      </P>
      <P>
        You earn <b>coins</b> in the game. At the end, your coins become a bonus payment:{" "}
        <b>
          {r.coins_per_currency_unit} coins = 1 {r.currency}
        </b>
        , on top of the participation payment.
      </P>
    </>
  );
}

function Rounds({ r }) {
  const rows = [
    ["event", "You see what happens at sea this round (for example a storm)."],
    ["communication", "You can communicate with your group."],
    ["decision", "You privately decide how to use your effort this round."],
    ["resolution", "You see what happened: your income, the group's catch and the fish left in the sea."],
  ];
  return (
    <>
      <P>Every round has the same steps. A timer shows how much time is left for each step.</P>
      <Table size="small" sx={{ mb: 2 }}>
        <TableBody>
          {rows.map(([phase, text]) => (
            <TableRow key={phase}>
              <TableCell sx={{ fontWeight: 600, pl: 0, verticalAlign: "top" }}>{PHASE_TITLES[phase]}</TableCell>
              <TableCell sx={{ pr: 0 }}>
                {text}{" "}
                <Typography component="span" variant="body2" color="text.secondary">
                  (up to {r.phase_seconds[phase]} s)
                </Typography>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <P>A step ends early when everyone in the group is done, so you will often wait less.</P>
    </>
  );
}

function Effort({ r }) {
  const perPointStart = r.catchability * r.stock_initial * r.infra_initial * r.price;
  const infraPct = r.infra_gain_per_point / r.infra_initial;
  return (
    <>
      <P>
        In every round you have <b>{r.effort_points} effort points</b>. You split them, as you like, between three
        activities:
      </P>
      <Box component="ul" sx={{ pl: 2.5, mt: 0, mb: 1.5 }}>
        <li>
          <Typography sx={{ mb: 1 }}>
            <b>Fish.</b> You catch fish and sell them right away for coins. At the start of the game one point of
            fishing brings about <b>{coins(perPointStart)} coins</b>. The fewer fish there are in the sea, the less each
            point brings.
          </Typography>
        </li>
        <li>
          <Typography sx={{ mb: 1 }}>
            <b>Build infrastructure</b> (boats, nets, harbours). This brings you nothing this round, but it makes{" "}
            <b>everyone's</b> fishing more productive in later rounds: each point adds about {pct(infraPct, 1)} to the
            catch of every islander. Infrastructure wears out by {pct(r.infra_depreciation)} each round.
          </Typography>
        </li>
        <li>
          <Typography sx={{ mb: 1 }}>
            <b>Save.</b> Each point adds <b>{coins(r.saving_return_per_point)} coins</b> to your private savings. Your
            savings earn {pct(r.interest_rate)} interest every round. Saving is safe but does not depend on the sea.
          </Typography>
        </li>
      </Box>
      <P>
        You can also <b>send coins</b> to another islander when you decide.
      </P>
      <P>
        Your decision is private. If you do not decide in time, your choice from the previous round is used again (in
        the first round: fish {r.timeout_default_allocation.harvest}, build {r.timeout_default_allocation.contribute},
        save {r.timeout_default_allocation.save}).
      </P>
    </>
  );
}

function Sea({ r }) {
  const groupShare = r.n_players * r.effort_points * r.catchability * r.infra_initial;
  return (
    <>
      <P>
        All islanders fish from the <b>same sea</b>. The sea can hold up to {coins(r.carrying_capacity, 0)} fish. At the
        start it holds {coins(r.stock_initial, 0)}.
      </P>
      <Box sx={{ my: 2 }}>
        <LinearProgress
          variant="determinate"
          value={(r.stock_initial / r.carrying_capacity) * 100}
          sx={{ height: 12, borderRadius: 6 }}
          aria-label="Fish at the start"
        />
        <Stack direction="row" justifyContent="space-between">
          <Typography variant="caption">0</Typography>
          <Typography variant="caption">start: {coins(r.stock_initial, 0)}</Typography>
          <Typography variant="caption">{coins(r.carrying_capacity, 0)}</Typography>
        </Stack>
      </Box>
      <P>
        After every round the fish <b>grow back</b>. They grow back fastest when the sea is about half full, and slowly
        when it is nearly empty or nearly full.
      </P>
      <P>
        If fewer than <b>{coins(r.stock_min, 0)} fish</b> are left, the fish <b>stop growing back</b> for good, and
        there is little left for anyone to catch.
      </P>
      <Alert severity="info" sx={{ mb: 1.5 }}>
        If all {r.n_players} islanders put all their points into fishing, the group would take about{" "}
        {pct(Math.min(1, groupShare))} of the fish in one round — more than can grow back.
      </Alert>
      <P>If the group tries to catch more fish than there are, everyone's catch is cut back by the same share.</P>
    </>
  );
}

function Differences({ r }) {
  return (
    <>
      <P>Islanders do not all start the same:</P>
      <Box component="ul" sx={{ pl: 2.5, mt: 0 }}>
        <li>
          <Typography sx={{ mb: 1 }}>
            Everyone starts with a different number of coins, between {r.wealth_min} and {r.wealth_max}.
          </Typography>
        </li>
        <li>
          <Typography sx={{ mb: 1 }}>
            Some islanders are better at fishing than others: from {pct(r.skill_min)} to {pct(r.skill_max)} of an
            average islander's catch.
          </Typography>
        </li>
      </Box>
      <P>These differences are decided by chance before the game starts. You will see your own coins in the game.</P>
    </>
  );
}

function Events({ r, condition }) {
  return (
    <>
      <P>At the start of every round, chance decides what happens at sea:</P>
      <Table size="small" sx={{ mb: 2 }}>
        <TableBody>
          {r.events.map((e) => {
            const d = describeEvent(e, condition !== "none");
            return (
              <TableRow key={e.name}>
                <TableCell sx={{ fontWeight: 600, pl: 0, verticalAlign: "top" }}>{d.title}</TableCell>
                <TableCell>{d.effects.join("; ")}</TableCell>
                <TableCell align="right" sx={{ pr: 0, color: "text.secondary", whiteSpace: "nowrap" }}>
                  {pct(e.probability)} of rounds
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </>
  );
}

function Rules({ condition }) {
  if (condition === "human") {
    // Milestone 4 adds the coordinator's instructions here.
    return <P>Your group has a coordinator, who is another participant in this study.</P>;
  }
  return (
    <>
      <P>
        In your group, <b>nobody sets rules</b>. There is no tax, no fishing limit and no fine. How much each islander
        fishes, builds and saves is up to them.
      </P>
      <P>Your group can use the communication step of each round to talk about what to do.</P>
    </>
  );
}

function TryIt({ r }) {
  const [a, setA] = useState({ harvest: 4, contribute: 3, save: 3 });
  const E = r.effort_points;
  const used = a.harvest + a.contribute + a.save;
  const set = (k, v) => setA((s) => ({ ...s, [k]: Math.max(0, Math.min(v, E - (used - s[k]))) }));
  const fishCoins = r.catchability * a.harvest * r.stock_initial * r.infra_initial * r.price;
  const saving = r.saving_return_per_point * a.save;
  const infraPct = (r.infra_gain_per_point * a.contribute) / r.infra_initial;
  const rows = [
    ["harvest", "Fish"],
    ["contribute", "Build infrastructure"],
    ["save", "Save"],
  ];
  return (
    <>
      <P>Try it out. This is only an example for an average islander in the first round; nothing here counts.</P>
      <Paper elevation={0} sx={{ p: 2, border: 1, borderColor: "divider" }}>
        <Typography variant="body2" color="text.secondary">
          Points left: <b>{E - used}</b>
        </Typography>
        {rows.map(([k, label]) => (
          <Box key={k} sx={{ mt: 1 }}>
            <Stack direction="row" justifyContent="space-between">
              <Typography fontWeight={600}>{label}</Typography>
              <Typography fontWeight={600}>{a[k]}</Typography>
            </Stack>
            <Slider value={a[k]} min={0} max={E} step={1} marks onChange={(_e, v) => set(k, v)} aria-label={label} />
          </Box>
        ))}
        <Typography variant="body2" sx={{ mt: 1 }}>
          This round: about <b>{coins(fishCoins)} coins</b> from fishing and <b>{coins(saving)} coins</b> into savings.
        </Typography>
        <Typography variant="body2" sx={{ mt: 0.5 }}>
          From next round on: everyone's fishing about <b>{pct(infraPct, 1)}</b> better because of your building.
        </Typography>
      </Paper>
      <P />
      <P>
        Fishing pays the most right now, but every fish you catch is no longer in the sea for later rounds — for you
        and for everyone else.
      </P>
    </>
  );
}

function Payment({ r }) {
  return (
    <>
      <P>
        At the end of the game, your <b>coins plus your savings</b> are your result. They are paid as a bonus:{" "}
        <b>
          {r.coins_per_currency_unit} coins = 1 {r.currency}
        </b>
        .
      </P>
      <P>
        Please stay until the end and keep this tab open. The other islanders depend on you: the game only works if
        everyone takes part in every round.
      </P>
      <P>When you continue, you will wait until your group is complete. The game then starts automatically.</P>
    </>
  );
}

export default function Instructions({ rules, condition = "none", onDone, doneLabel = "I'm ready" }) {
  const pages = useMemo(
    () => [
      ["Welcome", Welcome],
      ["How a round works", Rounds],
      ["Your effort points", Effort],
      ["The sea", Sea],
      ["Not everyone is the same", Differences],
      ["Events", (props) => <Events {...props} condition={condition} />],
      ["Who sets the rules?", () => <Rules condition={condition} />],
      ["Try it", TryIt],
      ["Your payment", Payment],
    ],
    [condition]
  );
  const [i, setI] = useState(0);
  const [title, Page] = pages[i];
  const last = i === pages.length - 1;
  return (
    <Paper elevation={0} sx={{ p: { xs: 2, sm: 3 }, border: 1, borderColor: "divider" }}>
      <Typography variant="overline" color="text.secondary">
        Instructions · {i + 1} of {pages.length}
      </Typography>
      <LinearProgress variant="determinate" value={((i + 1) / pages.length) * 100} sx={{ mb: 2, borderRadius: 2 }} />
      <Typography variant="h5" gutterBottom>
        {title}
      </Typography>
      <Page r={rules} />
      <Stack direction="row" spacing={1.5} sx={{ mt: 2 }}>
        <Button variant="outlined" disabled={i === 0} onClick={() => setI(i - 1)} sx={{ flex: 1 }}>
          Back
        </Button>
        <Button
          variant="contained"
          onClick={() => {
            window.scrollTo(0, 0);
            if (last) onDone && onDone();
            else setI(i + 1);
          }}
          sx={{ flex: 2 }}
          disabled={last && !onDone}
        >
          {last ? doneLabel : "Next"}
        </Button>
      </Stack>
    </Paper>
  );
}
