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
import { coins, describeEvent, describeRedistribution, PHASE_TITLES } from "../format";

const pct = (x, digits = 0) => `${(x * 100).toFixed(digits)}%`;

const letters = (n, conj = "or") => {
  const l = Array.from({ length: n }, (_, i) => `Islander ${String.fromCharCode(65 + i)}`);
  return l.length > 1 ? `${l.slice(0, -1).join(", ")} ${conj} ${l[l.length - 1]}` : l[0];
};

function P({ children }) {
  return (
    <Typography variant="body1" sx={{ mb: 1.5 }}>
      {children}
    </Typography>
  );
}

function Welcome({ r, condition }) {
  return (
    <>
      <P>
        In this study you play a game with <b>{r.n_players - 1} other participants</b>. Together you are{" "}
        {r.n_players} islanders who live from the same sea.
        {condition === "human" && " Your group also has a coordinator: one more participant, who sets rules for the islanders."}
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

function Rounds({ r, condition, role }) {
  const coord = role === "coordinator";
  const rows = [
    ["event", coord ? "Everyone sees what happens at sea this round (for example a storm)."
      : "You see what happens at sea this round (for example a storm)."],
    ...(condition === "human"
      ? [["policy", coord ? "You set the rules for this round." : "The coordinator sets the rules for this round."]]
      : []),
    ["communication", coord
      ? "Everyone can chat: in the group chat or in private messages. Islanders can also make you offers (see below)."
      : condition === "human"
        ? "You can chat with the group, send private messages, or make a private offer to the coordinator."
        : "You can chat with the whole group or send private messages."],
    ["decision", coord ? "Each islander privately decides how to use their effort this round."
      : "You privately decide how to use your effort this round."],
    ["resolution", coord ? "You see what happened: what each islander did, the group's catch and the fish left."
      : "You see what happened: your income, the group's catch and the fish left in the sea."],
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
      <P>
        Private messages are seen only by the person you send them to. For the research, all messages are recorded;
        they are never shown to anyone outside the study.
      </P>
    </>
  );
}

function Effort({ r, condition }) {
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
        {condition === "human"
          ? "The other islanders do not see your decision while you decide. After each round the coordinator sees what every islander did; whether the islanders see it too is one of the coordinator's rules. "
          : "Your decision is private while you decide. After each round everyone sees what each islander did. "}
        If you do not decide in time, your choice from the previous round is used again (in
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

function Differences({ r, role }) {
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
      <P>
        These differences are decided by chance before the game starts.{" "}
        {role === "coordinator"
          ? "You will see every islander's coins and savings after each round."
          : "You will see your own coins in the game."}
      </P>
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

function LeverList({ r }) {
  const L = r.levers;
  return (
    <Box component="ul" sx={{ pl: 2.5, mt: 0, mb: 1.5 }}>
      <li>
        <Typography sx={{ mb: 1 }}>
          <b>A fishing quota</b> (up to {L.quota.max} fish per islander per round). Whoever catches more may be
          audited (chance up to {pct(L.audit_prob.max)}) and then pays a fine of up to {L.fine.max} coins for every
          fish over the quota.
        </Typography>
      </li>
      <li>
        <Typography sx={{ mb: 1 }}>
          <b>A tax</b> on fishing income (up to {pct(L.tax_rate.max)}), paid into a common pot. The pot can add up to{" "}
          {pct(L.match_rate.max)} on top of every point put into infrastructure. The rest of the pot is either{" "}
          {r.redistribution_options.map(describeRedistribution).join(", or ")}.
        </Typography>
      </li>
      <li>
        <Typography sx={{ mb: 1 }}>
          <b>Storm insurance:</b> every islander pays {coins(r.insurance_premium)} coins per round into a pool, which is
          shared equally in a storm round.
        </Typography>
      </li>
      <li>
        <Typography sx={{ mb: 1 }}>
          <b>What islanders see</b> after each round: what each islander did, or only the group totals.
        </Typography>
      </li>
    </Box>
  );
}

// Offers to the coordinator (coordinator condition). Shown to islanders and the coordinator alike.
function Offers({ r, role }) {
  const coord = role === "coordinator";
  return (
    <>
      <Typography variant="subtitle1" fontWeight={700} sx={{ mt: 1 }}>
        Private offers to the coordinator
      </Typography>
      <P>
        During the communication step, {coord ? "an islander" : "you"} can privately offer the coordinator coins (at
        least {r.bribe_min_amount}), with a short note. Only the coordinator sees the offer. The coordinator can accept
        or refuse it; an offer that is not answered in that step counts as refused, and the coins stay with the
        islander.
      </P>
      <P>
        If the coordinator accepts, the islander pays the coins at the end of the round and the coordinator earns{" "}
        {pct(r.bribe_income_rate)} of them (at most {r.bribe_income_cap} coins in the whole game). With an accepted
        offer the coordinator can also give that islander <b>special treatment</b>: not bound by the quota, never
        audited, or a double share of the pot. Only that islander is told; the other islanders are not. The coordinator
        can also give or remove special treatment when setting the rules.
      </P>
      <P>
        Each accepted offer is discovered with a chance of {pct(r.bribe_detection_prob)}. Then the islander and the
        coordinator each pay a fine of {r.bribe_fine} coins.
      </P>
    </>
  );
}

function Rules({ r, condition }) {
  if (condition === "human") {
    return (
      <>
        <P>
          Your group has a <b>coordinator</b>. The coordinator is <b>another participant</b> in this study, chosen at
          random. The coordinator does not fish; at the start of every round they set the rules for all{" "}
          {r.n_players} islanders. They can set:
        </P>
        <LeverList r={r} />
        <P>
          The coordinator can also write a short announcement. Rules that are not changed stay as they are. At the
          start there are no rules at all.
        </P>
        <P>
          The coordinator earns a bonus of <b>{pct(r.welfare_bonus_rate)} of the islanders' total result</b> at the end
          of the game, so the coordinator earns more when the islanders together earn more.
        </P>
        <Offers r={r} role="player" />
      </>
    );
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

function CoordWelcome({ r }) {
  return (
    <>
      <P>
        In this study you take part in a game with <b>{r.n_players} other participants</b>, the islanders, who live
        from the same sea. You have been chosen at random to be their <b>coordinator</b>.
      </P>
      <P>
        You do not fish yourself. At the start of every round you <b>set the rules</b> for the islanders. Everyone in
        the group is a real person taking part right now; the islanders know that the coordinator is another
        participant. Nobody learns who anyone is. The islanders are called {letters(r.n_players, "and")}.
      </P>
      <P>
        The game lasts several rounds. Nobody knows in advance exactly how many, so every round could be followed by
        another one.
      </P>
      <P>
        You earn <b>coins</b>. At the end they become a bonus payment:{" "}
        <b>
          {r.coins_per_currency_unit} coins = 1 {r.currency}
        </b>
        , on top of the participation payment.
      </P>
    </>
  );
}

function CoordIslanders({ r }) {
  const perPointStart = r.catchability * r.stock_initial * r.infra_initial * r.price;
  return (
    <>
      <P>
        Every round each islander has <b>{r.effort_points} effort points</b> and privately splits them between:
      </P>
      <Box component="ul" sx={{ pl: 2.5, mt: 0, mb: 1.5 }}>
        <li>
          <Typography sx={{ mb: 1 }}>
            <b>Fishing</b>: coins right away (about {coins(perPointStart)} coins per point at the start), but every fish
            caught is gone from the shared sea.
          </Typography>
        </li>
        <li>
          <Typography sx={{ mb: 1 }}>
            <b>Building infrastructure</b>: makes everyone's fishing more productive in later rounds.
          </Typography>
        </li>
        <li>
          <Typography sx={{ mb: 1 }}>
            <b>Saving</b>: {coins(r.saving_return_per_point)} coins per point into private savings with{" "}
            {pct(r.interest_rate)} interest per round.
          </Typography>
        </li>
      </Box>
      <P>
        Islanders can also send coins to each other. After each round you see exactly what every islander did, their
        catch, coins and savings.
      </P>
    </>
  );
}

function CoordRole({ r }) {
  return (
    <>
      <P>
        At the start of every round you have up to {r.phase_seconds.policy} seconds to set the rules. You can set:
      </P>
      <LeverList r={r} />
      <P>
        You can also write an announcement of up to {r.announcement_max_chars} characters, for example to explain your
        rules. Rules you do not change stay as they are. If you do not confirm in time, the current rules stay in force.
        At the start there are no rules at all. You can also give single islanders special treatment (see the next
        below); only that islander is told.
      </P>
      <Offers r={r} role="coordinator" />
      <P>
        Your screen shows how the group is doing (its total wealth, how unequal it is, and the fish in the sea) and
        what each islander did in the last round.
      </P>
    </>
  );
}

function CoordTryIt({ r }) {
  const n = r.n_players;
  const incomes = Array.from({ length: n }, (_, i) => 4 + 2 * (n - 1 - i));
  const [tax, setTax] = useState(Math.min(0.2, r.levers.tax_rate.max));
  const [rule, setRule] = useState("equal");
  const pot = incomes.reduce((a, b) => a + b, 0) * tax;
  const share = incomes.map(() => (rule === "equal" ? pot / n : 0));
  return (
    <>
      <P>
        Try it out. Suppose the {n} islanders earn these coins from fishing this round. Nothing here counts; it is only
        an example.
      </P>
      <Paper elevation={0} sx={{ p: 2, border: 1, borderColor: "divider" }}>
        <Stack direction="row" justifyContent="space-between">
          <Typography fontWeight={600}>Tax</Typography>
          <Typography fontWeight={600}>{pct(tax)}</Typography>
        </Stack>
        <Slider value={tax} min={r.levers.tax_rate.min} max={r.levers.tax_rate.max}
          step={r.levers.tax_rate.step || 0.05} onChange={(_e, v) => setTax(v)} aria-label="Tax" />
        <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
          {["equal", "infrastructure"].filter((o) => r.redistribution_options.includes(o)).map((o) => (
            <Button key={o} size="small" variant={rule === o ? "contained" : "outlined"} onClick={() => setRule(o)}>
              {o === "equal" ? "Share equally" : "Invest in infrastructure"}
            </Button>
          ))}
        </Stack>
        <Table size="small">
          <TableBody>
            {incomes.map((y, i) => (
              <TableRow key={i}>
                <TableCell sx={{ pl: 0 }}>Islander {String.fromCharCode(65 + i)}</TableCell>
                <TableCell align="right">{coins(y)} earned</TableCell>
                <TableCell align="right">−{coins(y * tax)} tax</TableCell>
                <TableCell align="right" sx={{ pr: 0 }}>
                  {rule === "equal" ? `+${coins(share[i])} share` : ""}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        <Typography variant="body2" sx={{ mt: 1 }}>
          The pot holds <b>{coins(pot)} coins</b>.{" "}
          {rule === "equal"
            ? "Shared equally, islanders who fished less get back more than they paid."
            : `Invested, it raises infrastructure by about ${coins(pot * r.infra_gain_per_pot_coin, 3)}, which helps everyone's fishing from next round on.`}
        </Typography>
      </Paper>
      <P />
    </>
  );
}

function CoordPayment({ r }) {
  const example = r.n_players * ((r.wealth_min + r.wealth_max) / 2) * 2;
  return (
    <>
      <P>
        Your bonus is <b>{pct(r.welfare_bonus_rate)} of the islanders' total result</b> (their coins plus savings at the
        end of the game, all {r.n_players} together). For example, if the islanders end with {coins(example, 0)} coins in
        total, you earn {coins(example * r.welfare_bonus_rate)} coins.
      </P>
      <P>
        On top of that you earn {pct(r.bribe_income_rate)} of every offer you accept (at most {r.bribe_income_cap} coins
        in the whole game), minus {r.bribe_fine} coins for every accepted offer that is discovered.
      </P>
      <P>
        Please stay until the end and keep this tab open. The islanders depend on you: if you do not set rules, the old
        rules simply stay in force.
      </P>
      <P>When you continue, you will wait until your group is complete. The game then starts automatically.</P>
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

export default function Instructions({ rules, condition = "none", role = "player", onDone, doneLabel = "I'm ready" }) {
  const pages = useMemo(() => {
    const ctx = (C) => (props) => <C {...props} condition={condition} role={role} />;
    if (role === "coordinator") {
      return [
        ["Welcome, coordinator", CoordWelcome],
        ["How a round works", ctx(Rounds)],
        ["What the islanders do", CoordIslanders],
        ["The sea", Sea],
        ["Not everyone is the same", ctx(Differences)],
        ["Events", ctx(Events)],
        ["Your role: setting the rules", CoordRole],
        ["Try it", CoordTryIt],
        ["Your payment", CoordPayment],
      ];
    }
    return [
      ["Welcome", ctx(Welcome)],
      ["How a round works", ctx(Rounds)],
      ["Your effort points", ctx(Effort)],
      ["The sea", Sea],
      ["Not everyone is the same", ctx(Differences)],
      ["Events", ctx(Events)],
      ["Who sets the rules?", ctx(Rules)],
      ["Try it", TryIt],
      ["Your payment", Payment],
    ];
  }, [condition, role]);
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
